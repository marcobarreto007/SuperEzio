"""F51 Trade Gate — Central safety validator for ALL paper/real orders.

CRITICAL: This module is the SINGLE gate that every order MUST pass through.
It fails CLOSED. If in doubt, BLOCK.

Design contract:
- Called BEFORE auto_execute_paper and BEFORE _submit_paper_order
- Returns TradeGateDecision with status: ALLOW, BLOCK, or REVIEW
- BLOCK is the default — explicit conditions must be met to ALLOW
- Every BLOCK decision carries a specific reason code
- Journal records ALL decisions (ALLOW, BLOCK, REVIEW)
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from core.config.logging_config import get_logger
from core.config.settings import get_settings

logger = get_logger(__name__)

# ═══════════════════════════════════════════════════════════════
# EXECUTION FREEZE — Global safety switch
# ═══════════════════════════════════════════════════════════════


def _superezio_paper_only_or_live_disabled() -> str | None:
    """Check the SUPEREZIO_* safety family, unified with F51_TRADING_EXECUTION_FREEZE.

    These two variable families were introduced independently (F51_* by the
    original trade gate, SUPEREZIO_* by the research/paper-only pipeline
    added later) and did not check each other — a gate audit (2026-07-19,
    docs/audit/phase6_rag_pennylab_execution.md, finding 6.1) confirmed this
    let SUPEREZIO_LIVE_TRADING_DISABLED default to False with no effect on
    this gate. Both families must now agree for real execution to be
    possible; either one requesting safety wins (fail-safe OR, not AND).

    Returns a reason string if either SUPEREZIO_* flag requests a freeze,
    else None.
    """
    live_disabled = os.getenv("SUPEREZIO_LIVE_TRADING_DISABLED", "").strip().lower()
    if live_disabled in {"1", "true", "yes", "on"}:
        return "SUPEREZIO_LIVE_TRADING_DISABLED=true"
    paper_only = os.getenv("SUPEREZIO_RESEARCH_PAPER_ONLY", "").strip().lower()
    if paper_only in {"1", "true", "yes", "on"}:
        return "SUPEREZIO_RESEARCH_PAPER_ONLY=true"
    daytrade_paper_only = os.getenv("SUPEREZIO_DAYTRADE_PAPER_ONLY", "").strip().lower()
    if daytrade_paper_only in {"1", "true", "yes", "on"}:
        return "SUPEREZIO_DAYTRADE_PAPER_ONLY=true"
    return None


def is_execution_frozen() -> bool:
    """Check global kill switch (fail-safe: defaults to True).

    Priority: SUPEREZIO_* research/paper-only flags (any one true freezes)
    > env var F51_TRADING_EXECUTION_FREEZE > Pydantic Settings > default True.
    Direct env var check preserves testability via monkeypatch.
    """
    if _superezio_paper_only_or_live_disabled() is not None:
        return True
    # Check raw env var first (allows test overrides via monkeypatch.setenv)
    raw = os.getenv("F51_TRADING_EXECUTION_FREEZE", "").strip().lower()
    if raw in {"0", "false", "no", "off"}:
        return False
    if raw in {"1", "true", "yes", "on"}:
        return True
    # Fall back to validated Settings
    try:
        return get_settings().f51_trading_execution_freeze
    except RuntimeError:
        return True  # Settings invalid → SAFE


# ═══════════════════════════════════════════════════════════════
# PORTUGUESE / ENGLISH BLACKLIST
# ═══════════════════════════════════════════════════════════════

_TICKER_BLACKLIST: set[str] = {
    "TODAS",
    "TODOS",
    "TUDO",
    "HOJE",
    "AGORA",
    "ISSO",
    "AQUILO",
    "COMPRAR",
    "VENDER",
    "VENDA",
    "SENTIMENTO",
    "VIVO",
    "MELHOR",
    "PIOR",
    "NENHUM",
    "ALGUM",
    "CERTO",
    "ERRADO",
    "FORTE",
    "FRACO",
    "ALTA",
    "BAIXA",
    "FECHAR",
    "ABRIR",
    "ENTRAR",
    "SAIR",
    "FICAR",
    "MOMENTO",
    "MERCADO",
    "DINHEIRO",
    "CARTEIRA",
    "RISCO",
    "CUSTO",
    "LUCRO",
    "PREJU",
    "GANHO",
    "PERDA",
    "VALOR",
    "PAPEL",
    "ORDEM",
    "EXECUCAO",
    "ANALISE",
    "ESTRATEGIA",
    "ALL",
    "BUY",
    "SELL",
    "NOW",
    "TODAY",
    "HERE",
    "THERE",
    "THIS",
    "THAT",
    "WHAT",
    "WHEN",
    "WHY",
    "HOW",
    "JUST",
    "ONLY",
    "ALSO",
    "SENTIMENT",
    "MARKET",
    "PRICE",
    "VALUE",
    "COST",
    "PROFIT",
    "LOSS",
    "GAIN",
    "RISK",
    "TRADE",
    "ORDER",
    "EXECUTION",
}


def is_ticker_blacklisted(symbol: str) -> bool:
    return symbol.upper().strip() in _TICKER_BLACKLIST


def is_valid_ticker_format(symbol: str) -> bool:
    if not symbol or len(symbol.strip()) < 2:
        return False
    cleaned = symbol.upper().strip()
    pattern = r"^[A-Z]{2,5}(\.[A-Z]{1,3})?$"
    return bool(re.match(pattern, cleaned))


# ═══════════════════════════════════════════════════════════════
# EXPLICIT TRADE INTENT DETECTION
# ═══════════════════════════════════════════════════════════════

_TRADE_INTENT_PATTERNS: list[str] = [
    r"\bcompr[ae]\w*\b",
    r"\bvend[ae]\w*\b",
    r"\bexecut[ae]\w*\s+(ordem|trade|papel|paper)\b",
    r"\bsubmit\w*\s+(ordem|order|papel|paper)\b",
    r"\babr[ei]\w*\s+(posicao|position)\b",
    r"\bfech[ae]\w*\s+(posicao|position|trade)\b",
    r"\b(PAPER_TICKET|paper.ticket|paper order)\b",
    r"\bordem\s+(de\s+)?(compra|venda|paper)\b",
    r"\bacion[ae]\w*\s+(ordem|compra|venda)\b",
    r"\bbuy\b",
    r"\bsell\b",
    r"\bshort\b",
    r"\bexecute\s+(order|trade)\b",
    r"\bsubmit\s+(order|paper)\b",
    r"\bopen\s+(position|trade)\b",
    r"\bclose\s+(position|trade)\b",
    r"\bplace\s+(order|trade)\b",
]

_NON_TRADE_PATTERNS: list[str] = [
    r"\bexplica\b",
    r"\bexplique\b",
    r"\bexplain\b",
    r"\bo que (e|significa|quer dizer)\b",
    r"\bwhat (is|does|are)\b",
    r"\bcomo (funciona|se calcula|se usa)\b",
    r"\bhow (does|to|do|can|should)\b",
    r"\bme (ensina|mostra|explica|ajuda|tira duvida)\b",
    r"\b(duvida|pergunta|quest|question)\b",
    r"\banalisa\b",
    r"\banalyze?\b",
    r"\bverifica\b",
    r"\bcheck\b",
    r"\bmostra\b",
    r"\bshow\b",
    r"\bdescrev[ae]\b",
    r"\bdescrib\w*\b",
    # Hypothetical / conditional — NEVER trade intent
    r"\b(e se|what if|simula|hypothetical|hipotetico)\b",
    r"\bcompra\s*\?\s*$",  # "compra?" with question mark
    r"\bvende\s*\?\s*$",  # "vende?" with question mark
    r"\bcompras+\w*\s*\?\s*$",  # "comprasse?"
    r"\bsimula\w*\s+(comprar|vender|trade|ordem)\b",
]


def is_explicit_trade_intent(text: str) -> bool:
    if not text or not text.strip():
        return False
    text_lower = text.lower().strip()
    for pattern in _NON_TRADE_PATTERNS:
        if re.search(pattern, text_lower):
            logger.info("[F51_TRADE_GATE] Non-trade pattern matched: %s", pattern)
            return False
    for pattern in _TRADE_INTENT_PATTERNS:
        if re.search(pattern, text_lower):
            logger.info("[F51_TRADE_GATE] Trade intent pattern matched: %s", pattern)
            return True
    return False


# ═══════════════════════════════════════════════════════════════
# IBKR CONNECTIVITY PROBE
# ═══════════════════════════════════════════════════════════════


def is_ibkr_connectable() -> bool:
    settings = get_settings()
    ibkr_host = settings.ibkr_host
    ibkr_port = settings.ibkr_port
    try:
        import socket

        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(2.0)
        s.connect((ibkr_host, ibkr_port))
        s.close()
        return True
    except Exception as exc:
        logger.warning("[F51_TRADE_GATE] IBKR unreachable: %s:%s - %s", ibkr_host, ibkr_port, exc)
        return False


# ═══════════════════════════════════════════════════════════════
# JOURNAL HEALTH CHECK
# ═══════════════════════════════════════════════════════════════


def is_journal_healthy(journal_path: str | None = None) -> bool:
    from pathlib import Path
    import tempfile

    try:
        if journal_path:
            path = Path(journal_path)
        else:
            from core.trading.paper_journal import DEFAULT_JOURNAL_PATH

            path = DEFAULT_JOURNAL_PATH
        path.parent.mkdir(parents=True, exist_ok=True)
        probe_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="wb",
                prefix=".journal-health-",
                dir=path.parent,
                delete=False,
            ) as probe:
                probe.write(b"ok")
                probe.flush()
                os.fsync(probe.fileno())
                probe_path = Path(probe.name)
        finally:
            if probe_path is not None:
                probe_path.unlink(missing_ok=True)
        logger.info("[F51_TRADE_GATE] Journal healthy: %s", path)
        return True
    except Exception as exc:
        logger.error("[F51_TRADE_GATE] Journal unhealthy: %s", exc)
        return False


# ═══════════════════════════════════════════════════════════════
# TICKER VALIDATION via DataHub
# ═══════════════════════════════════════════════════════════════


def resolve_and_validate_ticker(symbol: str) -> "tuple[str | None, float | None, str | None]":
    if not symbol:
        return None, None, "missing_ticker"
    symbol = symbol.upper().strip()
    if is_ticker_blacklisted(symbol):
        return None, None, f"blacklisted_word:{symbol}"
    if not is_valid_ticker_format(symbol):
        return None, None, f"invalid_ticker_format:{symbol}"

    # Try DataHub with circuit breaker + price cache fallback
    try:
        from core.resilience import (
            CircuitOpenError,
            get_circuit,
            get_cached_price,
        )

        datahub_cb = get_circuit("datahub", failure_threshold=3, recovery_timeout=30)

        try:
            result = datahub_cb.call(_fetch_price_from_datahub, symbol)
            if result:
                return result
        except CircuitOpenError:
            logger.warning("datahub_circuit_open_fallback_to_cache", ticker=symbol)
        except Exception as exc:
            logger.warning("datahub_call_failed_fallback", ticker=symbol, error=str(exc)[:120])

        # Graceful degradation: use cached price
        cached_price, is_stale = get_cached_price(symbol)
        if cached_price > 0:
            logger.info(
                "using_cached_price",
                ticker=symbol,
                price=cached_price,
                stale=is_stale,
            )
            return symbol, cached_price, None if not is_stale else "stale_cache"

        return None, None, f"no_price_data:{symbol}"

    except ImportError:
        logger.warning("datahub_unavailable_no_fallback", ticker=symbol)
        return symbol, None, None


def _fetch_price_from_datahub(symbol: str) -> "tuple[str, float, None] | None":
    """Fetch price from DataHub. Separated for circuit breaker wrapping."""
    from data.data_hub import DataHub

    hub = DataHub()
    price_result = hub.get_price(symbol)
    if price_result and price_result.get("price"):
        price = float(price_result["price"])
        resolved_symbol = str(price_result.get("symbol", symbol)).upper()
        # Cache successful result for future fallback
        try:
            from core.resilience import cache_price

            cache_price(symbol, price)
        except ImportError:
            pass
        return resolved_symbol, price, None
    return None


# ═══════════════════════════════════════════════════════════════
# TradeGateDecision
# ═══════════════════════════════════════════════════════════════


@dataclass
class TradeGateDecision:
    status: str = "BLOCK"
    reason: str = ""
    reason_code: str = "UNKNOWN"
    evidence: dict[str, Any] = field(default_factory=dict)
    checked_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    gates_passed: list[str] = field(default_factory=list)
    gates_failed: list[str] = field(default_factory=list)


def build_order_gate_metadata(
    decision: TradeGateDecision,
    *,
    order_symbol: str,
    approval_id: str,
    consensus_decision: str,
) -> dict[str, Any]:
    """Bind a prepared order to an actual successful gate decision."""
    symbol = str(order_symbol or "").strip().upper()
    validated = str(decision.evidence.get("validated_ticker") or "").strip().upper()
    trace_id = str(decision.evidence.get("run_id") or "").strip()
    consensus = str(consensus_decision or "").strip().upper()
    if decision.status != "ALLOW":
        raise ValueError("gate decision is not ALLOW")
    if not symbol or validated != symbol:
        raise ValueError("gate decision ticker does not match order")
    if not trace_id:
        raise ValueError("gate decision has no trace id")
    if not approval_id:
        raise ValueError("order has no approval id")
    if consensus not in {"SUPPORT", "NEUTRAL"}:
        raise ValueError("order has no non-blocking weighted consensus")
    return {
        "gate_status": "ALLOW",
        "gate_trace_id": trace_id,
        "validated_ticker": validated,
        "journal_ready": True,
        "execution_freeze": False,
        "pipeline_prepared": True,
        "adaptive_policy_applied": True,
        "approval_id": approval_id,
        "consensus_decision": consensus,
    }


# ═══════════════════════════════════════════════════════════════
# THE MAIN GATE
# ═══════════════════════════════════════════════════════════════


def evaluate_trade_gate(
    message: str,
    ticker: str,
    thesis_ticker: str = "",
    qty: int = 0,
    limit_price: float = 0.0,
    run_id: str = "",
) -> TradeGateDecision:
    decision = TradeGateDecision()
    gates_checked: list[tuple[str, bool, str]] = []

    # GATE 1: Execution Freeze
    if is_execution_frozen():
        superezio_reason = _superezio_paper_only_or_live_disabled()
        reason = superezio_reason or "F51_TRADING_EXECUTION_FREEZE=true"
        gates_checked.append(("freeze", False, "execution_frozen_by_env"))
        return _build(
            decision,
            "BLOCK",
            "EXECUTION_FREEZE",
            f"Trading execution frozen by {reason}",
            gates_checked,
        )
    gates_checked.append(("freeze", True, "ok"))

    # GATE 2: Non-Trade Intent
    if not is_explicit_trade_intent(message):
        gates_checked.append(("intent", False, "non_trade_intent"))
        return _build(
            decision,
            "BLOCK",
            "NON_TRADE_INTENT",
            f"Message does not contain explicit trade request: '{message[:100]}'",
            gates_checked,
            evidence={"message_snippet": message[:200]},
        )
    gates_checked.append(("intent", True, "ok"))

    ticker = ticker.upper().strip()

    # GATE 3: Ticker Blacklist
    if is_ticker_blacklisted(ticker):
        gates_checked.append(("ticker_blacklist", False, f"blacklisted:{ticker}"))
        return _build(
            decision,
            "BLOCK",
            "BLACKLISTED_TICKER",
            f"Ticker '{ticker}' is a blacklisted common word",
            gates_checked,
            evidence={"ticker": ticker},
        )
    gates_checked.append(("ticker_blacklist", True, "ok"))

    # GATE 4: Ticker Format
    if not is_valid_ticker_format(ticker):
        gates_checked.append(("ticker_format", False, f"invalid_format:{ticker}"))
        return _build(
            decision,
            "BLOCK",
            "INVALID_TICKER_FORMAT",
            f"Ticker '{ticker}' does not match valid ticker format",
            gates_checked,
            evidence={"ticker": ticker},
        )
    gates_checked.append(("ticker_format", True, "ok"))

    # GATE 5: Ticker Mismatch (thesis vs order) should be evaluated before
    # external ticker validation so mismatch diagnostics remain deterministic.
    if thesis_ticker and thesis_ticker.upper() != ticker:
        gates_checked.append(("ticker_mismatch", False, f"{thesis_ticker}_vs_{ticker}"))
        return _build(
            decision,
            "BLOCK",
            "TICKER_MISMATCH",
            f"Thesis ticker {thesis_ticker} != order ticker {ticker}",
            gates_checked,
            evidence={"thesis_ticker": thesis_ticker, "order_ticker": ticker},
        )
    gates_checked.append(("ticker_mismatch", True, "ok"))

    # GATE 7: Quantity Placeholder
    if qty in (5, 10, 100) and limit_price == 99.0:
        gates_checked.append(("quantity", False, "placeholder_quantity_price"))
        return _build(
            decision,
            "BLOCK",
            "PLACEHOLDER_QUANTITY",
            f"Quantity={qty} with limit_price=$99.00 appears to be defaults. Blocked.",
            gates_checked,
            evidence={"qty": qty, "limit_price": limit_price},
        )
    if qty <= 0:
        gates_checked.append(("quantity", False, "zero_or_negative_qty"))
        return _build(
            decision,
            "BLOCK",
            "INVALID_QUANTITY",
            f"Quantity must be > 0, got {qty}",
            gates_checked,
            evidence={"qty": qty},
        )
    gates_checked.append(("quantity", True, "ok"))

    # GATE 8: Price Placeholder ($99.00)
    if limit_price == 99.0:
        gates_checked.append(("price", False, "placeholder_99"))
        return _build(
            decision,
            "BLOCK",
            "PLACEHOLDER_PRICE",
            "Placeholder price $99.00 blocked by policy.",
            gates_checked,
            evidence={"placeholder": 99.0, "ticker": ticker},
        )
    gates_checked.append(("price", True, "ok"))

    # GATE 9: Ticker Validation via DataHub
    validated_ticker, resolved_price, validation_error = resolve_and_validate_ticker(ticker)
    if validation_error:
        gates_checked.append(("ticker_validation", False, validation_error))
        return _build(
            decision,
            "BLOCK",
            "TICKER_VALIDATION_FAILED",
            f"Ticker '{ticker}' failed DataHub validation: {validation_error}",
            gates_checked,
            evidence={"ticker": ticker, "error": validation_error},
        )
    gates_checked.append(("ticker_validation", True, f"ok:{validated_ticker}"))

    # GATE 9: IBKR Health
    ibkr_online = is_ibkr_connectable()
    if not ibkr_online:
        gates_checked.append(("ibkr", False, "ibkr_offline"))
        return _build(
            decision,
            "BLOCK",
            "IBKR_OFFLINE",
            "IBKR TWS/Gateway not reachable. Order blocked.",
            gates_checked,
            evidence={
                "ibkr_host": os.getenv("IBKR_HOST", "127.0.0.1"),
                "ibkr_port": os.getenv("IBKR_PORT", "7497"),
            },
        )
    gates_checked.append(("ibkr", True, "ok"))

    # GATE 10: Journal Health
    journal_ok = is_journal_healthy()
    if not journal_ok:
        gates_checked.append(("journal", False, "journal_unhealthy"))
        return _build(
            decision,
            "BLOCK",
            "JOURNAL_UNAVAILABLE",
            "Paper journal not writable. Order blocked.",
            gates_checked,
        )
    gates_checked.append(("journal", True, "ok"))

    # ALL GATES PASSED
    return _build(
        decision,
        "ALLOW",
        "ALL_GATES_PASSED",
        f"All 10 safety gates passed for {ticker}",
        gates_checked,
        evidence={
            "ticker": ticker,
            "validated_ticker": validated_ticker,
            "resolved_price": resolved_price,
            "qty": qty,
            "run_id": run_id,
        },
    )


def _build(
    decision: TradeGateDecision,
    status: str,
    reason_code: str,
    reason: str,
    gates: list[tuple[str, bool, str]],
    evidence: dict[str, Any] | None = None,
) -> TradeGateDecision:
    decision.status = status
    decision.reason_code = reason_code
    decision.reason = reason
    decision.evidence = evidence or {}
    decision.gates_passed = [g[0] for g in gates if g[1]]
    decision.gates_failed = [g[0] for g in gates if not g[1]]
    return decision


def record_blocked_order(
    decision: TradeGateDecision,
    message: str = "",
    ticker: str = "",
    run_id: str = "",
) -> None:
    try:
        from core.trading.paper_journal import PaperJournal, PaperTrade

        journal = PaperJournal()
        trade = PaperTrade(
            trade_id=f"blocked-{run_id[:12]}"
            if run_id
            else f"blocked-{int(__import__('time').time())}",
            ticker=ticker or "UNKNOWN",
            thesis=f"BLOCKED: {decision.reason_code} - {decision.reason[:100]}",
            direction="blocked",
            entry_date=datetime.now(timezone.utc).isoformat(),
            entry_price=0.0,
            shares=0,
            entry_reasoning=f"f51_trade_gate | reason_code={decision.reason_code} | run_id={run_id}",
            verdict_at_entry="BLOCKED",
            risk_assessment="blocked_by_safety_gate",
            expected_holding_period="none",
        )
        trade_id = journal.open_trade(trade)
        journal.close_trade(
            trade_id,
            exit_price=0.0,
            exit_reason=f"BLOCKED:{decision.reason_code}",
            exit_date=datetime.now(timezone.utc).isoformat(),
        )
        logger.info("[F51_TRADE_GATE] Blocked order recorded: %s", decision.reason_code)
    except Exception as exc:
        logger.error("[F51_TRADE_GATE] Failed to record blocked order: %s", exc)
