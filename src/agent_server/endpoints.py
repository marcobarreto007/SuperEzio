import asyncio
import hmac
import json
import os
import re
import secrets
import time
from core.config.logging_config import get_logger
from collections.abc import AsyncGenerator
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from sse_starlette.sse import EventSourceResponse

# ML guards: lazy CPU-only quality telemetry.
from core.ml.reward_gate import reward_gate
from core.ml.sanity import sanity_check

from core.math.indicators import (
    calc_bollinger,
    calc_ema,
    calc_macd,
    calc_rsi,
    calc_sma,
)
from core.pipeline.intents import (
    detect_ticker,
    should_block_vague_financial_prompt,
    has_hint,
    detect_complex_finance_intent,
    detect_capital_allocation_intent,
    detect_decisive_trade_intent,
    detect_market_scan_intent,
    detect_broker_status_intent,
    parse_user_intent,
)
from core.risk_firewall import DecisionCandidate, evaluate_decision_with_sdca
from core.trading.td_direct_ticket import (
    TDDirectTicketError,
    append_td_direct_ticket,
    build_td_direct_ticket,
    load_td_commission_free_manifest,
)
from core.trading.approval_gate import approval_request_to_dict
from core.trading.manual_trade_workflow import ManualTradeWorkflow, ManualTradeWorkflowError
from core.trading.server_quote import ServerQuoteError, resolve_server_quote
from core.trading.canada_money_gate import (
    CanadaMoneyGate,
    CanadaMoneyGateError,
    resolve_usd_cad_evidence,
)
from core.trading.workflow_store import (
    WorkflowConflictError,
    WorkflowStoreError,
    build_trade_intent_fingerprint,
    get_trade_workflow_store,
)
from data.data_hub import hub

from core.ports.protocol import A2AMessage, MessageType  # .protocol facade removido (49f6d01)

logger = get_logger(__name__)
router = APIRouter()

_session_history: dict[str, dict[str, Any]] = {}

# Regex para extrair ticker mencionado na resposta (ex: "NOK (Nokia)", "NU (Nu Holdings)")
_RECOMMENDED_TICKER_RE = re.compile(r"\b([A-Z]{1,5})\s*\([A-Za-z]")
_ADVISORY_TRACE_ROUTES = {"capital_allocation", "personal_finance"}
_ADVISORY_TRACE_INTENTS = {
    "asset_allocation",
    "business_capital",
    "capital_allocation",
    "education_investment",
    "fraud_risk",
    "macro_thesis",
    "personal_finance",
    "real_estate_vs_markets",
}


def _get_sentiment_pulse(request: Request):
    pulse = getattr(request.app.state, "sentiment_pulse", None)
    if pulse is None:
        raise HTTPException(status_code=503, detail="sentiment pulse unavailable")
    return pulse


def _get_sentiment_monitor(request: Request):
    monitor = getattr(request.app.state, "sentiment_monitor", None)
    if monitor is None:
        raise HTTPException(status_code=503, detail="sentiment monitor unavailable")
    return monitor


def _sentiment_db_path():
    from pathlib import Path

    configured = os.getenv("SUPEREZIO_SENTIMENT_DB", "").strip()
    if configured:
        return Path(configured)
    return Path(__file__).resolve().parent.parent.parent / "runtime" / "investor.db"


def _parse_iso_datetime(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        text = str(value)
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        parsed = datetime.fromisoformat(text)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed
    except (TypeError, ValueError):
        return None


def _as_jsonable(value: Any) -> Any:
    if hasattr(value, "to_dict"):
        return value.to_dict()
    return value


def _clean_float(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not (-1e100 < number < 1e100):
        return None
    return number


def _clean_int(value: Any) -> int | None:
    number = _clean_float(value)
    if number is None:
        return None
    return int(number)


def _is_active_order_status(status: Any) -> bool:
    text = str(status or "").strip().lower().replace(" ", "")
    if not text:
        return True
    return text not in {
        "filled",
        "cancelled",
        "canceled",
        "apicancelled",
        "inactive",
        "completed",
        "done",
        "failed",
        "rejected",
    }


def _normalize_order_row(row: dict[str, Any], *, source: str) -> dict[str, Any] | None:
    ticker = str(row.get("ticker") or row.get("symbol") or "").strip().upper()
    if not ticker:
        return None
    status = str(row.get("status") or row.get("phase") or "pending").strip() or "pending"
    if not _is_active_order_status(status):
        return None
    action = str(row.get("action") or row.get("side") or "").strip().upper()
    order_id = str(row.get("order_id") or row.get("id") or f"{source}-{ticker}").strip()
    return {
        "order_id": order_id,
        "tws_order_id": str(row.get("tws_order_id") or row.get("orderId") or "").strip() or None,
        "perm_id": str(row.get("perm_id") or row.get("permId") or "").strip() or None,
        "client_id": str(row.get("client_id") or row.get("clientId") or "").strip() or None,
        "ticker": ticker,
        "symbol": ticker,
        "action": action,
        "side": action.lower() if action else "",
        "qty": _clean_float(row.get("qty") or row.get("quantity") or row.get("totalQuantity")),
        "order_type": str(row.get("order_type") or row.get("orderType") or "").strip().upper(),
        "limit_price": _clean_float(row.get("limit_price") or row.get("lmtPrice")),
        "stop_price": _clean_float(row.get("stop_price") or row.get("auxPrice")),
        "status": status,
        "source": source,
    }


def _cockpit_local_order_tickets() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    try:
        statuses = get_trade_workflow_store().list_tickets()
    except WorkflowStoreError as exc:
        logger.warning("Persistent local trade status unavailable: %s", exc)
        return rows
    for status in statuses:
        if not isinstance(status, dict):
            continue
        row = {
            "order_id": status.get("ticket_id"),
            "ticker": status.get("ticker") or status.get("symbol"),
            "action": status.get("action") or status.get("side"),
            "qty": status.get("qty") or status.get("quantity"),
            "status": status.get("status") or status.get("phase"),
            "source": "local_pending",
        }
        normalized = _normalize_order_row(row, source="local_pending")
        if normalized:
            rows.append(normalized)
    return rows


def _cockpit_ibkr_open_orders() -> list[dict[str, Any]]:
    """Get open orders from IBKRService (cached, no inline IB())."""
    enabled = str(os.getenv("SUPEREZIO_COCKPIT_READ_IBKR_ORDERS", "1")).lower()
    if enabled in {"0", "false", "no", "off"}:
        return []

    try:
        from adapters.broker import get_ibkr_service

        service = get_ibkr_service()
        orders = service.get_open_orders()

        rows = []
        for order_dict in orders:
            normalized = _normalize_order_row(order_dict, source="ibkr")
            if normalized and _is_active_order_status(normalized.get("status", "")):
                rows.append(normalized)
        return rows
    except Exception as exc:
        logger.debug("IBKR open-order read failed for cockpit: %s", exc)
        return []


def _dedupe_orders(*groups: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for group in groups:
        for row in group:
            key = str(row.get("order_id") or "") or (
                str(row.get("source") or "") + ":" + str(row.get("ticker") or "")
            )
            if key in seen:
                continue
            seen.add(key)
            out.append(row)
    return out


def _trade_history_sort_key(row: dict[str, Any]) -> str:
    return str(
        row.get("updated_at")
        or row.get("exit_date")
        or row.get("entry_date")
        or row.get("created_at")
        or ""
    )


def _normalize_trade_history_row(
    row: dict[str, Any],
    *,
    source: str = "paper_journal",
) -> dict[str, Any] | None:
    ticker = str(row.get("ticker") or row.get("symbol") or "").strip().upper()
    trade_id = str(row.get("trade_id") or row.get("order_id") or row.get("id") or "").strip()
    if not ticker or not trade_id:
        return None

    direction = str(row.get("direction") or row.get("action") or "").strip().lower()
    action = str(row.get("action") or "").strip().upper()
    if not action:
        if direction == "long":
            action = "BUY"
        elif direction == "short":
            action = "SELL"
        else:
            action = direction.upper()

    exit_date = row.get("exit_date") or None
    status = "closed" if exit_date else "open"
    return {
        "trade_id": trade_id,
        "order_id": trade_id,
        "ticker": ticker,
        "symbol": ticker,
        "action": action,
        "side": action.lower() if action else direction,
        "direction": direction,
        "qty": _clean_float(row.get("shares") or row.get("qty") or row.get("quantity")),
        "entry_price": _clean_float(row.get("entry_price")),
        "exit_price": _clean_float(row.get("exit_price")),
        "pnl_amount": _clean_float(row.get("pnl_amount")),
        "pnl_percent": _clean_float(row.get("pnl_percent")),
        "status": status,
        "outcome": row.get("outcome") or status,
        "thesis": str(row.get("thesis") or "")[:240],
        "entry_date": row.get("entry_date"),
        "exit_date": exit_date,
        "updated_at": row.get("updated_at") or row.get("created_at"),
        "source": source,
    }


def _cockpit_trade_history(limit: int = 50) -> dict[str, Any]:
    try:
        from core.trading.paper_journal import PaperJournal

        max_rows = max(1, min(int(limit), 250))
        journal = PaperJournal()
        trades = [
            normalized
            for normalized in (_normalize_trade_history_row(row) for row in journal.list_all())
            if normalized is not None
        ]
        trades.sort(key=_trade_history_sort_key, reverse=True)
        stats = journal.get_stats()
        stats["journal_records"] = len(trades)
        stats["open_hypotheses"] = sum(1 for trade in trades if trade.get("status") == "open")
        stats["broker_orders"] = 0
        stats["broker_fills"] = 0
        stats["broker_open_positions"] = 0
        return {
            "source": "paper_journal",
            "path": str(journal.path),
            "count": len(trades),
            "stats": stats,
            "trades": trades[:max_rows],
        }
    except Exception as exc:
        logger.debug("Paper journal read failed for cockpit: %s", exc)
        return {
            "source": "paper_journal",
            "count": 0,
            "stats": {},
            "trades": [],
            "error": str(exc)[:160],
        }


def _first_position_ticker(positions: list[Any]) -> str:
    for pos in positions:
        if isinstance(pos, dict):
            ticker = str(pos.get("symbol") or pos.get("ticker") or "").strip().upper()
        else:
            ticker = str(getattr(pos, "symbol", "") or getattr(pos, "ticker", "")).strip().upper()
        if ticker:
            return ticker
    return ""


def _cockpit_portfolio_snapshot() -> dict[str, Any]:
    """Get portfolio snapshot from IBKRService (cached, no inline IB())."""
    from core.mission_context import mission_health_summary
    from adapters.broker import get_ibkr_service

    mission = mission_health_summary()
    broker = ((mission.get("broker") or {}).get("ibkr") or {}) if isinstance(mission, dict) else {}
    connection = str(broker.get("connection") or "")
    connected = broker.get("can_read_account") is True or "connected" in connection

    # â”€â”€ Get live data from IBKRService (cached, isolated) â”€â”€
    service = get_ibkr_service()
    service_status = service.get_status()

    positions = service.get_positions()
    equity_float = service.get_account_equity()
    service_status = service.get_status()

    # Use service status after cache reads; first request may wait for the worker refresh.
    connected = service_status.get("connected", False) and service_status.get("can_read", False)
    from core.mission_context import get_mission_equity

    equity_default = f"{get_mission_equity():.2f}"
    equity = (
        f"{equity_float:,.2f}"
        if equity_float > 0
        else broker.get("account_equity") or equity_default
    )
    positions_count = len(positions)

    raw_mode = str(broker.get("mode") or "").lower()
    paper_configured = (
        broker.get("paper_port") is True or "paper" in raw_mode or connection == "connected_paper"
    )
    paper = bool(connected and paper_configured)
    can_submit = bool(connected and broker.get("can_submit_orders") is True and paper)
    if connected and paper:
        mode = "paper_order_enabled" if can_submit else "paper_read_only"
        connection = "connected_paper"
    elif connected:
        mode = "live_blocked"
        can_submit = False
    else:
        connection = "offline"
        mode = "offline"
        can_submit = False

    broker_orders = _cockpit_ibkr_open_orders()
    local_tickets = _cockpit_local_order_tickets()
    orders = _dedupe_orders(broker_orders, local_tickets)
    trade_history = _cockpit_trade_history(limit=12)
    selected_ticker = ""
    if orders:
        selected_ticker = str(orders[0].get("ticker") or orders[0].get("symbol") or "").upper()
    if not selected_ticker:
        selected_ticker = _first_position_ticker(positions)
    orders_source = "ibkr" if broker_orders else ("local_pending" if local_tickets else "none")
    return {
        "provider": "IBKR",
        "connected": connected,
        "connection": connection or "unknown",
        "mode": mode,
        "paper": paper,
        "can_submit_orders": can_submit,
        "equity": equity,
        "cash": broker.get("cash") or None,
        "positions_count": positions_count,
        "positions": positions,
        "orders_count": len(orders),
        "orders": orders,
        "active_orders": orders,
        "broker_orders_count": len(broker_orders),
        "broker_orders": broker_orders,
        "local_tickets_count": len(local_tickets),
        "local_tickets": local_tickets,
        "orders_source": orders_source,
        "trade_history_count": trade_history.get("count", 0),
        "trade_history": trade_history.get("trades", []),
        "trade_stats": trade_history.get("stats", {}),
        "journal_path": trade_history.get("path"),
        "selected_ticker": selected_ticker,
        "live_port_warning": bool(connected and not paper),
        "verified_at": datetime.now(timezone.utc).isoformat(),
    }


def _cockpit_guardrail_summary() -> dict[str, Any]:
    """Return no score until a real Guardrail Hub run supplies evidence."""
    return {
        "ok": None,
        "total": None,
        "status": "unknown",
        "layers": [],
        "evidence_at": None,
    }


def _cockpit_approval_summary() -> dict[str, Any]:
    from core.trading.approval_gate import approval_request_to_dict, get_approval_gate

    gate = get_approval_gate()
    pending = [approval_request_to_dict(req) for req in gate.get_pending()]
    return {
        "pending_count": len(pending),
        "pending": pending,
    }


def _cockpit_status_snapshot(
    *,
    pipeline_status: dict[str, Any],
    sentiment_available: bool,
    portfolio: dict[str, Any],
) -> dict[str, Any]:
    guardrails = _cockpit_guardrail_summary()
    # Zero-cloud: every panel is served by the shared local llama-server.
    local_model = os.getenv(
        "SUPEREZIO_PRIMARY_MODEL",
        os.getenv("SUPEREZIO_DEEPSEEK_MODEL", "Qwen3.8-27B-Q4_K_M"),
    )
    ceo_online = pipeline_status.get("status") in {"ok", "ready"} or bool(
        pipeline_status.get("mode")
    )
    return {
        "ceo": "online" if ceo_online else "degraded",
        "genie": {
            "status": "online" if sentiment_available else "offline",
            "provider": "local",
        },
        "deep": {
            "status": "online" if ceo_online else "degraded",
            "model": local_model,
        },
        "ibkr": {
            "status": "online" if portfolio.get("connected") else "offline",
            "paper": portfolio.get("paper"),
            "equity": portfolio.get("equity"),
            "positions_count": portfolio.get("positions_count", 0),
            "orders_count": portfolio.get("orders_count", 0),
        },
        "guardrails": guardrails,
        "kill_switch": {"state": "ARMED", "armed": True},
        "primary_model": local_model,
    }


def _remember_cockpit_event(request: Request, event: dict[str, Any]) -> None:
    event_type = event.get("type")
    if event_type == "MATH_REPORT":
        request.app.state.last_math_report = _as_jsonable(event)
    elif event_type == "EXPERT_DONE":
        experts = list(getattr(request.app.state, "last_expert_verdicts", []))
        experts.append(_as_jsonable(event))
        request.app.state.last_expert_verdicts = experts[-12:]
    elif event_type == "TRINITY_DELIBERATION":
        request.app.state.last_trinity_report = _as_jsonable(event)


def _is_what_happened_query(message: str) -> bool:
    clean = message.strip().lower().rstrip("?").strip()
    return clean in {
        "o que houve",
        "what happened",
        "why",
        "bug",
        "what went wrong",
    }


def _extract_complex_intent(content: str) -> str | None:
    intents = [
        "MACRO_THESIS",
        "PERSONAL_FINANCE",
        "CAPITAL_ALLOCATION",
        "ASSET_ALLOCATION",
        "REAL_ESTATE_VS_MARKETS",
        "BUSINESS_CAPITAL",
        "FRAUD_RISK",
        "EDUCATION_INVESTMENT",
    ]
    match = re.search(
        r"Question\s+Classification.*?(?:" + "|".join(intents) + ")", content, re.IGNORECASE
    )
    if match:
        matched_text = match.group(0).upper()
        for intent in intents:
            if intent in matched_text:
                return intent
    for intent in intents:
        if re.search(rf"\b{intent}\b", content[:1000], re.IGNORECASE):
            return intent
    return None


def _is_advisory_scanner_violation(
    *,
    route_used: str,
    detected_intent: str,
    scanner_invoked: bool,
) -> bool:
    """Return true only when a true advisory path used the market scanner."""
    if not scanner_invoked:
        return False
    route = (route_used or "").strip().lower()
    intent = (detected_intent or "").strip().lower()
    return route in _ADVISORY_TRACE_ROUTES or intent in _ADVISORY_TRACE_INTENTS


VAGUE_FINANCIAL_RESPONSE = (
    "Para anÃ¡lise financeira, informe pelo menos um ativo/ticker, o prazo desejado "
    "(ex.: ENB.TO 14 dias, tendÃªncia, risco, valuation, notÃ­cias)."
)


def _build_no_empty_fallback_chunk(
    *,
    message: str,
    route_used: str,
    detected_intent: str,
    scanner_invoked: bool,
    agent_called: bool,
    candidate_count: int,
    rejected_count: int,
    rejection_line: str,
    provider_error: str | None,
    selected_ui_ticker: str,
) -> str:
    """Build a useful answer when the pipeline emitted no final content."""
    lower = (message or "").lower()
    ticker = selected_ui_ticker or detect_ticker(message) or "the requested ticker"

    # A missing final chunk is a pipeline failure, not a request-quality verdict.
    header = (
        "A pipeline terminou sem publicar uma resposta final. "
        "Isto Ã© uma falha interna de sÃ­ntese, nÃ£o falta de detalhe no teu pedido.\n\n"
    )
    is_etf_comparison = (
        any(word in lower for word in ("compare", "comparison", " vs ", "versus"))
        and sum(1 for symbol in ("voo", "vti", "schd") if symbol in lower) >= 2
    )

    if (route_used == "market_scan" or scanner_invoked) and candidate_count > 0:
        body = (
            f"O scan aprovou {candidate_count} candidato(s) e rejeitou {rejected_count}, "
            "mas o agente falhou antes de publicar a escolha validada. "
            "Isto nÃ£o Ã© uma rejeiÃ§Ã£o de mercado e nenhuma ordem foi enviada."
        )
        verdict = "Final verdict: WAIT_SYSTEM_ERROR"
        suggestion = (
            "Suggestion: retry the same request after the pipeline is healthy; "
            "do not loosen the scan gates."
        )
    elif route_used == "market_scan" or scanner_invoked:
        body = (
            "The scan path did not return a validated final candidate. I will not invent a trade. "
            f"Candidates passed: {candidate_count}; rejected: {rejected_count}; top reasons: {rejection_line}. "
            "Use REJECT_ALL unless a candidate has verified price, liquidity, catalyst, risk, and invalidation."
        )
        verdict = "Final verdict: REJECT_ALL"
        suggestion = "Suggestion: tighten universe, liquidity floor, catalyst window, or provide candidate tickers."
    elif is_etf_comparison:
        body = (
            "ETF comparison fallback: VOO is S&P 500 large-cap exposure, VTI is total US market exposure, "
            "and SCHD is dividend-quality/value-tilted equity exposure. For most long-term buy-and-hold investors, "
            "pick one core US equity fund instead of stacking overlapping funds. VTI is the broadest core choice; "
            "VOO is fine if you specifically want large-cap S&P 500 exposure; SCHD is a satellite for dividend tilt, not a full-market core."
        )
        verdict = "Final verdict: ETF"
        suggestion = "Suggestion: choose one core ETF first, then add SCHD only if dividend tilt is intentional."
    elif route_used == "ticker_analysis":
        if "concentrated" in lower or "40%" in lower or "40 percent" in lower:
            body = (
                f"{ticker} concentration fallback: a 40 percent single-stock weight is portfolio risk, even for a blue-chip. "
                "Do not sell blindly, but cap new exposure, route new money to diversified assets, and reduce concentration gradually "
                "with tax-aware tranches. Require a tax plan before realizing large gains."
            )
        elif "invalidate" in lower or "invalidation" in lower:
            body = (
                f"{ticker} invalidation fallback: a bullish short-term thesis is invalidated if price loses the prior support zone, "
                "volume expands on down days, relative strength breaks versus the market, or the catalyst/risk event changes the thesis. "
                "Use WAIT until current chart data confirms support, resistance, and trend."
            )
        else:
            body = (
                f"The ticker route was selected for {ticker}, but the pipeline did not return enough verified content. "
                "Treat this as WAIT, not a buy signal. Before acting, require current price, volume/liquidity, trend, "
                "next catalyst, downside risk, and a written invalidation level."
            )
        verdict = "Final verdict: WAIT"
        suggestion = (
            f"Suggestion: retry '{ticker} 14-day analysis with price, volume, RSI, "
            "support, resistance, and catalyst.'"
        )
    elif "credit card" in lower or "19 percent" in lower or "19%" in lower:
        body = (
            "With high-interest debt, the clean default is to pay debt before taking market risk. "
            "A 19 percent credit-card balance is a guaranteed drag; beating that after tax and risk "
            "is unrealistic for a normal portfolio."
        )
        verdict = "Final verdict: PAY_DEBT"
        suggestion = "Suggestion: pay the high-interest balance first, then rebuild emergency cash before ETF contributions."
    elif "capital_allocation" in detected_intent.lower() or (
        "allocate" in lower and any(term in lower for term in ("cash", "debt", "etf", "portfolio"))
    ):
        body = (
            "Scope note: this is an educational framework, not personalized financial advice. "
            "Capital allocation fallback: use illustrative assumptions, not forecasts. "
            "First keep 3-6 months of emergency cash reserve. Then pay debt above a 6-8 percent interest gate. "
            "Only fund side-business equipment when there is documented demand, clear payback, and time-to-cashflow evidence. "
            "Use TFSA, RRSP, RESP, or FHSA choices based on the individual's tax situation. "
            "Illustrative allocation: 40 percent emergency reserve, 30 percent high-interest debt payoff, "
            "15 percent broad diversified ETF exposure, 10 percent business/education only with payback evidence, "
            "5 percent learning/risk budget."
        )
        verdict = "Final verdict: WAIT"
        suggestion = "Suggestion: fill in debt rate, monthly expenses, emergency balance, and registered-account room."
    elif "fax" in lower:
        body = (
            "Fax industry fallback: pure fax is structurally declining. The better thesis is not fax hardware or legacy fax service; "
            "it is secure document workflow, e-signature, healthcare/legal compliance automation, audit trails, and AI document intelligence. "
            "Do not start with a ticker until the replacement workflow and growth economics are clear."
        )
        verdict = "Final verdict: WAIT"
        suggestion = "Suggestion: research digital document workflow and compliance adjacencies before scanning stocks."
    elif "cad 50" in lower or "lottery" in lower or "risk lab" in lower:
        body = (
            "CAD 50 risk-lab fallback: treat this as a controlled experiment, not investing capital. "
            "Max loss is CAD 50 per week. No leverage, no options, no revenge trades. Every attempt needs thesis, liquidity, entry, stop, target, and post-mortem. "
            "If there is no verifiable edge, the correct action is no bet this week."
        )
        verdict = "Final verdict: WAIT"
        suggestion = "Suggestion: ask for a scan only after naming momentum, mean-reversion, or catalyst criteria."
    elif "dividend" in lower or "passive income" in lower:
        body = (
            "Dividend fallback: for a Canadian investor, prioritize dividend durability, diversification, account placement, and tax treatment over headline yield. "
            "Use Canadian-listed dividend ETFs or high-quality Canadian dividend names as research candidates, keep single-stock weights small, and verify payout ratio, debt, dividend growth, and valuation."
        )
        verdict = "Final verdict: ETF"
        suggestion = "Suggestion: screen Canadian dividend exposure by yield sustainability, MER, holdings, payout ratio, and account type."
    elif "dollar-cost" in lower or "dca" in lower or "wait for a correction" in lower:
        body = (
            "DCA fallback: default to dollar-cost averaging instead of waiting for a perfect correction. "
            "Use scheduled tranches, keep emergency cash separate, and only accelerate buying if valuation, cash stability, and risk tolerance all support it. "
            "Waiting requires a written trigger; otherwise it becomes market-timing drift."
        )
        verdict = "Final verdict: ETF"
        suggestion = "Suggestion: split the amount into 4-12 scheduled tranches and define what would pause or accelerate deployment."
    elif "mutual fund" in lower or "etf" in lower:
        body = (
            "ETF vs mutual fund framework: ETFs usually win on low cost, transparency, intraday liquidity, "
            "and tax efficiency. Mutual funds can still be useful for automatic contributions, advisor-managed "
            "plans, or niche mandates. For a beginner, prefer broad low-cost diversified exposure before specialty products."
        )
        verdict = "Final verdict: ETF"
        suggestion = "Suggestion: compare MER, holdings, tracking index, account type, and trading costs before choosing."
    elif "sell everything" in lower or "go to cash" in lower or "markets are falling" in lower:
        body = (
            "Do not sell everything only because markets are falling. Use gates: emergency cash, time horizon, debt, "
            "job risk, portfolio concentration, and whether your thesis changed. If liquidity is safe and the horizon "
            "is long, panic selling usually damages compounding."
        )
        verdict = "Final verdict: WAIT"
        suggestion = "Suggestion: rebalance only if your risk limit or cash need changed; otherwise use staged DCA."
    else:
        body = (
            "I can still give a useful framework from the available context. Start with objective, time horizon, "
            "liquidity need, risk capacity, and what data is missing. Use tools only when current market evidence "
            "or a named ticker is required."
        )
        verdict = "Final verdict: WAIT"
        suggestion = "Suggestion: state the goal, horizon, amount, and whether you want framework, ticker analysis, or a scan."

    error_line = f"\nprovider_error: {provider_error}" if provider_error else ""
    trace_line = (
        f"\nroute: {route_used or 'unknown'}\ndetected_intent: {detected_intent or 'unknown'}\n"
    )
    return f"{header}{body}\n{verdict}\n{suggestion}{trace_line}{error_line}"


# ---------------------------------------------------------------------------
# Chart data
# ---------------------------------------------------------------------------


VALID_TIMEFRAMES = frozenset({"1D", "1W", "1M", "3M", "6M", "1Y", "5Y"})

SSE_REFRESH_INTERVAL: dict[str, int] = {
    "1D": 2,
    "1W": 3,
    "1M": 5,
    "3M": 10,
    "6M": 15,
    "1Y": 30,
    "5Y": 30,
}


def _sanitize_ticker(raw: str) -> str:
    clean_ticker = re.sub(r"[^\w.\-\^]", "", raw).upper()
    if not clean_ticker or clean_ticker.strip("_") == "HEARTBEAT":
        raise HTTPException(status_code=400, detail="Ticker invalido")
    return clean_ticker


def _parse_candle_time(raw: str) -> int:
    """Converte timestamp string do provider para Unix epoch (segundos)."""
    from datetime import datetime

    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
        try:
            return int(datetime.strptime(raw, fmt).timestamp())
        except ValueError:
            continue
    return 0


def _build_ohlcv(candles: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Normaliza candles de qualquer provider para o formato do frontend."""
    ohlcv: list[dict[str, Any]] = []
    for c in candles:
        t_raw = c.get("time", "")
        t = int(t_raw) if isinstance(t_raw, (int, float)) else _parse_candle_time(str(t_raw))
        ohlcv.append(
            {
                "time": t,
                "open": round(float(c["open"]), 4),
                "high": round(float(c["high"]), 4),
                "low": round(float(c["low"]), 4),
                "close": round(float(c["close"]), 4),
                "volume": int(c.get("volume", 0)),
            }
        )
    return ohlcv


@router.get("/api/chart-data/{ticker}")
async def get_chart_data(
    ticker: str,
    timeframe: str = Query("6M", pattern="^(1D|1W|1M|3M|6M|1Y|5Y)$"),
) -> dict:
    """Retorna OHLCV + indicadores tecnicos para renderizar charts â€” via DataHub."""
    clean_ticker = _sanitize_ticker(ticker)

    # DataHub methods are synchronous (requests-based). Run them in a worker
    # thread (so a slow provider cannot stall the event loop) AND bound each call
    # with a timeout — a hanging/saturated provider (or contention with Bob's
    # background scans) must fail fast instead of hanging the browser request.
    try:
        result = await asyncio.wait_for(
            asyncio.to_thread(hub.get_candles, clean_ticker, timeframe=timeframe),
            timeout=10.0,
        )
    except asyncio.TimeoutError:
        raise HTTPException(
            status_code=504, detail=f"DataHub candles timeout (>10s) for {clean_ticker}"
        )
    if "error" in result:
        attempts = result.get("attempts", [])
        detail = result["error"] if not attempts else str(attempts)
        raise HTTPException(status_code=502, detail=f"DataHub: {detail}")

    candles = result.get("candles", [])
    if not candles:
        raise HTTPException(status_code=404, detail=f"Sem dados para {clean_ticker}")

    # Profile is best-effort: bound it so a hanging profile provider never stalls
    # the chart response (candles already succeeded above).
    try:
        profile_result = await asyncio.wait_for(
            asyncio.to_thread(hub.get_profile, clean_ticker), timeout=5.0
        )
    except asyncio.TimeoutError:
        logger.warning("Profile lookup timed out (>5s) for %s — using fallback", clean_ticker)
        profile_result = {"error": "profile_timeout"}
    if "error" in profile_result:
        logger.warning(
            "Profile lookup failed for %s: %s",
            clean_ticker,
            profile_result.get("error"),
        )
        info: dict[str, Any] = {"name": clean_ticker}
    else:
        info = {
            "name": profile_result.get("name") or clean_ticker,
            "sector": profile_result.get("sector"),
            "currency": profile_result.get("currency", "USD"),
            "exchange": profile_result.get("exchange"),
            "market_cap": profile_result.get("market_cap"),
        }

    ohlcv = _build_ohlcv(candles)

    closes = [c["close"] for c in ohlcv]
    times = [c["time"] for c in ohlcv]

    def _series(values):
        return [{"time": t, "value": v} for t, v in zip(times, values) if v is not None]

    current_price = closes[-1] if closes else None
    prev_close = closes[-2] if len(closes) > 1 else closes[0] if closes else None
    change = None
    change_pct = None
    if current_price is not None and prev_close is not None and prev_close != 0:
        change = round(current_price - prev_close, 4)
        change_pct = round((change / prev_close) * 100, 2)

    macd_data = calc_macd(closes)
    bb = calc_bollinger(closes)
    return {
        "ticker": clean_ticker,
        "timeframe": timeframe,
        "profile": info,
        "price": {
            "current": current_price,
            "previous_close": prev_close,
            "change": change,
            "change_pct": change_pct,
        },
        "ohlcv": ohlcv,
        "indicators": {
            "sma20": _series(calc_sma(closes, 20)),
            "sma50": _series(calc_sma(closes, 50)),
            "ema20": _series(calc_ema(closes, 20)),
            "rsi": _series(calc_rsi(closes)),
            "macd": _series(macd_data["macd"]),
            "macd_signal": _series(macd_data["signal"]),
            "macd_histogram": _series(macd_data["histogram"]),
            "bb_upper": _series(bb["upper"]),
            "bb_middle": _series(bb["middle"]),
            "bb_lower": _series(bb["lower"]),
        },
    }


@router.get("/api/chart-sse/{ticker}")
async def stream_chart_data(
    ticker: str,
    request: Request,
    timeframe: str = Query("1D", pattern="^(1D|1W|1M|3M|6M|1Y|5Y)$"),
    refresh_s: int = Query(3, ge=1, le=30),
    max_points: int = Query(180, ge=30, le=500),
):
    """SSE de velas em tempo real (polling) para painel live â€” via DataHub."""

    clean_ticker = _sanitize_ticker(ticker)
    default_refresh = SSE_REFRESH_INTERVAL.get(timeframe, 3)
    effective_refresh = max(refresh_s, default_refresh)

    async def _event_gen():
        last_sig = ""
        first_snapshot = True

        while True:
            if await request.is_disconnected():
                break

            try:
                result = await asyncio.to_thread(hub.get_candles, clean_ticker, timeframe=timeframe)
                if "error" in result:
                    yield {
                        "event": "error",
                        "data": json.dumps(
                            {
                                "ticker": clean_ticker,
                                "detail": str(
                                    result.get("error") or result.get("attempts", "Unknown")
                                ),
                                "timeframe": timeframe,
                            }
                        ),
                    }
                else:
                    all_candles = _build_ohlcv(result.get("candles", []))
                    ohlcv = (
                        all_candles[-max_points:] if len(all_candles) > max_points else all_candles
                    )
                    if not ohlcv:
                        yield {
                            "event": "error",
                            "data": json.dumps(
                                {
                                    "ticker": clean_ticker,
                                    "detail": "Sem dados de vela para o ticker/timeframe.",
                                    "timeframe": timeframe,
                                }
                            ),
                        }
                    else:
                        latest = ohlcv[-1]
                        signature = (
                            f"{latest['time']}:{latest['close']}:{latest['volume']}:{len(ohlcv)}"
                        )

                        if first_snapshot:
                            payload = {
                                "ticker": clean_ticker,
                                "timeframe": timeframe,
                                "server_ts": int(time.time()),
                                "ohlcv": ohlcv,
                                "latest": latest,
                            }
                            yield {"event": "snapshot", "data": json.dumps(payload)}
                            first_snapshot = False
                        elif signature != last_sig:
                            payload = {
                                "ticker": clean_ticker,
                                "timeframe": timeframe,
                                "server_ts": int(time.time()),
                                "latest": latest,
                                "tail": ohlcv[-5:],
                            }
                            yield {"event": "candle", "data": json.dumps(payload)}

                        last_sig = signature

            except Exception as exc:
                yield {
                    "event": "error",
                    "data": json.dumps(
                        {
                            "ticker": clean_ticker,
                            "detail": str(exc)[:300],
                            "timeframe": timeframe,
                        }
                    ),
                }

            yield {
                "event": "heartbeat",
                "data": json.dumps({"ts": int(time.time()), "ticker": clean_ticker}),
            }
            await asyncio.sleep(effective_refresh)

    return EventSourceResponse(_event_gen(), ping=15)


PRODUCT_MANIFEST = {
    "product_name": "SuperEzio",
    "positioning": "Financial copilot with one pipeline, verifiable evidence, and risk guardrails.",
    "operating_principles": [
        "Evidence-based analysis, never a buy or sell order.",
        "Current financial numbers must come from collected sources with evidence_id.",
        "Missing data blocks strong conclusions and favors STUDY_MORE or WAIT.",
        "Fraud/manipulation patterns are treated as red flags, never accusations.",
        "The final verdict must show conflicts, missing data, and the permitted next step.",
    ],
    "safe_actions": ["STUDY_MORE", "WATCHLIST", "WAIT", "SMALL_POSITION", "AVOID"],
    "committee": {
        "fast_mode": {
            "label": "Family Investor Committee",
            "agent_count": 7,
            "roles": [
                "Orchestrator",
                "Education Agent",
                "Company Analyst",
                "ETF Portfolio Agent",
                "Risk Officer",
                "Devils Advocate",
                "Decision Journal Agent",
            ],
        },
        "full_mode": {
            "label": "Institutional Committee",
            "agent_count": 4,
            "roles": [
                "Macro & Risk Analyst",
                "Fundamental & Value Analyst",
                "Momentum & Technical Analyst",
                "Contrarian & Opportunity Analyst",
            ],
        },
    },
    "penny_guardrail": {
        "label": "PennyLab Guardrail",
        "agent_count": 5,
        "mode": "optional",
        "description": (
            "Optional forensic layer for penny-stock workflows. It does not "
            "replace the 4-expert institutional committee."
        ),
        "roles": [
            "Fraud Hunter",
            "Flow Analyst",
            "Ruin Calculator",
            "Sentiment Detective",
            "Market Context",
        ],
    },
    "workflow": [
        {
            "id": "orchestrator_primary",
            "label": "Orchestrator",
            "description": "Orchestrator classifies route, ticker, and data needs.",
        },
        {
            "id": "data",
            "label": "Evidence",
            "description": "Collects price, fundamentals, technicals, news, risk, and memory when available.",
        },
        {
            "id": "experts_4",
            "label": "4 Experts",
            "description": "Experts analyze the same data under an anti-guessing contract.",
        },
        {
            "id": "agent_primary",
            "label": "Bob Core Agent",
            "description": "Local Bob core via llama.cpp + F51 LoRA consolidates conflicts and chooses one permitted next step.",
        },
    ],
    "decision_modes": [
        "Ticker analysis",
        "Decision diary",
        "Market research",
        "Watchlist",
        "Decision history",
    ],
}

# Regex para detectar tickers em mensagens do usuÃ¡rio
_TICKER_RE = re.compile(
    r"\b([A-Z]{1,5}(?:34|4|3|11)?\.(?:SA|TO|V))\b"  # BR/CA: PETR4.SA, RY.TO
    r"|\b([A-Z]{1,5})\b"  # US symbols, for example MSFT
)

_SMALLTALK_RE = re.compile(
    r"^\s*(?:"
    r"hi|hello|hey|yo|sup|"
    r"oi|ola|olÃ¡|e ai|e aÃ­|"
    r"bom dia|boa tarde|boa noite|"
    r"tudo bem|como vai|who are you|quem e voce|quem Ã© vocÃª"
    r")(?:[!.?\s]+)?$",
    re.IGNORECASE,
)

_CHART_CONTEXT_HINTS = (
    "grafico",
    "grÃ¡fico",
    "chart",
    "candle",
    "candles",
    "vela",
    "velas",
    "ohlcv",
    "suporte",
    "resistencia",
    "resistÃªncia",
    "trend",
    "tendencia",
    "tendÃªncia",
    "price action",
    "rsi",
    "macd",
    "sma",
    "ema",
    "volume",
    "bollinger",
    "rompimento",
    "pullback",
    "setup",
    "entry",
    "stop",
    "target",
    "alvo",
    "indicador",
    "indicator",
    "esta acao",
    "esta aÃ§Ã£o",
    "essa acao",
    "essa aÃ§Ã£o",
    "esse ativo",
    "este ativo",
    "this stock",
    "this asset",
    "this ticker",
    "this chart",
    "current chart",
    "current stock",
    "ticker atual",
    "ativo atual",
    "ativo na tela",
    "na tela",
    "no grafico",
    "no grÃ¡fico",
    "que voce ve",
    "que vocÃª vÃª",
    "olhando isso",
    "olhando o grafico",
    "olhando o grÃ¡fico",
)


_MAX_MESSAGE_CHARS = 8_000
_MAX_CHART_CONTEXT_CHARS = 20_000
_SECRET_ENV_MARKERS = ("KEY", "TOKEN", "SECRET", "PASSWORD")


def _safe_error_detail(exc: Exception) -> str:
    detail = str(exc) or exc.__class__.__name__
    for key, value in os.environ.items():
        if (
            value
            and len(value) >= 8
            and any(marker in key.upper() for marker in _SECRET_ENV_MARKERS)
        ):
            detail = detail.replace(value, "[REDACTED]")
    return detail[:500]


_FALSE_NO_CHART_DATA_PATTERNS = (
    r"\bnao\s+(?:ha|tenho|tem)\s+(?:preco|grafico|dados|metricas)\b",
    r"\bsem\s+(?:preco|grafico|dados\s+de\s+preco|dados\s+do\s+grafico|metricas)\b",
    r"\bno\s+(?:price|chart|market\s+data|ohlcv|candles|metrics)\b",
    r"\bwithout\s+(?:price|chart|market\s+data|ohlcv|candles|metrics)\b",
)


def _ascii_lower(text: str) -> str:
    import unicodedata

    normalized = unicodedata.normalize("NFKD", text or "")
    return "".join(ch for ch in normalized if not unicodedata.combining(ch)).lower()


def _answer_denies_attached_chart_data(answer: str) -> bool:
    normalized = _ascii_lower(answer)
    return any(re.search(pattern, normalized) for pattern in _FALSE_NO_CHART_DATA_PATTERNS)


def _extract_chart_fact(chart_context: str, label: str) -> str:
    pattern = re.compile(rf"^\s*{re.escape(label)}\s*:\s*(.+?)\s*$", re.IGNORECASE | re.MULTILINE)
    match = pattern.search(chart_context or "")
    return match.group(1).strip() if match else ""


def _build_chart_context_repair_answer(
    *,
    ticker: str,
    chart_context: str,
    raw_message: str,
) -> str:
    ticker = (ticker or _extract_chart_fact(chart_context, "Ticker") or "ticker").upper()
    current_price = _extract_chart_fact(chart_context, "Current price")
    last_close = _extract_chart_fact(chart_context, "Last close")
    change_pct = _extract_chart_fact(chart_context, "Change %")
    data_points = _extract_chart_fact(chart_context, "Data points")
    last_volume = _extract_chart_fact(chart_context, "Last volume")
    rsi = _extract_chart_fact(chart_context, "RSI")
    sma20 = _extract_chart_fact(chart_context, "SMA20")
    sma50 = _extract_chart_fact(chart_context, "SMA50")

    sentiment_match = re.search(r"Sentimento\s*=\s*([^,.;\n]+)", raw_message or "", re.IGNORECASE)
    sentiment = sentiment_match.group(1).strip() if sentiment_match else "nao informado"
    reddit_match = re.search(r"Reddit\s*=\s*([^,.;\n]+)", raw_message or "", re.IGNORECASE)
    reddit = reddit_match.group(1).strip() if reddit_match else "nao informado"

    facts = [
        f"preco atual {current_price}" if current_price else "",
        f"ultimo close {last_close}" if last_close else "",
        f"variacao {change_pct}" if change_pct else "",
        f"{data_points} candles" if data_points else "",
        f"volume ultimo candle {last_volume}" if last_volume else "",
        f"RSI {rsi}" if rsi else "",
        f"SMA20 {sma20}" if sma20 else "",
        f"SMA50 {sma50}" if sma50 else "",
    ]
    fact_line = "; ".join(item for item in facts if item) or "chart_context anexado"

    return (
        f"Correcao operacional: {ticker} tem chart_context anexado, entao nao vou tratar "
        f"como falta de dados. Dados usados: {fact_line}. Sentimento Vivo: {sentiment}; "
        f"Reddit: {reddit}.\n\n"
        "Tese: leitura de espera. Sem impulso social relevante, a decisao depende do grafico "
        "e de confirmacao por volume, nao de narrativa.\n\n"
        "Risco: liquidez e falso rompimento. Se o volume continuar fraco ou o candle perder "
        "suporte recente, nao ha setup limpo.\n\n"
        "Invalidacao: perda do ultimo close/suporte relevante com volume crescente, ou noticia "
        "fraca acompanhada de spike promocional.\n\n"
        "Acao: WAIT. Para virar trade, primeiro executar coleta/experts/guardrails e somente "
        "depois emitir PAPER_TICKET com entrada, alvo e stop numericos."
    )


def _should_include_chart_context(raw_message: str, detected_ticker: str) -> bool:
    """Decide se o chart_context deve influenciar a resposta.

    Regras:
    - Se o usuario falou um ticker explicitamente, pode anexar.
    - Small talk/greetings nunca devem herdar o ativo atual do grafico.
    - Sem ticker explicito, so anexamos se a mensagem parecer de analise
      tecnica/financeira ou fizer referencia ao grafico/ativo atual.
    """
    message = (raw_message or "").strip()
    if not message:
        return False
    if detected_ticker:
        return True
    if _SMALLTALK_RE.match(message):
        return False

    return has_hint(message, _CHART_CONTEXT_HINTS)


def _get_pipeline(request: Request):
    pipeline = getattr(request.app.state, "pipeline", None)
    if not pipeline:
        raise HTTPException(status_code=500, detail="Brain not initialized (Pipeline missing)")
    return pipeline


@router.post("/task/submit")
async def submit_task(envelope: A2AMessage, request: Request) -> StreamingResponse:
    """Submit a task to the pipeline and stream NDJSON updates."""
    logger.info("Received task: %s from %s", envelope.type, envelope.from_agent)

    if envelope.type != MessageType.TASK_SUBMIT:
        raise HTTPException(status_code=400, detail="Invalid message type for this endpoint")

    # â”€â”€ Task Queue: evita probe preso, 1 task ativa por sessÃ£o â”€â”€
    from core.pipeline.task_queue import get_task_queue

    tq = get_task_queue()
    session_id_raw = (
        (envelope.payload or {}).get("session_id") if isinstance(envelope.payload, dict) else ""
    )
    task = tq.submit(message=str(envelope.payload), session_id=str(session_id_raw))
    if task is None:
        active = tq.active_for_session(str(session_id_raw))
        raise HTTPException(
            status_code=429,
            detail={
                "code": "active_task",
                "message": "Bob is already processing another request for this session. Wait for it to finish or cancel it.",
                "run_id": active.run_id if active else "",
                "session_id": str(session_id_raw),
                "elapsed": round(active.elapsed, 3) if active else 0,
            },
        )

    try:
        payload = envelope.payload if isinstance(envelope.payload, dict) else {}
        raw_message = (
            payload.get("message") or payload.get("task_description") or str(envelope.payload or "")
        )
        if not isinstance(raw_message, str):
            raw_message = str(raw_message)
        if len(raw_message) > _MAX_MESSAGE_CHARS:
            raise HTTPException(
                status_code=413,
                detail=f"Message too large. Limit is {_MAX_MESSAGE_CHARS} characters.",
            )
        prompt = raw_message
        session_id = payload.get("session_id") or envelope.from_agent or "default"
        memory_mode = payload.get("memory_mode") or "relevant_all"
        rigor = payload.get("rigor") or "strict"

        if _SMALLTALK_RE.match(raw_message):
            greeting = "Oi! Bob está online. Como posso ajudar?"
            trace = {
                "user_query": raw_message,
                "detected_intent": "general_question",
                "selected_ui_ticker": "",
                "chart_context_attached": False,
                "route_used": "general",
                "scanner_invoked": False,
                "agent_called": False,
                "fallback_used": False,
                "final_content_length": len(greeting),
            }
            _session_history[session_id] = {
                "detected_intent": "general_question",
                "failed": False,
            }

            async def stream_smalltalk() -> AsyncGenerator[str, None]:
                try:
                    yield (
                        json.dumps(
                            {
                                "type": "STREAM_START",
                                "msg_id": envelope.msg_id,
                                "run_id": task.run_id,
                            }
                        )
                        + "\n"
                    )
                    yield (
                        json.dumps(
                            {
                                "type": "INTENT_CLASSIFIED",
                                "intent": "general_question",
                                "route": "general",
                            }
                        )
                        + "\n"
                    )
                    yield (
                        json.dumps({"type": "CHUNK", "content": greeting}, ensure_ascii=False)
                        + "\n"
                    )
                    request.app.state.last_decision_trace = trace
                    yield (
                        json.dumps({"type": "STREAM_END", "trace": trace, "run_id": task.run_id})
                        + "\n"
                    )
                finally:
                    tq.complete(task.run_id)

            return StreamingResponse(stream_smalltalk(), media_type="application/x-ndjson")

        pipeline = _get_pipeline(request)
        chart_context = str(payload.get("chart_context") or "")
        if len(chart_context) > _MAX_CHART_CONTEXT_CHARS:
            chart_context = chart_context[:_MAX_CHART_CONTEXT_CHARS]

        session_meta = _session_history.get(session_id) or {}
        trade_order_context = dict(session_meta.get("trade_order_context") or {})

        # Inject previously recommended tickers as excluded for follow-up requests
        prev_recs = list(session_meta.get("recommended_tickers") or [])
        if prev_recs:
            excluded = list(trade_order_context.get("excluded_tickers") or [])
            for t in prev_recs:
                if t.upper() not in excluded:
                    excluded.append(t.upper())
            if excluded:
                trade_order_context["excluded_tickers"] = excluded

        # Intercept "o que houve" query if the previous request failed
        if _is_what_happened_query(raw_message):
            prev_run = _session_history.get(session_id)
            if prev_run and prev_run.get("failed"):
                prev_intent = prev_run.get("detected_intent", "unknown")
                explanation = (
                    f"The previous request failed to produce valid content. "
                    f"It was classified as {prev_intent}. "
                    f"No market scanner should have been used. "
                    f"Check runtime logs."
                )

                # Update session history to mark this query as succeeded
                _session_history[session_id] = {
                    "detected_intent": "WHAT_HAPPENED_INTERCEPT",
                    "failed": False,
                }

                async def stream_intercepted() -> AsyncGenerator[str, None]:
                    try:
                        yield (
                            json.dumps(
                                {
                                    "type": "STREAM_START",
                                    "msg_id": envelope.msg_id,
                                    "run_id": task.run_id,
                                }
                            )
                            + "\n"
                        )
                        yield (
                            json.dumps(
                                {"type": "CHUNK", "content": explanation}, ensure_ascii=False
                            )
                            + "\n"
                        )
                        trace = {
                            "user_query": raw_message,
                            "detected_intent": "WHAT_HAPPENED_INTERCEPT",
                            "selected_ui_ticker": "",
                            "chart_context_attached": False,
                            "route_used": "general",
                            "scanner_invoked": False,
                            "agent_called": False,
                            "fallback_used": False,
                            "final_content_length": len(explanation),
                        }
                        logger.info("Bob Response Trace (Intercepted): %s", json.dumps(trace))
                        request.app.state.last_decision_trace = trace
                        yield (
                            json.dumps(
                                {"type": "STREAM_END", "trace": trace, "run_id": task.run_id}
                            )
                            + "\n"
                        )
                    finally:
                        tq.complete(task.run_id)

                return StreamingResponse(stream_intercepted(), media_type="application/x-ndjson")

        # Ticker from UI field takes priority; fall back to message text detection
        is_broker_status = detect_broker_status_intent(raw_message)
        explicit_ticker = "" if is_broker_status else str(payload.get("ticker") or "").strip()
        detected_ticker = "" if is_broker_status else explicit_ticker or detect_ticker(raw_message)

        # Hard block context leak for advisory / scan intents.
        # - Complex finance / capital allocation: chart context must never leak.
        # - Market scan: UI ticker must not hijack routing away from the scanner.
        #   The user asked to FIND stocks, not to analyze the chart ticker.
        is_complex = detect_complex_finance_intent(raw_message)
        is_capital_alloc = detect_capital_allocation_intent(raw_message)
        is_market_scan = detect_market_scan_intent(raw_message)
        is_paper_training = detect_decisive_trade_intent(raw_message)
        if is_broker_status or is_complex or is_capital_alloc:
            explicit_ticker = ""
            detected_ticker = ""
            chart_context = ""
            context_block = ""
            block_vague_financial = False
        elif (
            (is_market_scan or is_paper_training)
            and explicit_ticker
            and not detect_ticker(raw_message)
        ):
            # Market scan request with a chart ticker but no inline ticker:
            # the chart ticker is stale context, not the scan target.
            # Zero it so parse_user_intent routes to market_scan, not ticker_analysis.
            explicit_ticker = ""
            detected_ticker = detect_ticker(raw_message)
            chart_context = ""
            context_block = ""
            block_vague_financial = False
        else:
            block_vague_financial = should_block_vague_financial_prompt(
                raw_message,
                detected_ticker,
                rigor,
            )

            # Inject chart context only when the user is actually asking
            # about the chart / current asset / financial analysis.
            context_block = ""
            if (
                chart_context
                and not block_vague_financial
                and _should_include_chart_context(raw_message, detected_ticker)
            ):
                context_block = (
                    "\n\n[CHART_VISUAL_CONTEXT]\n"
                    f"{chart_context}\n"
                    "The user is viewing this chart now. Use these OHLCV data to "
                    "discuss candle patterns, support, resistance, trends, and any "
                    "relevant technical observation. Be specific about what the candles show. "
                    "Hard contract: because CHART_CONTEXT is attached, do not say there is "
                    "no price, no chart, no candles, no metrics, or no data for this ticker.\n"
                    "[/CHART_VISUAL_CONTEXT]"
                )

        # Trace metadata variables
        user_query = raw_message
        selected_ui_ticker = payload.get("ticker") or ""
        chart_context_attached = bool(context_block)
        try:
            initial_intent = parse_user_intent(
                raw_message,
                rigor=rigor,
                ticker=detected_ticker,
                trade_order_context=trade_order_context or None,
            )
            detected_intent = initial_intent.intent or "unknown"
            route_used = initial_intent.route or "unknown"
        except Exception:
            detected_intent = "unknown"
            route_used = "unknown"
        scanner_invoked = False
        agent_called = False
        fallback_used = False
        final_content_length = 0
        full_content: list[str] = []
        # Scan telemetry surfaced by collector via DATA_COLLECTED events
        candidate_count = 0
        rejected_count = 0
        rejection_summary: dict[str, int] = {}
        provider_sources_used: set[str] = set()
        provider_error: str | None = None

        async def stream_result() -> AsyncGenerator[str, None]:
            nonlocal \
                detected_intent, \
                route_used, \
                scanner_invoked, \
                agent_called, \
                fallback_used, \
                final_content_length
            nonlocal candidate_count, rejected_count, rejection_summary, provider_error
            nonlocal trade_order_context
            current_task = asyncio.current_task()
            if current_task is not None:
                task.bind_execution(current_task)
            buffer_answer_until_validation = chart_context_attached
            answer_repaired = False
            if detected_ticker:
                yield (json.dumps({"type": "CHART_DATA", "ticker": detected_ticker}) + "\n")
            yield (
                json.dumps(
                    {"type": "STREAM_START", "msg_id": envelope.msg_id, "run_id": task.run_id}
                )
                + "\n"
            )

            try:
                if hasattr(pipeline, "stream_events"):
                    async for event in pipeline.stream_events(
                        prompt,
                        context=context_block,
                        session_id=session_id,
                        memory_mode=memory_mode,
                        rigor=rigor,
                        ticker=detected_ticker,
                        trade_order_context=trade_order_context or None,
                    ):
                        if isinstance(event, dict):
                            _remember_cockpit_event(request, event)
                            event_type = event.get("type")
                            if event_type == "INTENT_CLASSIFIED":
                                if event.get("intent"):
                                    detected_intent = event["intent"]
                                if event.get("route"):
                                    route_used = event["route"]
                            elif event_type == "PIPELINE_STEP":
                                step = event.get("step")
                                status = event.get("status")
                                if step == "agent_primary" and status == "started":
                                    agent_called = True
                                elif (
                                    step == "data"
                                    and status == "started"
                                    and (
                                        route_used == "market_scan"
                                        or event.get("route") == "market_scan"
                                    )
                                ):
                                    scanner_invoked = True
                            elif event_type == "DATA_COLLECTED":
                                # Only mark scanner as invoked when the route is
                                # explicitly market_scan.  The presence of
                                # rejected_count alone does not mean a scanner
                                # ran â€” single-ticker collection may also reject
                                # candidates for data-quality reasons.
                                if route_used == "market_scan":
                                    scanner_invoked = True
                                if isinstance(event.get("candidates"), int):
                                    candidate_count = event["candidates"]
                                if isinstance(event.get("rejected_count"), int):
                                    rejected_count = event["rejected_count"]
                                if isinstance(event.get("rejection_summary"), dict):
                                    rejection_summary = event["rejection_summary"]
                                for prov in event.get("providers") or []:
                                    if prov:
                                        provider_sources_used.add(str(prov))
                                # Provider errors are visible via source_errors[]
                                for err in event.get("source_errors") or []:
                                    if isinstance(err, str) and provider_error is None:
                                        provider_error = err[:200]
                            elif event_type == "ERROR":
                                fallback_used = True
                                detail = event.get("detail")
                                if isinstance(detail, str) and provider_error is None:
                                    provider_error = detail[:200]
                            elif event_type == "CHUNK":
                                content = event.get("content", "")
                                final_content_length += len(content)
                                full_content.append(content)
                                if buffer_answer_until_validation:
                                    continue
                            elif event_type == "TRADE_ORDER_CONTEXT":
                                trade_order_context = {
                                    k: v for k, v in event.items() if k != "type" and v is not None
                                }
                            yield json.dumps(event, ensure_ascii=False) + "\n"
                        else:
                            content_str = str(event)
                            final_content_length += len(content_str)
                            full_content.append(content_str)
                            if buffer_answer_until_validation:
                                continue
                            yield (
                                json.dumps(
                                    {"type": "CHUNK", "content": content_str},
                                    ensure_ascii=False,
                                )
                                + "\n"
                            )
                else:
                    chat_iter = pipeline.chat_async(
                        prompt,
                        context=context_block,
                        session_id=session_id,
                        memory_mode=memory_mode,
                        rigor=rigor,
                        ticker=detected_ticker,
                        trade_order_context=trade_order_context or None,
                    )
                    async for chunk in chat_iter:
                        if isinstance(chunk, dict):
                            _remember_cockpit_event(request, chunk)
                            event_type = chunk.get("type")
                            if event_type == "INTENT_CLASSIFIED":
                                if chunk.get("intent"):
                                    detected_intent = chunk["intent"]
                                if chunk.get("route"):
                                    route_used = chunk["route"]
                            elif event_type == "PIPELINE_STEP":
                                step = chunk.get("step")
                                status = chunk.get("status")
                                if step == "agent_primary" and status == "started":
                                    agent_called = True
                                elif (
                                    step == "data"
                                    and status == "started"
                                    and (
                                        route_used == "market_scan"
                                        or chunk.get("route") == "market_scan"
                                    )
                                ):
                                    scanner_invoked = True
                            elif event_type == "DATA_COLLECTED":
                                # Same rationale as the stream_events branch above:
                                # only route=market_scan implies scanner invocation.
                                if route_used == "market_scan":
                                    scanner_invoked = True
                                if isinstance(chunk.get("candidates"), int):
                                    candidate_count = chunk["candidates"]
                                if isinstance(chunk.get("rejected_count"), int):
                                    rejected_count = chunk["rejected_count"]
                                if isinstance(chunk.get("rejection_summary"), dict):
                                    rejection_summary = chunk["rejection_summary"]
                                for prov in chunk.get("providers") or []:
                                    if prov:
                                        provider_sources_used.add(str(prov))
                                for err in chunk.get("source_errors") or []:
                                    if isinstance(err, str) and provider_error is None:
                                        provider_error = err[:200]
                            elif event_type == "ERROR":
                                fallback_used = True
                                detail = chunk.get("detail")
                                if isinstance(detail, str) and provider_error is None:
                                    provider_error = detail[:200]
                            elif event_type == "CHUNK":
                                content = chunk.get("content", "")
                                final_content_length += len(content)
                                full_content.append(content)
                                if buffer_answer_until_validation:
                                    continue
                            yield json.dumps(chunk, ensure_ascii=False) + "\n"
                            continue
                        if isinstance(chunk, str):
                            raw_chunk = chunk.strip()
                            if raw_chunk.startswith("{") and raw_chunk.endswith("}"):
                                try:
                                    event = json.loads(raw_chunk)
                                    if event.get("type") in {"CHART_DATA"}:
                                        yield (json.dumps(event, ensure_ascii=False) + "\n")
                                        continue
                                except json.JSONDecodeError:
                                    pass
                            final_content_length += len(chunk)
                            full_content.append(chunk)
                            if buffer_answer_until_validation:
                                continue
                            yield (
                                json.dumps({"type": "CHUNK", "content": chunk}, ensure_ascii=False)
                                + "\n"
                            )

                # Post-processing answer content for sub-classification if complex
                # finance or capital allocation.
                accumulated_answer = "".join(full_content)
                if is_complex or is_capital_alloc:
                    route_used = "general"
                    sub_intent = _extract_complex_intent(accumulated_answer)
                    if sub_intent:
                        detected_intent = sub_intent
                    elif is_capital_alloc:
                        detected_intent = "CAPITAL_ALLOCATION"
                    elif detected_intent == "unknown" or detected_intent == "general_question":
                        detected_intent = "MACRO_THESIS"  # default complex fallback

                # No Empty Response Rule (OPUS Â§7): backend must never let the
                # frontend render a blank assistant bubble. If the pipeline
                # produced zero content, emit a structured fallback CHUNK with
                # enough trace info for the user to retry usefully.
                if final_content_length == 0 or not accumulated_answer.strip():
                    fallback_used = True
                    top_reasons = sorted(
                        rejection_summary.items(),
                        key=lambda kv: kv[1],
                        reverse=True,
                    )[:3]
                    rejection_line = (
                        ", ".join(f"{r}:{c}" for r, c in top_reasons) if top_reasons else "n/a"
                    )
                    fallback_chunk = _build_no_empty_fallback_chunk(
                        message=raw_message,
                        route_used=route_used,
                        detected_intent=detected_intent,
                        scanner_invoked=scanner_invoked,
                        agent_called=agent_called,
                        candidate_count=candidate_count,
                        rejected_count=rejected_count,
                        rejection_line=rejection_line,
                        provider_error=provider_error,
                        selected_ui_ticker=selected_ui_ticker,
                    )
                    final_content_length = len(fallback_chunk)
                    yield (
                        json.dumps(
                            {"type": "CHUNK", "content": fallback_chunk},
                            ensure_ascii=False,
                        )
                        + "\n"
                    )
                elif buffer_answer_until_validation:
                    if _answer_denies_attached_chart_data(accumulated_answer):
                        answer_repaired = True
                        accumulated_answer = _build_chart_context_repair_answer(
                            ticker=detected_ticker,
                            chart_context=chart_context,
                            raw_message=raw_message,
                        )
                        full_content[:] = [accumulated_answer]
                        final_content_length = len(accumulated_answer)
                    yield (
                        json.dumps(
                            {"type": "CHUNK", "content": accumulated_answer},
                            ensure_ascii=False,
                        )
                        + "\n"
                    )

                quality_score: float | None = None
                quality_score_source: str | None = None
                quality_score_scope: str | None = None
                quality_warnings: list[str] = []
                quality_flagged = False
                if accumulated_answer.strip() and agent_called and not fallback_used:
                    try:
                        score_result = reward_gate.score_with_provenance(accumulated_answer)
                        quality_score = score_result.value
                        quality_score_source = score_result.source
                        quality_score_scope = score_result.scope
                        sanity = sanity_check.verify(raw_message, accumulated_answer)
                        if not sanity.passed:
                            quality_flagged = True
                            quality_warnings = list(sanity.blocks)
                            logger.warning(
                                "Sanity check flagged response: %s",
                                "; ".join(sanity.blocks),
                            )
                        elif quality_score < reward_gate.threshold:
                            quality_flagged = True
                            quality_warnings = [
                                f"reward_score={quality_score:.3f} < {reward_gate.threshold}"
                            ]
                            logger.warning(
                                "Reward gate low score: %.3f < %.2f",
                                quality_score,
                                reward_gate.threshold,
                            )
                        else:
                            quality_warnings = list(sanity.warnings)
                            if quality_warnings:
                                logger.info(
                                    "Sanity warnings: %s",
                                    "; ".join(quality_warnings),
                                )
                    except Exception:
                        logger.exception("ML quality gate error; passing through")

                top_rejection_reasons = [
                    f"{r}:{c}"
                    for r, c in sorted(
                        rejection_summary.items(),
                        key=lambda kv: kv[1],
                        reverse=True,
                    )[:3]
                ]
                # Hard runtime invariant: advisory intents must never invoke
                # the market scanner. Sovereign opportunity searches can keep
                # route=general while intentionally using the scanner, so the
                # guard is based on advisory intent/route, not route=general.
                if _is_advisory_scanner_violation(
                    route_used=route_used,
                    detected_intent=detected_intent,
                    scanner_invoked=scanner_invoked,
                ):
                    logger.warning(
                        "INVARIANT VIOLATION: route=%s intent=%s but scanner_invoked=True. User query: %s",
                        route_used,
                        detected_intent,
                        user_query[:200],
                    )

                trace = {
                    "user_query": user_query,
                    "detected_intent": detected_intent,
                    "selected_ui_ticker": selected_ui_ticker,
                    "chart_context_attached": chart_context_attached,
                    "route_used": route_used,
                    "scanner_invoked": scanner_invoked,
                    "candidate_count": candidate_count,
                    "rejected_count": rejected_count,
                    "top_rejection_reasons": top_rejection_reasons,
                    "agent_called": agent_called,
                    "fallback_used": fallback_used,
                    "final_content_length": final_content_length,
                    "provider_sources_used": sorted(provider_sources_used),
                    "provider_error": provider_error,
                }
                if quality_score is not None:
                    trace["quality_score"] = round(quality_score, 4)
                    trace["quality_score_source"] = quality_score_source
                    trace["quality_score_scope"] = quality_score_scope
                if quality_warnings:
                    trace["quality_warnings"] = quality_warnings
                if quality_flagged:
                    trace["quality_flagged"] = True
                if answer_repaired:
                    trace["answer_repaired"] = True
                    trace["repair_reason"] = "model_denied_attached_chart_context"
                logger.info("Bob Response Trace: %s", json.dumps(trace))
                request.app.state.last_decision_trace = trace

                # Update session history
                session_record: dict[str, Any] = {
                    "detected_intent": detected_intent,
                    "failed": fallback_used,
                }
                if trade_order_context:
                    session_record["trade_order_context"] = trade_order_context

                # Track recommended tickers for exclusion on follow-up requests
                if scanner_invoked and candidate_count > 0 and accumulated_answer:
                    prev_recs = list(session_meta.get("recommended_tickers") or [])
                    match = _RECOMMENDED_TICKER_RE.search(accumulated_answer)
                    if match:
                        rec_ticker = match.group(1).upper()
                        if rec_ticker not in prev_recs:
                            prev_recs.append(rec_ticker)
                    session_record["recommended_tickers"] = prev_recs

                _session_history[session_id] = session_record

                yield (
                    json.dumps({"type": "STREAM_END", "trace": trace, "run_id": task.run_id}) + "\n"
                )
            except asyncio.CancelledError:
                logger.info(
                    "Client disconnected for session=%s msg=%s", session_id, envelope.msg_id
                )
                tq.cancel(task.run_id)
                raise
            except Exception as exc:
                fallback_used = True
                err_detail = _safe_error_detail(exc)
                if provider_error is None:
                    provider_error = err_detail[:200]
                yield (json.dumps({"type": "ERROR", "detail": err_detail}) + "\n")

                # No Empty Response Rule (OPUS Â§7) also applies on exception
                # paths: if nothing reached the user, surface a structured
                # fallback CHUNK so the frontend has something to render.
                if final_content_length == 0:
                    fallback_chunk = (
                        "Bob hit a runtime error while preparing this answer.\n"
                        f"- route: {route_used}\n"
                        f"- detected_intent: {detected_intent}\n"
                        f"- scanner_invoked: {scanner_invoked}\n"
                        f"- agent_called: {agent_called}\n"
                        f"- error: {provider_error or err_detail}\n"
                        "\n"
                        "Suggestion: retry with a narrower question (specific "
                        "ticker or educational framework) so the pipeline can "
                        "route to a smaller, more reliable path."
                    )
                    final_content_length = len(fallback_chunk)
                    yield (
                        json.dumps(
                            {"type": "CHUNK", "content": fallback_chunk},
                            ensure_ascii=False,
                        )
                        + "\n"
                    )

                top_rejection_reasons = [
                    f"{r}:{c}"
                    for r, c in sorted(
                        rejection_summary.items(),
                        key=lambda kv: kv[1],
                        reverse=True,
                    )[:3]
                ]
                trace = {
                    "user_query": user_query,
                    "detected_intent": detected_intent,
                    "selected_ui_ticker": selected_ui_ticker,
                    "chart_context_attached": chart_context_attached,
                    "route_used": route_used,
                    "scanner_invoked": scanner_invoked,
                    "candidate_count": candidate_count,
                    "rejected_count": rejected_count,
                    "top_rejection_reasons": top_rejection_reasons,
                    "agent_called": agent_called,
                    "fallback_used": True,
                    "final_content_length": final_content_length,
                    "provider_sources_used": sorted(provider_sources_used),
                    "provider_error": provider_error,
                }
                logger.info("Bob Response Trace (Error): %s", json.dumps(trace))
                request.app.state.last_decision_trace = trace

                # Update session history
                _session_history[session_id] = {
                    "detected_intent": detected_intent,
                    "failed": True,
                }

                yield (
                    json.dumps({"type": "STREAM_END", "trace": trace, "run_id": task.run_id}) + "\n"
                )
            finally:
                tq.complete(task.run_id)

        return StreamingResponse(stream_result(), media_type="application/x-ndjson")

    except HTTPException:
        tq.complete(task.run_id)
        raise
    except Exception as exc:
        tq.complete(task.run_id)
        raise HTTPException(status_code=500, detail=_safe_error_detail(exc)) from exc


@router.post("/feedback")
async def submit_feedback(payload: dict[str, Any]) -> dict[str, Any]:
    """Save user feedback for a completed response."""
    msg_id = str(payload.get("msg_id", "")).strip()
    comment = str(payload.get("comment", "")).strip()
    try:
        rating = int(payload.get("rating", 0))
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="rating must be 0-5") from None

    if not msg_id:
        raise HTTPException(status_code=400, detail="msg_id is required")
    if len(msg_id) > 120:
        raise HTTPException(status_code=400, detail="msg_id is too long")
    if rating not in (0, 1, 2, 3, 4, 5):
        raise HTTPException(status_code=400, detail="rating must be 0-5")
    if len(comment) > 1000:
        raise HTTPException(status_code=400, detail="comment is too long")

    from core.ml.feedback import save_feedback

    path = save_feedback(msg_id, rating, comment=comment)
    logger.info("Feedback saved: msg_id=%s rating=%s file=%s", msg_id, rating, path.name)
    return {"ok": True}


@router.get("/feedback/stats")
async def get_feedback_stats(days: int = 30) -> dict[str, Any]:
    """Return aggregate feedback statistics."""
    if days < 1 or days > 365:
        raise HTTPException(status_code=400, detail="days must be between 1 and 365")

    from core.ml.feedback import load_recent_feedback

    records = load_recent_feedback(days)
    ratings = [r["rating"] for r in records if 1 <= r.get("rating", 0) <= 5]
    return {
        "total": len(records),
        "avg_rating": round(sum(ratings) / len(ratings), 2) if ratings else 0,
        "distribution": {str(k): sum(1 for r in ratings if r == k) for k in range(1, 6)},
        "days": days,
    }


@router.get("/capabilities")
async def get_capabilities(request: Request) -> dict:
    return {
        "agent": "f51_universal",
        "supported_tasks": [
            "echo",
            "task/submit (pipeline completo)",
            "experts/neural-decision/predict",
            "api/sdca/evaluate",
            "experts/pennylab/predict",
            "data/providers",
        ],
        "brain": "UnifiedPipeline",
        "orchestrator": None,
        "product": PRODUCT_MANIFEST,
    }


@router.get("/product/manifest")
async def product_manifest(request: Request) -> dict:
    """Public product contract consumed by the browser UI."""
    pipeline = getattr(request.app.state, "pipeline", None)
    status = pipeline.get_status() if pipeline else {}
    manifest = dict(PRODUCT_MANIFEST)
    manifest["runtime"] = {
        "brain": "UnifiedPipeline",
        "status": status,
    }
    return manifest


@router.post("/api/sdca/evaluate")
async def evaluate_sdca(candidate: DecisionCandidate) -> dict:
    """Evaluate a candidate decision with SDCA-Lite. Does not execute trades."""

    decision = evaluate_decision_with_sdca(candidate)
    return decision.model_dump(mode="json")


@router.post("/experts/neural-decision/predict")
async def predict_neural_decision(payload: dict) -> dict:
    """Evaluate technical signals and risk regimes via NeuralDecisionExpert."""
    from experts.neural_decision import NeuralDecisionExpert

    symbol = payload.get("symbol", "")
    timeframe = payload.get("timeframe", "")
    features = payload.get("features", {})
    context = payload.get("context", {})

    expert = NeuralDecisionExpert()
    result = expert.predict(symbol, timeframe, features, context)

    if "error" in result:
        raise HTTPException(
            status_code=400,
            detail={
                "error": result["error"],
                "validation_errors": result.get("validation_errors", []),
                "recommendation": result.get("recommendation"),
                "veto": result.get("veto"),
            },
        )

    return result


# -----------------------------------------------------------------
# Evidence Mode - audit trail endpoints
# -----------------------------------------------------------------


@router.get("/evidence/{run_id}")
async def get_evidence(run_id: str) -> dict:
    """List all evidence files for a run."""
    run_dir = _resolve_evidence_run_dir(run_id)

    files = {}
    for f in sorted(run_dir.iterdir()):
        if f.is_file():
            files[f.name] = {
                "size": f.stat().st_size,
                "url": f"/evidence/{run_id}/{f.name}",
            }

    return {"run_id": run_id, "files": files}


@router.get("/evidence/{run_id}/{filename:path}")
async def serve_evidence_file(run_id: str, filename: str):
    """Serve a specific evidence file (HTML, JSON, etc.)."""
    from fastapi.responses import FileResponse, HTMLResponse

    file_path = _resolve_evidence_file(run_id, filename)

    if file_path.suffix.lower() == ".html":
        return HTMLResponse(content=file_path.read_text(encoding="utf-8"))

    return FileResponse(str(file_path))


@router.get("/evidence")
async def list_evidence_runs() -> dict:
    """List all evidence runs."""
    from core.evidence.run import EVIDENCE_DIR

    if not EVIDENCE_DIR.exists():
        return {"runs": []}

    runs = []
    for d in sorted(EVIDENCE_DIR.iterdir(), reverse=True):
        if d.is_dir():
            report = d / "report.html"
            analysis = d / "analysis.json"
            runs.append(
                {
                    "run_id": d.name,
                    "has_report": report.exists(),
                    "has_analysis": analysis.exists(),
                    "url": f"/evidence/{d.name}",
                }
            )

    return {"runs": runs[:50]}  # limit to last 50


@router.get("/cockpit/portfolio")
def get_cockpit_portfolio() -> dict[str, Any]:
    """Return the portfolio snapshot consumed by the cockpit frontpage."""

    return _cockpit_portfolio_snapshot()


@router.get("/cockpit/mangala")
async def get_cockpit_mangala() -> dict[str, Any]:
    """Return the Mangala compound tracker summary for the cockpit.

    Mostra o crescimento do capital comecando com $20 (dinheiro da loteria).
    Consumido pelo frontend no renderMangalaCard().
    """
    try:
        from core.pipeline.nodes.mangala_tracker import get_mangala_tracker

        tracker = get_mangala_tracker()
        summary = tracker.compound_summary()
        summary["status"] = "ok"
        return summary
    except Exception as exc:
        logger.warning("Mangala tracker unavailable: %s", exc)
        return {
            "status": "unavailable",
            "starting": 20.0,
            "current": 20.0,
            "total_flips": 0,
            "win_rate": 0.0,
            "total_profit": 0.0,
            "best_flip": None,
            "worst_flip": None,
            "growth_pct": 0.0,
            "next_target": 30.0,
            "remaining_to_target": 10.0,
            "progress_pct": 0.0,
            "error": str(exc)[:200],
        }


@router.get("/cockpit/mangala/opportunities")
async def get_cockpit_mangala_opportunities() -> dict[str, Any]:
    """Return the top 5 Mangala opportunities from the latest proactive scan.

    Consumido pelo frontend para mostrar as oportunidades scanneadas
    pelo Mangala Daily Scan (whale, pump, score, flip_plan).

    Returns:
        Dict with scanned_at, count, and opportunities list.
        Each opportunity: ticker, price, volume, name, score, signal,
        factors, whale_status, whale_score, pump_risk, pump_score,
        flip_plan, scanned_at.
    """
    try:
        from scripts.mangala_daily_scan import load_latest_scan

        data = load_latest_scan()
        if not data:
            return {
                "status": "no_data",
                "scanned_at": None,
                "count": 0,
                "opportunities": [],
            }
        data["status"] = "ok"
        return data
    except Exception as exc:
        logger.warning("Mangala opportunities unavailable: %s", exc)
        return {
            "status": "unavailable",
            "scanned_at": None,
            "count": 0,
            "opportunities": [],
            "error": str(exc)[:200],
        }


@router.get("/trades/history")
async def get_trade_history(limit: int = Query(50, ge=1, le=250)) -> dict[str, Any]:
    """Return PaperJournal trade history for cockpit audit panels."""

    return _cockpit_trade_history(limit=limit)


@router.get("/cockpit/summary")
def get_cockpit_summary(request: Request) -> dict[str, Any]:
    """Return aggregated cockpit data for the frontpage panels."""

    pipeline = getattr(request.app.state, "pipeline", None)
    pipeline_status = pipeline.get_status() if pipeline else {"status": "unavailable"}
    sentiment: dict[str, Any] = {"available": False, "pulses": [], "alerts": [], "db_rows": 0}
    pulse = getattr(request.app.state, "sentiment_pulse", None)
    monitor = getattr(request.app.state, "sentiment_monitor", None)
    if pulse is not None and monitor is not None:
        pulses = [_as_jsonable(item) for item in pulse.get_all_pulses()]
        alerts = monitor.get_alerts(limit=20)
        sentiment = {
            "available": True,
            "pulses": pulses,
            "pulse_count": len(pulses),
            "alerts": alerts,
            "alert_count": len(alerts),
        }
    # â”€â”€ Sentiment DB stats (SQLite long-term history) â”€â”€
    try:
        import sqlite3

        _db = _sentiment_db_path()
        if _db.exists():
            _conn = sqlite3.connect(str(_db))
            _cnt = _conn.execute("SELECT COUNT(*) FROM sentiment_history").fetchone()
            sentiment["db_rows"] = int(_cnt[0]) if _cnt else 0
            _conn.close()
    except Exception:
        sentiment["db_rows"] = -1  # unavailable

    portfolio = _cockpit_portfolio_snapshot()
    status = _cockpit_status_snapshot(
        pipeline_status=pipeline_status,
        sentiment_available=sentiment["available"],
        portfolio=portfolio,
    )
    guardrails = _cockpit_guardrail_summary()
    deep = {
        "last_math": getattr(request.app.state, "last_math_report", None),
        "last_experts": getattr(request.app.state, "last_expert_verdicts", []),
        "last_trinity": getattr(request.app.state, "last_trinity_report", ""),
    }
    bob = {
        "last_decision": getattr(request.app.state, "last_decision_trace", {}),
        "portfolio": portfolio,
        "guardrails": guardrails,
        "approvals": _cockpit_approval_summary(),
    }

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "pipeline": pipeline_status,
        "sentiment": sentiment,
        "portfolio": portfolio,
        "genie": {
            "pulses": sentiment["pulses"],
            "alerts": sentiment["alerts"][:5],
        },
        "deep": deep,
        "bob": bob,
        "status": status,
    }


@router.post("/paper/approve/{request_id}")
async def approve_paper_order(request_id: str, request: Request) -> dict[str, Any]:
    _require_trading_auth(request)
    """Approve a pending paper trading request."""

    from core.trading.approval_gate import approval_request_to_dict, get_approval_gate

    approved = get_approval_gate().approve(request_id, approver="operator")
    if approved is None:
        raise HTTPException(status_code=404, detail=f"approval request not found: {request_id}")
    return {"ok": True, "request": approval_request_to_dict(approved)}


@router.post("/paper/reject/{request_id}")
async def reject_paper_order(request_id: str, request: Request) -> dict[str, Any]:
    _require_trading_auth(request)
    """Reject a pending paper trading request."""

    from core.trading.approval_gate import approval_request_to_dict, get_approval_gate

    rejected = get_approval_gate().reject(request_id, approver="operator")
    if rejected is None:
        raise HTTPException(status_code=404, detail=f"approval request not found: {request_id}")
    return {"ok": True, "request": approval_request_to_dict(rejected)}


@router.get("/sentiment/pulse")
async def get_sentiment_pulses(request: Request) -> dict[str, Any]:
    """Return the latest sentiment pulse for the full watchlist."""

    pulse = _get_sentiment_pulse(request)
    reports = [_as_jsonable(item) for item in pulse.get_all_pulses()]
    return {"pulses": reports, "count": len(reports)}


@router.get("/sentiment/pulse/{ticker}")
async def get_sentiment_pulse(ticker: str, request: Request) -> dict[str, Any]:
    """Return the latest sentiment pulse for one ticker."""

    clean = _sanitize_ticker(ticker)
    pulse = _get_sentiment_pulse(request)
    return {"pulse": _as_jsonable(pulse.get_pulse(clean))}


@router.get("/sentiment/alerts")
async def get_sentiment_alerts(
    request: Request,
    limit: int = Query(20, ge=1, le=100),
) -> dict[str, Any]:
    """Return newest live sentiment alerts."""

    monitor = _get_sentiment_monitor(request)
    alerts = monitor.get_alerts(limit=limit)
    return {"alerts": alerts, "count": len(alerts)}


@router.get("/sentiment/history/{ticker}")
async def get_sentiment_history(
    ticker: str,
    request: Request,
    hours: int = Query(24, ge=1, le=168),
) -> dict[str, Any]:
    """Return sentiment history for one ticker."""

    clean = _sanitize_ticker(ticker)
    monitor = _get_sentiment_monitor(request)
    snapshot = monitor.get_sentiment_snapshot(clean)
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    history = []
    for item in snapshot.get("history_24h") or []:
        ts = _parse_iso_datetime(item.get("collected_at"))
        if ts is None or ts >= cutoff:
            history.append(item)
    return {"ticker": clean, "hours": hours, "history": history, "count": len(history)}


@router.get("/sentiment/history/{ticker}/db")
async def get_sentiment_history_db(
    ticker: str,
    days: int = Query(30, ge=1, le=365),
) -> dict[str, Any]:
    """Return long-term sentiment history from SQLite."""
    import sqlite3

    clean = _sanitize_ticker(ticker)
    db_path = _sentiment_db_path()
    if not db_path.exists():
        return {"ticker": clean, "days": days, "history": [], "count": 0}

    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    try:
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """SELECT collected_at, score, label, reddit_mentions, news_count, flags
               FROM sentiment_history
               WHERE ticker = ? AND collected_at >= ?
               ORDER BY collected_at DESC
               LIMIT 500""",
            (clean, cutoff),
        ).fetchall()
        conn.close()
    except Exception:
        return {
            "ticker": clean,
            "days": days,
            "history": [],
            "count": 0,
            "error": "db_query_failed",
        }

    history = [dict(r) for r in rows]
    return {"ticker": clean, "days": days, "history": history, "count": len(history)}


@router.get("/health/trace/{run_id}")
async def get_decision_trace(run_id: str) -> dict[str, Any]:
    """Return the DecisionTrace blame report for one pipeline run."""
    if not re.fullmatch(r"[A-Za-z0-9_.-]{1,96}", run_id or ""):
        raise HTTPException(status_code=400, detail="Invalid trace run id")

    from core.audit.decision_trace import DecisionTraceLogger

    report = DecisionTraceLogger().blame_report(run_id)
    return report


@router.get("/health/trace/agent/{agent}/stats")
async def get_agent_trace_stats(agent: str, days: int = 7) -> dict[str, Any]:
    """Return agent performance stats from decision traces."""
    if not re.fullmatch(r"[A-Za-z0-9_.-]{1,64}", agent or ""):
        raise HTTPException(status_code=400, detail="Invalid agent name")

    from core.audit.decision_trace import get_agent_stats

    try:
        days = min(max(int(days), 1), 90)  # Clamp between 1-90 days
    except (ValueError, TypeError):
        days = 7

    return get_agent_stats(agent, days)


def _resolve_evidence_run_dir(run_id: str):
    """Resolve an evidence run directory without allowing traversal."""
    from core.evidence.run import EVIDENCE_DIR

    if not re.fullmatch(r"[A-Za-z0-9_.-]{1,96}", run_id or ""):
        raise HTTPException(status_code=400, detail="Invalid evidence run id")

    root = EVIDENCE_DIR.resolve()
    run_dir = (root / run_id).resolve()
    if not run_dir.is_relative_to(root) or not run_dir.is_dir():
        raise HTTPException(status_code=404, detail=f"Evidence run not found: {run_id}")
    return run_dir


def _resolve_evidence_file(run_id: str, filename: str):
    """Resolve an evidence file without allowing traversal outside the run."""
    if not filename or "\\" in filename:
        raise HTTPException(status_code=400, detail="Invalid evidence filename")

    run_dir = _resolve_evidence_run_dir(run_id)
    file_path = (run_dir / filename).resolve()
    if not file_path.is_relative_to(run_dir) or not file_path.is_file():
        raise HTTPException(status_code=404, detail=f"File not found: {filename}")
    return file_path


# â”€â”€ Two-Phase Paper Trade â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

# --- Trading auth (2FA) ---
_TRADING_TOKENS: dict[str, float] = {}
_TRADING_TOKEN_TTL = 900  # 15 minutes


def _require_trading_auth(request: Request) -> str:
    """Verify second-factor trading token. Skipped if SUPEREZIO_API_KEY is not configured (dev mode)."""
    if not os.getenv("SUPEREZIO_API_KEY"):
        return ""  # dev mode — no trading auth required
    token = request.headers.get("X-Trading-Token", "")
    if not token:
        raise HTTPException(status_code=401, detail="Trading requires X-Trading-Token header")
    ts = _TRADING_TOKENS.get(token)
    if ts is None:
        raise HTTPException(status_code=401, detail="Invalid trading token")
    if time.time() - ts > _TRADING_TOKEN_TTL:
        del _TRADING_TOKENS[token]
        raise HTTPException(status_code=401, detail="Trading token expired")
    return token


def _require_td_ticket_auth(request: Request) -> str:
    """Fail closed for live-manual artifacts even when the rest of the app is in dev mode."""

    if not os.getenv("SUPEREZIO_API_KEY"):
        raise HTTPException(
            status_code=503,
            detail="TD live-manual tickets require SUPEREZIO_API_KEY to be configured",
        )
    token = _require_trading_auth(request)
    _TRADING_TOKENS.pop(token, None)
    return token


def _manual_workflow() -> ManualTradeWorkflow:
    return ManualTradeWorkflow(get_trade_workflow_store())


def _manual_operator(payload: dict[str, Any]) -> str:
    operator = str(payload.get("operator") or "").strip()
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{2,63}", operator):
        raise HTTPException(status_code=422, detail="operator identity is required")
    return operator


def _manual_workflow_http_error(exc: Exception) -> HTTPException:
    detail = str(exc)
    status_code = 404 if detail.startswith("unknown ticket:") else 409
    return HTTPException(status_code=status_code, detail=detail)


@router.post("/api/trading/token")
async def create_trading_token(request: Request) -> dict[str, Any]:
    """Generate a single-use trading token after JWT and API-key authentication."""
    expected_key = os.getenv("SUPEREZIO_API_KEY", "")
    if not expected_key:
        raise HTTPException(
            status_code=503,
            detail="Trading token issuance is disabled until SUPEREZIO_API_KEY is configured",
        )
    provided_key = request.headers.get("X-API-Key", "")
    if not provided_key or not hmac.compare_digest(provided_key, expected_key):
        raise HTTPException(status_code=401, detail="Invalid or missing X-API-Key")

    token = secrets.token_urlsafe(32)
    _TRADING_TOKENS[token] = time.time()
    for t, ts in list(_TRADING_TOKENS.items()):
        if time.time() - ts > _TRADING_TOKEN_TTL:
            del _TRADING_TOKENS[t]
    return {"token": token, "expires_in": _TRADING_TOKEN_TTL, "type": "trading_session"}


@router.post("/trade/execute")
async def execute_trade_fast(payload: dict[str, Any], request: Request) -> dict[str, Any]:
    _require_trading_auth(request)
    """Create a pending paper-trade ticket without bypassing validation."""
    ticker = str(payload.get("ticker", "")).upper()
    action = str(payload.get("action", "buy")).lower()
    qty = int(payload.get("qty", 1))
    limit_price = _clean_float(payload.get("limit_price")) or 0.0
    message = str(payload.get("message", ""))
    session_id = str(payload.get("session_id", "fast-trade"))

    if not ticker:
        raise HTTPException(status_code=400, detail="missing ticker")
    if action not in {"buy", "sell"}:
        raise HTTPException(status_code=400, detail="action must be buy or sell")
    if qty <= 0:
        raise HTTPException(status_code=400, detail="qty must be positive")

    fingerprint = build_trade_intent_fingerprint(
        {
            "ticker": ticker,
            "action": action,
            "qty": qty,
            "limit_price": limit_price,
            "session_id": session_id,
        }
    )
    order_id = f"ticket-{fingerprint[:20]}"
    ticket = {
        "ticket_id": order_id,
        "fingerprint": fingerprint,
        "broker": "BROKER_NEUTRAL_VALIDATION_ONLY",
        "phase": "pending_validation",
        "status": "PENDING_VALIDATION",
        "ticker": ticker,
        "action": action,
        "qty": qty,
        "limit_price": limit_price,
        "message": message,
        "session_id": session_id,
        "pipeline": "required_before_submit",
        "submitted_to_broker": False,
        "reason": "committee_required_before_submit",
        "next_step": (
            "Submit through Bob/pipeline so guardrails, feedback, RAG "
            "and expert committee run before broker transmission."
        ),
    }
    try:
        stored, created = get_trade_workflow_store().create_ticket(ticket)
    except (WorkflowStoreError, WorkflowConflictError) as exc:
        raise HTTPException(status_code=503, detail="trade status store is unavailable") from exc

    return {
        "ok": False,
        "order_id": order_id,
        "idempotent_replay": not created,
        **stored,
    }


@router.post("/trade/td-draft")
async def create_td_direct_live_ticket(payload: dict[str, Any], request: Request) -> dict[str, Any]:
    """Create an auditable live-manual TD ticket; never connect to or submit at TD."""

    _require_td_ticket_auth(request)
    client_quote_fields = sorted(
        field for field in ("quote_price", "quote_source", "quote_as_of") if field in payload
    )
    if client_quote_fields:
        raise HTTPException(
            status_code=422,
            detail="client quote assertions are forbidden: " + ", ".join(client_quote_fields),
        )
    try:
        trusted_quote = resolve_server_quote(payload, data_hub=hub)
        ticket = build_td_direct_ticket(payload, trusted_quote=trusted_quote)
    except ServerQuoteError as exc:
        raise HTTPException(status_code=503, detail=f"trusted quote unavailable: {exc}") from exc
    except TDDirectTicketError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    try:
        store = get_trade_workflow_store()
        stored_ticket, created = store.create_ticket(ticket)
        append_td_direct_ticket(ticket)
    except (OSError, TDDirectTicketError, WorkflowStoreError, WorkflowConflictError) as exc:
        try:
            fingerprint = str(locals().get("ticket", {}).get("fingerprint") or "unknown")
            store = locals().get("store") or get_trade_workflow_store()
            store.record_dead_letter(
                category="td_ticket_audit",
                idempotency_key=fingerprint,
                payload=locals().get("ticket", {"payload_rejected": True}),
                error=str(exc),
            )
            stored = locals().get("stored_ticket")
            if isinstance(stored, dict) and str(stored.get("status", "")).startswith("DRAFT_"):
                store.transition_ticket(
                    str(stored["ticket_id"]),
                    expected_status=str(stored["status"]),
                    new_status="AUDIT_WRITE_FAILED",
                    new_phase="dead_letter_replay_required",
                    actor="system",
                    idempotency_key=f"audit-write-failed:{fingerprint}",
                    details={"error": type(exc).__name__},
                )
        except Exception:
            logger.exception("Failed to persist TD ticket dead letter")
        raise HTTPException(status_code=503, detail="TD ticket audit log is unavailable") from exc

    order_id = str(stored_ticket["ticket_id"])
    return {
        "ok": False,
        "ready_for_execution": False,
        "order_id": order_id,
        "audit_recorded": True,
        "idempotent_replay": not created,
        "ticket": stored_ticket,
    }


@router.post("/trade/manual/{ticket_id}/request-approval")
async def request_manual_trade_approval(
    ticket_id: str, payload: dict[str, Any], request: Request
) -> dict[str, Any]:
    """Request human approval after trusted automated gates have passed."""

    _require_td_ticket_auth(request)
    operator = _manual_operator(payload)
    try:
        approval = _manual_workflow().request_approval(ticket_id, actor=operator)
    except (ManualTradeWorkflowError, WorkflowConflictError, WorkflowStoreError) as exc:
        raise _manual_workflow_http_error(exc) from exc
    return {
        "ok": False,
        "ready_for_execution": False,
        "ticket_id": ticket_id,
        "approval": approval_request_to_dict(approval),
        "submitted_to_broker": False,
    }


@router.post("/trade/manual/{ticket_id}/td-preview")
async def record_manual_td_preview(
    ticket_id: str, payload: dict[str, Any], request: Request
) -> dict[str, Any]:
    """Record the complete official TD cost preview before human approval."""

    _require_td_ticket_auth(request)
    operator = _manual_operator(payload)
    try:
        ticket = _manual_workflow().record_td_preview(ticket_id, payload, actor=operator)
    except (ManualTradeWorkflowError, WorkflowConflictError, WorkflowStoreError) as exc:
        raise _manual_workflow_http_error(exc) from exc
    return {
        "ok": True,
        "ticket": ticket,
        "preview_evidence_hash": ticket["td_preview"]["evidence_hash"],
        "submitted_to_broker": False,
        "system_transmitted": False,
    }


@router.post("/trade/manual/{ticket_id}/money-gate")
async def run_manual_trade_money_gate(
    ticket_id: str, payload: dict[str, Any], request: Request
) -> dict[str, Any]:
    """Evaluate a fresh operator-attested TD snapshot and reserve buying power."""

    _require_td_ticket_auth(request)
    operator = _manual_operator(payload)
    store = get_trade_workflow_store()
    ticket = store.get_ticket(ticket_id)
    if ticket is None:
        raise HTTPException(status_code=404, detail=f"unknown ticket: {ticket_id}")
    if ticket.get("status") == "GATED" and dict(ticket.get("money_gate") or {}).get("passed"):
        return {
            "ok": True,
            "ticket": ticket,
            "money_gate": ticket["money_gate"],
            "submitted_to_broker": False,
            "system_transmitted": False,
            "idempotent_replay": True,
        }
    try:
        fx_evidence = (
            resolve_usd_cad_evidence() if str(ticket.get("currency")).upper() == "USD" else None
        )
        evidence = CanadaMoneyGate(store).evaluate(
            ticket,
            payload.get("account_snapshot") or {},
            operator=operator,
            fx_evidence=fx_evidence,
        )
        gated = _manual_workflow().apply_money_gate(ticket_id, evidence)
    except (
        CanadaMoneyGateError,
        ManualTradeWorkflowError,
        WorkflowConflictError,
        WorkflowStoreError,
    ) as exc:
        raise _manual_workflow_http_error(exc) from exc
    return {
        "ok": True,
        "ticket": gated,
        "money_gate": evidence,
        "submitted_to_broker": False,
        "system_transmitted": False,
    }


@router.post("/trade/manual/{ticket_id}/approve/{approval_id}")
async def approve_manual_trade(
    ticket_id: str,
    approval_id: str,
    payload: dict[str, Any],
    request: Request,
) -> dict[str, Any]:
    """Resolve the approval attached to exactly one durable ticket hash."""

    _require_td_ticket_auth(request)
    operator = _manual_operator(payload)
    try:
        ticket = _manual_workflow().approve(ticket_id, approval_id, actor=operator)
    except (ManualTradeWorkflowError, WorkflowConflictError, WorkflowStoreError) as exc:
        raise _manual_workflow_http_error(exc) from exc
    return {"ok": True, "ticket": ticket, "submitted_to_broker": False}


@router.post("/trade/manual/{ticket_id}/reject/{approval_id}")
async def reject_manual_trade(
    ticket_id: str,
    approval_id: str,
    payload: dict[str, Any],
    request: Request,
) -> dict[str, Any]:
    _require_td_ticket_auth(request)
    operator = _manual_operator(payload)
    try:
        ticket = _manual_workflow().reject(ticket_id, approval_id, actor=operator)
    except (ManualTradeWorkflowError, WorkflowConflictError, WorkflowStoreError) as exc:
        raise _manual_workflow_http_error(exc) from exc
    return {"ok": True, "ticket": ticket, "submitted_to_broker": False}


@router.post("/trade/manual/{ticket_id}/entered")
async def record_manual_trade_entry(
    ticket_id: str, payload: dict[str, Any], request: Request
) -> dict[str, Any]:
    """Record the operator's attestation after using an official TD platform."""

    _require_td_ticket_auth(request)
    operator = _manual_operator(payload)
    try:
        ticket = _manual_workflow().record_manual_entry(ticket_id, payload, actor=operator)
    except (ManualTradeWorkflowError, WorkflowConflictError, WorkflowStoreError) as exc:
        raise _manual_workflow_http_error(exc) from exc
    return {
        "ok": False,
        "broker_confirmed": False,
        "ticket": ticket,
        "warning": "Operator-reported submission is not yet broker confirmation.",
    }


@router.post("/trade/manual/{ticket_id}/broker-confirm")
async def record_manual_trade_broker_confirmation(
    ticket_id: str, payload: dict[str, Any], request: Request
) -> dict[str, Any]:
    """Record a human-observed TD confirmation reference; never contact TD."""

    _require_td_ticket_auth(request)
    operator = _manual_operator(payload)
    try:
        ticket = _manual_workflow().record_broker_confirmation(ticket_id, payload, actor=operator)
    except (ManualTradeWorkflowError, WorkflowConflictError, WorkflowStoreError) as exc:
        raise _manual_workflow_http_error(exc) from exc
    return {
        "ok": True,
        "broker_confirmed": True,
        "ticket": ticket,
        "system_transmitted": False,
    }


@router.get("/trade/td-commission-free")
async def get_td_commission_free_etfs() -> dict[str, Any]:
    """Return the dated official TD commission-free ETF research universe."""

    try:
        manifest = load_td_commission_free_manifest()
    except TDDirectTicketError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    canadian = manifest["symbols"]["CAN"]
    us = manifest["symbols"]["US"]
    return {
        "ok": True,
        "count": len(canadian) + len(us),
        "manifest": manifest,
        "warning": "Confirm eligibility and total fees in TD's order preview before trading.",
    }


@router.get("/trade/status/{order_id}")
async def get_trade_status(order_id: str) -> dict[str, Any]:
    """Fase 2: Verificar status da validaÃ§Ã£o (pipeline background)."""
    try:
        store = get_trade_workflow_store()
        status = store.get_ticket(order_id) or {"phase": "unknown"}
        if status.get("ticket_id"):
            status["events"] = store.get_events(order_id)
    except WorkflowStoreError as exc:
        raise HTTPException(status_code=503, detail="trade status store is unavailable") from exc
    return {"order_id": order_id, **status}


@router.get("/training/orders")
async def get_training_orders() -> dict[str, Any]:
    """Retorna ordens de treinamento para o Bob aparecerem no UI."""
    from pathlib import Path

    training_file = (
        Path(__file__).resolve().parent.parent.parent
        / "runtime"
        / "training"
        / "bob_chart_orders.jsonl"
    )
    orders = []

    if training_file.exists():
        try:
            for line in training_file.read_text(encoding="utf-8").strip().splitlines():
                if not line:
                    continue
                try:
                    order = json.loads(line)
                    # Convert training order to UI-compatible format
                    orders.append(
                        {
                            "order_id": order.get("order_id"),
                            "ticker": order.get("ticker"),
                            "action": order.get("action", "BUY").upper(),
                            "side": order.get("action", "buy").lower(),
                            "qty": 100,  # Default training qty
                            "limit_price": None,
                            "order_type": "MARKET",
                            "status": "TRAINING",
                            "source": "training",
                            "training_type": order.get("type"),
                            "training_message": order.get("message"),
                            "timeframe": order.get("timeframe"),
                        }
                    )
                except json.JSONDecodeError:
                    continue
        except Exception as exc:
            logger.warning("Failed to load training orders", error=str(exc)[:200])

    return {
        "source": "training",
        "count": len(orders),
        "orders": orders,
    }


# â”€â”€ Task Queue endpoints â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


@router.get("/task/status/{run_id}")
async def get_task_status(run_id: str) -> dict[str, Any]:
    """Status de uma task pelo run_id."""
    from core.pipeline.task_queue import get_task_queue

    return get_task_queue().status(run_id)


@router.post("/task/cancel/{run_id}")
async def cancel_task(run_id: str) -> dict[str, Any]:
    """Cancela uma task ativa."""
    from core.pipeline.task_queue import get_task_queue

    ok = get_task_queue().cancel(run_id)
    return {"cancelled": ok, "run_id": run_id}


@router.get("/task/active")
async def list_active_tasks() -> dict[str, Any]:
    """Lista todas as tasks ativas."""
    from core.pipeline.task_queue import get_task_queue

    tq = get_task_queue()
    return {"count": tq.active_count, "tasks": tq.active_tasks}
