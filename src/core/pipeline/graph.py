"""Pipeline v4 graph builder - thin, readable, no business logic."""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from typing import Any, AsyncGenerator, Generator

from langgraph.config import get_stream_writer
from langgraph.graph import END, START, StateGraph

from core.evidence import EvidenceRun, generate_html_report, save_evidence
from core.math.math_hub import MathHub

from .contracts import PipelineState
from .nodes import (
    node_agent,
    node_collector,
    node_tool_executor,
    route_after_agent,
    node_explanation,
    node_blocked,
    node_orchestrator,
)
from .nodes.experts import node_collect_experts, node_expert, EXPERT_PROVIDERS
from .nodes.f51 import node_f51_verdict
from .nodes.neural_decision import node_neural_decision
from .nodes.sdca_firewall import node_sdca_firewall
from .nodes.rag import node_rag_forensics
from .nodes.guardrail_hub import node_guardrail_hub
from .nodes.trinity import node_trinity

logger = logging.getLogger(__name__)

__all__ = ["PipelineApp", "build_graph", "route_after_orchestrator", "route_after_trinity"]


def _scan_evidence_payload(
    node_output: dict[str, Any],
) -> tuple[list[dict[str, Any]], int, list[str]] | None:
    scan_output = node_output.get("scan")
    if isinstance(scan_output, dict):
        scan_trace = scan_output.get("scan_trace") or {}
        sources = scan_trace.get("provider_sources_used") or []
        return (
            scan_output.get("candidates", []),
            int(scan_output.get("rejected_count", 0) or 0),
            list(sources),
        )
    if node_output.get("candidates"):
        return (
            node_output.get("candidates", []),
            int(node_output.get("rejected", 0) or 0),
            list(node_output.get("sources_used", [])),
        )
    return None


def route_after_orchestrator(state: dict) -> str:
    """Esteira linear — sem desvios. Tudo vai pro agente."""
    return "agent"


def route_after_trinity(state: dict) -> str:
    """Esteira linear — sem desvios. Tudo vai pro agente."""
    return "agent"


def _merge_node_update(
    working_state: dict[str, Any],
    output: dict[str, Any],
    update: dict[str, Any],
) -> None:
    """Merge node output into the working state and the graph update."""

    for key, value in (update or {}).items():
        if key == "errors":
            combined = list(working_state.get("errors") or []) + [
                str(item) for item in (value or [])
            ]
            working_state["errors"] = combined
            output["errors"] = combined
            continue
        working_state[key] = value
        output[key] = value


async def _auto_full_analysis(
    state: dict,
    *,
    gateway=None,
    config=None,
) -> dict:
    """Collect evidence and run the decision stack before Bob answers.

    The critical contract is state propagation: collector output must feed the
    experts, F51, neural decision, SDCA, RAG, and then Bob's prompt.
    """

    writer = get_stream_writer()
    run_id = state.get("run_id", "")
    route = state.get("route", "general")
    working_state: dict[str, Any] = {**state}
    output: dict[str, Any] = {}

    # ── CASE tracking ──
    financial_case = working_state.get("financial_case")
    # Preserve case_pending from orchestrator (survives state propagation)
    output["case_pending"] = list(working_state.get("case_pending") or [])
    output["case_context"] = working_state.get("case_context") or ""
    def _mark_step(step_name: str, evidence: dict | None = None):
        if financial_case:
            financial_case.mark_complete(step_name, evidence)
            output["case_steps"] = {
                name: {"completed": s.completed, "error": s.error}
                for name, s in financial_case.steps.items()
            }
            output["case_is_complete"] = financial_case.is_complete
            output["case_pending"] = financial_case.pending_steps

    # ── Clean ticker-specific state between requests ──
    # Prevents ticker leakage: "analise AAPL" → "invista em outros" still sees AAPL
    if route == "general" and not working_state.get("ticker"):
        for key in ("ticker", "data", "data_context", "expert_results",
                     "expert_summary", "expert_verdicts", "trinity_report",
                     "f51_verdict", "math_report", "math_prompt",
                     "neural_decision", "rag_context"):
            working_state.pop(key, None)
        logger.debug("[auto_full_analysis] Cleaned ticker-specific state for route=general")

    writer(
        {
            "type": "PIPELINE_STEP",
            "run_id": run_id,
            "step": "auto_full_analysis",
            "status": "started",
            "route": route,
        }
    )

    # FULL_ACCESS means Bob may use tools; it is not an instruction to run
    # market collection before Bob has decided what the user is asking.
    should_collect_market = bool(
        route in {"market_scan", "ticker_analysis"}
        or working_state.get("force_auto_collect")
    )

    try:
        collector_result: dict[str, Any] = {}
        # Sovereign mode: ALWAYS collect data — Bob needs evidence, not a chat
        if (
            should_collect_market
            and not working_state.get("scan")
            and not working_state.get("data")
        ):
            collector_route = (
                "ticker_analysis"
                if working_state.get("ticker") and route != "market_scan"
                else "market_scan"
            )
            collector_result = await node_collector(
                {**working_state, "route": collector_route},
                config=config,
            )
        if collector_result:
            _merge_node_update(working_state, output, collector_result)
            _mark_step("data_collection")
    except Exception as exc:
        _merge_node_update(
            working_state,
            output,
            {"errors": [f"auto_full_analysis.collect_data:{exc}"]},
        )

    ticker = str(
        working_state.get("ticker") or (working_state.get("data") or {}).get("ticker") or ""
    ).upper()
    data_context = str(working_state.get("data_context") or working_state.get("message") or "")

    try:
        math_hub = MathHub()
        math_report = math_hub.calculate_all(working_state)
        math_prompt = math_hub.to_deepseek_prompt(math_report)
        math_update: dict[str, Any] = {"math_report": math_report, "math_prompt": math_prompt}
        if math_prompt:
            existing_context = str(working_state.get("data_context") or data_context or "")
            math_update["data_context"] = (
                f"{existing_context}\n\n{math_prompt}" if existing_context else math_prompt
            )
        _merge_node_update(working_state, output, math_update)
        _mark_step("math_hub")
        data_context = str(working_state.get("data_context") or data_context)
        writer(
            {
                "type": "MATH_REPORT",
                "run_id": run_id,
                "ticker": math_report.get("ticker"),
                "coverage": math_report.get("coverage"),
                "summary": math_report.get("summary"),
                "modules": math_report.get("modules"),
                "numbers": math_report.get("numbers"),
            }
        )
    except Exception as exc:
        _merge_node_update(
            working_state,
            output,
            {"errors": [f"auto_full_analysis.math_hub:{exc}"]},
        )

    # Market experts only run after market/ticker evidence is actually present.
    expert_results: list[dict[str, Any]] = []
    should_run_market_stack = bool(working_state.get("scan") or working_state.get("data")) and (
        should_collect_market
        or route in {"market_scan", "ticker_analysis"}
        or working_state.get("force_auto_market_stack")
    )
    if should_run_market_stack:
        if not ticker:
            scan_candidates = (working_state.get("scan") or {}).get("candidates", [])
            if scan_candidates:
                ticker = str(scan_candidates[0].get("ticker") or "").upper()
                if ticker:
                    working_state["ticker"] = ticker

        roles = [
            "macro_risk",
            "fundamental_value",
            "momentum_technical",
            "contrarian_opportunity",
            "sentiment",
            "social_forensics",
        ]
        for role in roles:
            try:
                res = await node_expert(
                    {
                        **working_state,
                        "role": role,
                        "ticker": ticker,
                        "data_context": data_context,
                    },
                    gateway=gateway,
                )
                for expert_result in res.get("expert_results", []):
                    expert_result.setdefault("role", role)
                    expert_result.setdefault("provider", EXPERT_PROVIDERS.get(role, "unknown"))
                    expert_results.append(expert_result)
            except Exception as exc:
                expert_results.append(
                    {
                        "role": role,
                        "ok": False,
                        "error": str(exc)[:200],
                        "provider": EXPERT_PROVIDERS.get(role, "?"),
                    }
                )

        _merge_node_update(working_state, output, {"expert_results": expert_results})
        _mark_step("expert_committee", {"roles_ran": len(expert_results)})
        try:
            collect_res = await node_collect_experts(
                {**working_state, "expert_results": expert_results}
            )
            _merge_node_update(working_state, output, collect_res)
        except Exception as exc:
            _merge_node_update(
                working_state,
                output,
                {
                    "expert_summary": f"Expert collection error: {exc}",
                    "errors": [f"auto_full_analysis.experts:{exc}"],
                },
            )
    # ── IBKR portfolio snapshot: always inject current positions ──
    # Run IBKR connection in a thread to avoid asyncio event-loop
    # conflicts on Windows (ib_insync uses its own loop).

    def _fetch_ibkr_snapshot() -> str:
        import asyncio as _asyncio
        _loop = _asyncio.new_event_loop()
        _asyncio.set_event_loop(_loop)
        try:
            from ib_insync import IB as _IB
            from ib_insync import Stock as _Stock

            _ib = _IB()
            _ib.connect("127.0.0.1", 7497, clientId=int(time.time() * 1000) % 9000 + 100, timeout=5)

            # Configure market data types (delayed 3 is free, no subscription required)
            _ib.reqMarketDataType(3)

            pos_list = _ib.positions()
            positions = []
            total_value = 0.0

            if pos_list:
                contracts = [_Stock(p.contract.symbol, "SMART", "USD") for p in pos_list]
                _ib.qualifyContracts(*contracts)
                tickers = [_ib.reqMktData(c) for c in contracts]
                _ib.sleep(1.0)

                for p, ticker in zip(pos_list, tickers):
                    _ib.cancelMktData(p.contract)
                    price = ticker.last or ticker.close or ticker.marketPrice() or float(p.avgCost)
                    pos_val = float(p.position) * price
                    pnl = (price - float(p.avgCost)) * float(p.position)
                    positions.append(
                        f"{p.contract.symbol}: {p.position} shares @ avg ${float(p.avgCost):.2f} (current ${price:.2f}) = ${pos_val:,.2f} [PnL: ${pnl:+,.2f}]"
                    )
                    total_value += pos_val

            equity = 0.0
            for v in _ib.accountSummary():
                if v.tag == "NetLiquidation":
                    equity = float(v.value)
            _ib.disconnect()

            return (
                f"CURRENT PORTFOLIO (IBKR paper):\n"
                f"  Equity: ${equity:,.2f}\n"
                f"  Positions: {len(positions)}\n"
                + "".join(f"    {p}\n" for p in positions)
                + (
                    f"  Total invested: ${total_value:,.2f}\n"
                    if positions
                    else "  (empty — no positions)\n"
                )
                + f"  Cash: ${equity - total_value:,.2f}\n"
            )
        except Exception as exc:
            logger.warning("IBKR portfolio snapshot failed: %s", exc)
            return "IBKR offline — portfolio data unavailable"
        finally:
            _loop.close()

    try:
        loop = asyncio.get_running_loop()
        portfolio_context = await asyncio.wait_for(
            loop.run_in_executor(None, _fetch_ibkr_snapshot),
            timeout=8.0,
        )
        _merge_node_update(working_state, output, {"portfolio_snapshot": portfolio_context})
        _mark_step("system_status")
        _mark_step("portfolio_snapshot")
    except Exception as exc:
        logger.warning("IBKR snapshot failed (%s: %s) — falling back to offline", type(exc).__name__, exc)
        _merge_node_update(
            working_state,
            output,
            {"portfolio_snapshot": "IBKR offline — portfolio data unavailable"},
        )
        _mark_step("system_status", {"ibkr": "offline"})

    if ticker:
        for label, node in (
            ("f51", node_f51_verdict),
            ("neural_decision", node_neural_decision),
            ("sdca_firewall", node_sdca_firewall),
            ("rag_forensics", node_rag_forensics),
        ):
            try:
                result = await node(working_state)
                _merge_node_update(working_state, output, result)
            except Exception as exc:
                _merge_node_update(
                    working_state,
                    output,
                    {"errors": [f"auto_full_analysis.{label}:{exc}"]},
                )
    else:
        try:
            result = await node_sdca_firewall(working_state)
            _merge_node_update(working_state, output, result)
        except Exception as exc:
            _merge_node_update(
                working_state,
                output,
                {"errors": [f"auto_full_analysis.sdca_firewall:{exc}"]},
            )

    try:
        result = await node_guardrail_hub(working_state)
        _merge_node_update(working_state, output, result)
        _mark_step("guardrails")
    except Exception as exc:
        _merge_node_update(
            working_state,
            output,
            {"errors": [f"auto_full_analysis.guardrail_hub:{exc}"]},
        )

    writer(
        {
            "type": "PIPELINE_STEP",
            "run_id": run_id,
            "step": "auto_full_analysis",
            "status": "completed",
            "ticker": ticker,
            "has_data": bool(working_state.get("data")),
            "has_scan": bool(working_state.get("scan")),
            "has_f51": bool(working_state.get("f51_verdict")),
            "has_sdca": bool(working_state.get("sdca_firewall")),
            "has_experts": bool(working_state.get("expert_summary")),
            "has_portfolio": bool(working_state.get("portfolio_snapshot")),
            "has_math_report": bool(working_state.get("math_report")),
            "has_guardrail_hub": bool(working_state.get("guardrail_hub")),
        }
    )
    return output


def build_graph(
    gateway=None,
    config=None,
    mandamentos: list[Any] | None = None,
) -> "PipelineApp":
    """Build, compile, and wrap the SuperEzio pipeline graph.

    Returns a PipelineApp instance with shutdown(), chat(), stream_events(),
    and get_status() methods.
    """
    mandamentos = mandamentos or []

    async def _orchestrator(state: dict) -> dict:
        return await node_orchestrator(state, gateway=gateway, config=config)

    async def _auto(state: dict) -> dict:
        return await _auto_full_analysis(state, gateway=gateway, config=config)

    async def _trinity(state: dict) -> dict:
        return await node_trinity(state, gateway=gateway)

    async def _agent(state: dict) -> dict:
        return await node_agent(state, gateway=gateway, config=config, mandamentos=mandamentos)

    async def _tool_executor(state: dict) -> dict:
        return await node_tool_executor(state, gateway=gateway, config=config)

    async def _auto_execute_paper(state: dict) -> dict:
        """Auto-submit paper orders when Bob produces a PAPER_TICKET.

        Parses the agent's final_answer for ticker/shares/action and
        calls the IBKR paper adapter to place the order in TWS.
        """
        import os as _os
        import re
        from collections import deque
        from pathlib import Path
        from langgraph.config import get_stream_writer
        from core.pipeline.nodes.tool_executor import _submit_paper_order

        # Dedup: only execute once per run_id (agent loop can trigger this node multiple times)
        _EXECUTED: deque[str] = deque(maxlen=32)
        _dedup_key = f"paper_{state.get('run_id', '')}"

        # Enable paper order submission for this pipeline execution
        _os.environ.setdefault("SUPEREZIO_ENABLE_PAPER_ORDER_SUBMIT", "1")

        writer = get_stream_writer()
        run_id = state.get("run_id", "")

        writer(
            {
                "type": "PIPELINE_STEP",
                "run_id": run_id,
                "step": "auto_execute_paper",
                "status": "started",
            }
        )

        # ── Dedup guard: agent loop can trigger this node multiple times ──
        if _dedup_key in _EXECUTED:
            writer(
                {
                    "type": "PIPELINE_STEP",
                    "run_id": run_id,
                    "step": "auto_execute_paper",
                    "status": "skipped",
                    "reason": "already_executed_for_this_run",
                }
            )
            return {}
        _EXECUTED.append(_dedup_key)

        final = state.get("final_answer", "")
        scan = state.get("scan") or {}
        candidates = scan.get("candidates", []) if isinstance(scan, dict) else []

        # ── Gate: respect Bob's verdict ──
        # Check trade_order_context first (authoritative), then final_answer text
        trade_ctx = state.get("trade_order_context") or {}
        bob_decision = str(trade_ctx.get("decision", "")).upper()
        final_text = (state.get("final") or state.get("final_answer") or "").lower()
        bob_says_wait_or_reject = (
            bob_decision in ("WAIT", "REJECT_ALL")
            or re.search(r"(?:final|model)\s*verdict\s*:\s*(?:wait|reject)", final_text)
            or re.search(r"decisao\s*(?:final|correta)\s*[:\w]*\s*(?:wait|reject)", final_text)
        )
        if bob_says_wait_or_reject:
            writer(
                {
                    "type": "PIPELINE_STEP",
                    "run_id": run_id,
                    "step": "auto_execute_paper",
                    "status": "skipped",
                    "reason": "bob_verdict_blocks_execution",
                }
            )
            return {}

        # ── Strategy 0: Tool already executed the order ──
        if state.get("submit_paper_order_result"):
            result = state["submit_paper_order_result"]
            ticker = str(result.get("symbol", result.get("ticker", ""))).upper()
            qty = int(result.get("qty", result.get("quantity", 10)) or 10)
            action = str(result.get("action", "buy")).lower()
            if ticker and qty > 0:
                # Order already placed by tool_executor — just log and pass through
                writer({
                    "type": "PIPELINE_STEP", "run_id": run_id,
                    "step": "auto_execute_paper", "status": "completed",
                    "ticker": ticker, "action": action, "qty": qty,
                    "mode": "tool_already_executed",
                })
                return {
                    "submit_paper_order_result": result,
                    "paper_order_executed": True,
                }

        # ── Strategy 1: PAPER_TICKET in Bob's response ──
        if final and "PAPER_TICKET" in final:
            ticker_match = re.search(r"(?:Ticker|ticker):\s*([A-Z]{1,5}(?:\.[A-Z]{2})?)", final)
            ticker = ticker_match.group(1) if ticker_match else state.get("ticker", "")
            qty_match = re.search(r"(?:quantity|qty|shares|Estimated quantity):\s*([\d,.]+)", final)
            qty = float(qty_match.group(1).replace(",", "")) if qty_match else 10
            action = "sell" if "SELL" in final or "short" in final.lower() else "buy"

        # ── Strategy 2: Fallback — pick top scan candidate ──
        elif candidates and state.get("route") in ("market_scan",):
            top = candidates[0] if isinstance(candidates[0], dict) else {}
            ticker = str(top.get("ticker", top.get("symbol", ""))).upper()
            if not ticker:
                writer(
                    {
                        "type": "PIPELINE_STEP",
                        "run_id": run_id,
                        "step": "auto_execute_paper",
                        "status": "skipped",
                        "reason": "no_ticker_in_scan_candidates",
                    }
                )
                return {}
            price = float(top.get("price", top.get("latest_price", 0)) or 0)
            qty = max(1, int(1000 / price)) if price > 0 else 10
            action = "buy"

        # ── Strategy 3: Direct ticker order (compre SNDL, buy PLUG, etc.) ──
        elif state.get("ticker") and state.get("route") in ("ticker_analysis",):
            ticker = str(state.get("ticker", "")).upper()
            # Parse quantity from message or final answer
            qty_match = re.search(
                r"(\d+)\s*(?:share|acao|acoes|shares)",
                final or state.get("message", ""),
                re.IGNORECASE,
            )
            qty = int(qty_match.group(1)) if qty_match else 5
            action = (
                "sell"
                if any(w in (final or "").lower() for w in ("venda", "vender", "sell", "short"))
                else "buy"
            )

        # ── Strategy 4: Any ticker + trade intent → EXECUTE DIRECTLY ──
        elif state.get("ticker") and any(
            w in (state.get("message", "")).lower()
            for w in ("compr", "buy", "venda", "sell", "trade", "ordem", "paper")
        ):
            ticker = str(state.get("ticker", "")).upper()
            qty_match = re.search(
                r"(\d+)\s*(?:share|acao|acoes|shares)",
                final or state.get("message", ""), re.IGNORECASE
            )
            qty = int(qty_match.group(1)) if qty_match else 10
            action = (
                "sell" if any(w in (final or state.get("message","")).lower()
                             for w in ("venda", "vender", "sell", "short"))
                else "buy"
            )
        else:
            writer(
                {
                    "type": "PIPELINE_STEP",
                    "run_id": run_id,
                    "step": "auto_execute_paper",
                    "status": "skipped",
                    "reason": "no_paper_ticket_or_scan_or_direct_order",
                }
            )
            return {}

        if not ticker:
            writer(
                {
                    "type": "PIPELINE_STEP",
                    "run_id": run_id,
                    "step": "auto_execute_paper",
                    "status": "skipped",
                    "reason": "no_ticker_parsed",
                }
            )
            return {"paper_exec_note": "no ticker parsed"}

        # ── Position sizing: max 10% of paper equity per trade ──
        from core.mission_context import get_mission_equity
        paper_equity = get_mission_equity()
        # Price source: scan candidates → state latest_price → IBKR execution fill
        # IBKR paper accounts lack real-time market data subscriptions (Error 10089).
        # The actual fill price comes from IBKR at execution via _ibkr_order.py.
        # DataHub (Finnhub) latency: ~1-2s at best, ~15min at worst.
        limit_price = 0.0
        data_age_s = 0
        if isinstance(scan, dict):
            for c in scan.get("candidates") or []:
                if isinstance(c, dict) and str(c.get("ticker", "")).upper() == ticker:
                    limit_price = float(c.get("price", c.get("latest_price", 0)) or 0)
                    collected = c.get("collected_at") or scan.get("collected_at") or ""
                    if collected:
                        try:
                            from datetime import datetime, timezone

                            collected_dt = datetime.fromisoformat(
                                str(collected).replace("Z", "+00:00")
                            )
                            data_age_s = (datetime.now(timezone.utc) - collected_dt).total_seconds()
                        except Exception:
                            pass
                    break
        if limit_price <= 0:
            limit_price = float(state.get("latest_price", 0)) or 0

        if limit_price > 0:
            try:
                from core.trading.position_sizer import PositionSizer

                requested_qty = int(qty)
                size = PositionSizer(equity=paper_equity).size(entry_price=limit_price)
                if size.shares <= 0:
                    writer(
                        {
                            "type": "PIPELINE_STEP",
                            "run_id": run_id,
                            "step": "auto_execute_paper",
                            "status": "skipped",
                            "reason": f"position_sizer_blocked:{size.size_reason}",
                        }
                    )
                    return {"paper_exec_blocked": f"position_sizer:{size.size_reason}"}
                if requested_qty > size.shares:
                    qty = max(1, size.shares)
                    writer(
                        {
                            "type": "POSITION_SIZE_ADJUSTED",
                            "run_id": run_id,
                            "ticker": ticker,
                            "requested_qty": requested_qty,
                            "approved_qty": qty,
                            "reason": size.size_reason,
                        }
                    )
            except Exception as exc:
                writer(
                    {
                        "type": "PIPELINE_STEP",
                        "run_id": run_id,
                        "step": "auto_execute_paper",
                        "status": "skipped",
                        "reason": f"position_sizer_error:{str(exc)[:120]}",
                    }
                )
                return {"paper_exec_blocked": f"position_sizer_error:{exc}"}
        position_value = qty * (limit_price if limit_price > 0 else 100)

        # ── Concentration gate: block if ticker already >50% of equity ──
        # Uses subprocess to avoid ib_insync event loop conflicts
        concentration_blocked = False
        try:
            import subprocess as _sp
            import sys as _sys
            import json as _json

            check_script = str(
                Path(__file__).resolve().parent.parent.parent.parent.parent
                / "scripts"
                / "_ibkr_position_check.py"
            )
            proc = _sp.run(
                [_sys.executable, check_script, ticker],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if proc.returncode == 0:
                data = _json.loads(proc.stdout.strip())
                existing_pct = data.get("pct_of_equity", 0)
                from core.mission_context import get_mission_equity
                new_total_pct = existing_pct + (position_value / data.get("equity", get_mission_equity()) * 100)
                if new_total_pct > 50:
                    concentration_blocked = True
                    writer(
                        {
                            "type": "PIPELINE_STEP",
                            "run_id": run_id,
                            "step": "auto_execute_paper",
                            "status": "skipped",
                            "reason": f"concentration_gate:{ticker}_at_{existing_pct:.0f}pct_would_be_{new_total_pct:.0f}pct",
                            "existing_pct": round(existing_pct, 1),
                            "new_total_pct": round(new_total_pct, 1),
                        }
                    )
        except Exception:
            pass

        if concentration_blocked:
            return {"paper_exec_blocked": f"concentration:{ticker}"}

        try:
            from core.trading.kill_switch import get_kill_switch

            kill_state = get_kill_switch().check()
            if kill_state.is_active:
                reason = kill_state.reason.value if kill_state.reason else "unknown"
                writer(
                    {
                        "type": "PAPER_ORDER_BLOCKED",
                        "run_id": run_id,
                        "ticker": ticker,
                        "step": "auto_execute_paper",
                        "status": "blocked",
                        "reason": f"kill_switch_active:{reason}",
                        "daily_pnl": kill_state.daily_pnl,
                        "trade_count": kill_state.trade_count,
                    }
                )
                return {
                    "paper_exec_blocked": f"kill_switch:{reason}",
                    "submit_paper_order_error": f"kill_switch_active:{reason}",
                }
        except Exception as exc:
            logger.warning("kill switch preflight unavailable: %s", exc)

        writer(
            {
                "type": "PAPER_EXEC",
                "run_id": run_id,
                "ticker": ticker,
                "action": action,
                "qty": qty,
                "limit_price": limit_price,
                "position_value": round(position_value, 2),
                "max_position_pct": 10,
                "data_age_s": round(data_age_s, 1),
                "data_source": "datahub_scan" if limit_price > 0 else "fallback",
            }
        )

        # Paper order submission requires:
        # - ticket_allowed=True in state (cognitive contract)
        # - order_type=LMT (limit order, safer for paper)
        # - limit_price from scan data or default near current price
        order_state = {**state, "ticket_allowed": True}
        if limit_price <= 0:
            limit_price = 99.0  # fallback — will likely not fill, which is safer than bad fill

        result = await _submit_paper_order(
            order_state,
            {
                "ticker": ticker,
                "action": action,
                "qty": qty,
                "order_type": "LMT",
                "limit_price": limit_price,
            },
        )

        # ── Record in paper journal (audit trail) ──
        journal_entry = None
        try:
            from core.trading.paper_journal import PaperJournal, PaperTrade
            from datetime import datetime, timezone

            journal = PaperJournal()

            if action in ("sell", "SELL"):
                # Auto-close: find open trade for this ticker and close it
                open_trades = journal.list_open()
                closed = None
                for ot in open_trades:
                    if ot.get("ticker") == ticker:
                        # Use fill price from IBKR result if available
                        fill_price = limit_price
                        so = result.get("submit_paper_order_result", {})
                        if so.get("avg_price") and so["avg_price"] > 0:
                            fill_price = float(so["avg_price"])
                        closed = journal.close_trade(
                            ot["trade_id"],
                            exit_price=fill_price,
                            exit_reason="auto_sell",
                            exit_date=datetime.now(timezone.utc).isoformat(),
                        )
                        if closed:
                            journal.add_reflection(
                                ot["trade_id"],
                                thesis_correct=(closed.outcome == "win"),
                                what_went_right="Auto-closed by sell order"
                                if closed.outcome == "win"
                                else "",
                                what_went_wrong="Auto-closed — loss"
                                if closed.outcome == "loss"
                                else "",
                                lesson_learned=f"Auto trade: {ticker} {'won' if closed.outcome == 'win' else 'lost'} ${abs(closed.pnl_amount or 0):.2f}",
                            )

                            # Trigger learning cycle after trade close (async, non-blocking)
                            try:
                                import threading

                                def _run_learning_cycle():
                                    try:
                                        from core.trading.feedback_loop import get_feedback_loop
                                        fb = get_feedback_loop()
                                        fb.run_learning_cycle()
                                        logger.info("[learning] Cycle completed after closing %s", ot["trade_id"])
                                    except Exception as e:
                                        logger.warning("[learning] Cycle failed after trade close: %s", e)

                                # Run in background thread to not block the pipeline
                                threading.Thread(target=_run_learning_cycle, daemon=True).start()
                            except Exception as exc:
                                logger.debug("[learning] Failed to trigger learning cycle: %s", exc)

                        journal_entry = f"closed:{ot['trade_id']}"
                        break
                if not closed:
                    journal_entry = f"no_open_trade_for:{ticker}"
            else:
                trade = PaperTrade(
                    trade_id=f"bob-{run_id[:12]}" if run_id else f"bob-{int(time.time())}",
                    ticker=ticker,
                    thesis=state.get("message", "Auto-executed paper trade")[:200],
                    direction=action,
                    entry_date=datetime.now(timezone.utc).isoformat(),
                    entry_price=limit_price,
                    shares=qty,
                    entry_reasoning=f"auto_execute_paper | route={state.get('route', '?')} | run_id={run_id}",
                    verdict_at_entry=bob_decision or "auto",
                    risk_assessment=state.get("risk_tolerance", "moderada"),
                    expected_holding_period="swing",
                )
                journal.open_trade(trade)
                journal_entry = trade.trade_id
        except Exception as exc:
            journal_entry = f"journal_error:{exc}"

        writer(
            {
                "type": "PIPELINE_STEP",
                "run_id": run_id,
                "step": "auto_execute_paper",
                "status": "completed",
                "result": result,
                "journal_entry": journal_entry,
            }
        )

        return {
            "paper_exec_result": result,
            "paper_exec_ticker": ticker,
            "paper_exec_qty": qty,
            "paper_journal_entry": journal_entry,
        }

    async def _explanation(state: dict) -> dict:
        return await node_explanation(state)

    async def _blocked(state: dict) -> dict:
        return await node_blocked(state)

    builder = StateGraph(PipelineState)

    builder.add_node("orchestrator_primary", _orchestrator)
    builder.add_node("auto_full_analysis", _auto)
    builder.add_node("trinity", _trinity)
    builder.add_node("agent", _agent)
    builder.add_node("auto_execute_paper", _auto_execute_paper)
    builder.add_node("tool_executor", _tool_executor)
    builder.add_node("explanation", _explanation)
    builder.add_node("respond_blocked", _blocked)

    builder.add_edge(START, "orchestrator_primary")
    builder.add_conditional_edges(
        "orchestrator_primary",
        route_after_orchestrator,
        {
            "respond_blocked": "respond_blocked",
            "agent": "auto_full_analysis",
        },
    )
    # After full analysis, run Trinity deliberation before Bob sees the state.
    builder.add_edge("auto_full_analysis", "trinity")
    builder.add_conditional_edges(
        "trinity",
        route_after_trinity,
        {
            "agent": "agent",
            "respond_blocked": "respond_blocked",
        },
    )

    # Agent decides whether to call a tool or output the final answer.
    # Route through auto_execute_paper before explanation so paper orders
    # are auto-submitted to IBKR when Bob produces a PAPER_TICKET.
    builder.add_conditional_edges(
        "agent",
        route_after_agent,
        {
            "tool_executor": "tool_executor",
            "explanation": "auto_execute_paper",
        },
    )

    # After a tool executes, return control to the agent
    builder.add_edge("tool_executor", "agent")

    # Auto-execute paper orders, then go to explanation
    builder.add_edge("auto_execute_paper", "explanation")

    builder.add_edge("explanation", END)
    builder.add_edge("respond_blocked", END)

    compiled = builder.compile()
    return PipelineApp(
        graph=compiled,
        gateway=gateway,
        config=config,
        mandamentos=mandamentos,
    )


class PipelineApp:
    """Production wrapper around CompiledStateGraph.

    Provides the public API expected by agent_server:
    - shutdown(): graceful teardown
    - stream_events(): async event stream
    - chat() / chat_sync(): convenience methods
    - get_status(): health/status dict
    """

    def __init__(
        self,
        graph,
        gateway=None,
        config=None,
        mandamentos: list[Any] | None = None,
    ):
        self.graph = graph
        self.gateway = gateway
        self.config = config
        self.mandamentos = mandamentos or []
        self._shutting_down = False

    def shutdown(self) -> None:
        logger.info("PipelineApp shutting down...")
        self._shutting_down = True
        if self.gateway:
            try:
                self.gateway.unload_all()
            except Exception as exc:
                logger.warning("Gateway unload error during shutdown: %s", exc)

    async def stream_events(
        self,
        message: str,
        context: str = "",
        session_id: str = "default",
        memory_mode: str = "relevant_all",
        rigor: str = "strict",
        ticker: str = "",
        trade_order_context: dict[str, Any] | None = None,
    ) -> AsyncGenerator[dict[str, Any], None]:
        run_id = uuid.uuid4().hex[:12]

        evidence: EvidenceRun | None = None
        evidence_saved = False
        response_chunks: list[str] = []
        try:
            evidence = EvidenceRun(prompt=message, ticker=ticker)
            evidence.start()
        except Exception:
            pass

        # ── Bob Memory: UnifiedRetriever com perfil + contexto formatado ──
        try:
            from core.memory import get_unified_retriever

            retriever = get_unified_retriever()

            # 1. Extrai/atualiza perfil da mensagem
            profile_updates = retriever.extract_profile_from_message(message)
            for key, value, confidence in profile_updates:
                retriever.upsert_profile(key, value, confidence)

            # 2. Renderiza contexto completo no formato EXATO
            memory_context = retriever.render_memory_context(
                session_id=session_id,
                message=message,
                ticker=ticker,
            )

            # 3. Injeta no context (antes do prompt do Bob)
            if memory_context:
                context = f"{memory_context}\n\n{context}" if context else memory_context

            # 4. Injeta lições aprendidas do FeedbackLoop
            try:
                from core.trading.feedback_loop import get_feedback_loop
                fb_loop = get_feedback_loop()
                if fb_loop:
                    learning_context = fb_loop.render_for_bob(max_chars=1000)
                    if learning_context:
                        context = f"{context}\n\n{learning_context}" if context else learning_context
                        logger.debug("[memory] Injected learning context (%d chars)", len(learning_context))
            except Exception as exc:
                logger.debug("[memory] Failed to load learning context: %s", exc)

        except Exception as exc:
            logger.warning("[memory] Failed to load unified context: %s", exc)

        def _finalize_evidence() -> None:
            nonlocal evidence_saved
            if evidence is None or evidence_saved:
                return
            try:
                if response_chunks and not evidence.response:
                    response_text = "".join(response_chunks)
                    evidence.record_response(
                        response_text=response_text,
                        tokens=len(response_text.split()),
                    )
                evidence.finish()
                run_dir = save_evidence(evidence)
                generate_html_report(evidence, run_dir)
                evidence_saved = True
                logger.info("[evidence] Saved: %s", run_dir)
            except Exception as exc:
                logger.warning("[evidence] Save failed: %s", exc)

        initial: dict[str, Any] = {
            "run_id": run_id,
            "message": message,
            "context": context,
            "session_id": session_id,
            "memory_mode": memory_mode,
            "rigor": rigor,
            "errors": [],
        }
        if ticker:
            initial["ticker"] = ticker
        if trade_order_context:
            initial["trade_order_context"] = trade_order_context

        yield {
            "type": "PIPELINE_STEP",
            "run_id": run_id,
            "step": "graph",
            "status": "started",
        }

        try:
            async for item in self.graph.astream(
                initial,
                stream_mode=["custom", "updates"],
            ):
                if isinstance(item, dict):
                    mode = item.get("type", "")
                    payload = item.get("data")
                elif isinstance(item, tuple) and len(item) == 2:
                    mode, payload = item
                else:
                    continue

                if mode == "custom":
                    if isinstance(payload, dict):
                        payload.setdefault("run_id", run_id)

                        # Evidence: capture pipeline events.
                        if evidence is not None:
                            evt_type = payload.get("type", "")
                            try:
                                if evt_type in {"CHUNK", "EXPLANATION_CHUNK"} and payload.get(
                                    "content"
                                ):
                                    response_chunks.append(str(payload.get("content", "")))
                                if evt_type == "DATA_COLLECTED":
                                    provider = payload.get("provider") or (
                                        ", ".join(payload.get("providers") or []) or "scanner"
                                    )
                                    capability = payload.get("capability") or payload.get(
                                        "quality", "market_data"
                                    )
                                    evidence.record_source(
                                        provider=provider,
                                        capability=capability,
                                        status=payload.get("status", "collected"),
                                        data=payload,
                                    )
                                elif evt_type == "SCAN_COMPLETE":
                                    evidence.record_scan(
                                        candidates=payload.get("candidates", []),
                                        rejected=payload.get("rejected", 0),
                                        sources_used=payload.get("sources", []),
                                    )
                                elif evt_type == "EXPERT_COMPLETE":
                                    evidence.record_expert(
                                        expert_name=payload.get("expert", "unknown"),
                                        verdict=payload.get("verdict", "?"),
                                        confidence=float(payload.get("confidence", 0)),
                                        provider=payload.get("provider", "unknown"),
                                        bob_readable=payload.get("bob_readable", ""),
                                    )
                                elif evt_type == "SDCA_COMPLETE":
                                    evidence.record_risk(payload)
                                elif evt_type == "F51_VERDICT":
                                    evidence.record_verdict(payload)
                            except Exception:
                                pass

                        yield payload
                    elif payload is not None:
                        yield {
                            "type": "CHUNK",
                            "run_id": run_id,
                            "content": str(payload),
                        }
                elif mode == "updates":
                    # Evidence: capture node outputs from updates.
                    if evidence is not None and isinstance(payload, dict):
                        try:
                            for node_name, node_output in payload.items():
                                if isinstance(node_output, dict):
                                    if node_name == "explanation" and node_output.get(
                                        "explanation"
                                    ):
                                        evidence.record_response(
                                            response_text=str(node_output["explanation"]),
                                            tokens=len(str(node_output["explanation"]).split()),
                                        )
                                    scan_payload = _scan_evidence_payload(node_output)
                                    if scan_payload is not None:
                                        candidates, rejected, sources_used = scan_payload
                                        evidence.record_scan(
                                            candidates=candidates,
                                            rejected=rejected,
                                            sources_used=sources_used,
                                        )
                        except Exception:
                            pass
                    continue

            _finalize_evidence()
            yield {
                "type": "PIPELINE_STEP",
                "run_id": run_id,
                "step": "graph",
                "status": "completed",
                "evidence_run_id": evidence.run_id if evidence else None,
            }
        except Exception as exc:
            detail = str(exc) or exc.__class__.__name__
            if evidence is not None:
                try:
                    evidence.record_error("pipeline", detail)
                except Exception:
                    pass
            yield {"type": "ERROR", "run_id": run_id, "detail": detail[:500]}

        finally:
            _finalize_evidence()

            # ── Bob Memory: salva turno + inger no Knowledge Graph ──
            if response_chunks:
                try:
                    from core.memory import (
                        get_conversation_memory,
                        get_graph_bridge,
                    )

                    mem = get_conversation_memory()
                    response_text = "".join(response_chunks)

                    # Extrai metadados da resposta
                    category = "general"
                    verdict = ""
                    confidence = 0.0
                    thesis = ""

                    # Tenta extrair veredito do final_answer
                    if "Model verdict:" in response_text or "Final verdict:" in response_text:
                        for line in response_text.split("\n"):
                            if "Model verdict:" in line or "Final verdict:" in line:
                                verdict = line.split(":")[-1].strip().upper()
                                break

                    # Tenta extrair confiança
                    import re
                    conf_match = re.search(r"Confidence:\s*(\d+)", response_text)
                    if conf_match:
                        confidence = float(conf_match.group(1))

                    # Detecta categoria baseada no state
                    if ticker:
                        category = "ticker_analysis"
                    elif "scan" in context.lower() or "candidates" in response_text.lower():
                        category = "market_scan"

                    # Cria turno
                    turn = mem.add_turn(
                        session_id=session_id,
                        user_message=message,
                        bob_response=response_text[:5000],
                        context_summary=context[:500] if context else "",
                        ticker_discussed=ticker,
                        thesis_formed=thesis,
                        verdict=verdict,
                        confidence=confidence,
                        category=category,
                    )
                    logger.debug("[memory] Saved turn for session %s", session_id)

                    # ── Knowledge Graph: ingere turno (Fase 4) ──
                    try:
                        graph_bridge = get_graph_bridge()
                        graph_bridge.ingest_conversation_turn(turn)
                        logger.debug("[memory] Ingested turn into knowledge graph")
                    except Exception as e:
                        logger.debug("[memory] Graph ingestion skipped: %s", e)

                except Exception as exc:
                    logger.warning("[memory] Failed to save conversation turn: %s", exc)

    async def chat_async(
        self,
        message: str,
        context: str = "",
        session_id: str = "default",
        memory_mode: str = "relevant_all",
        rigor: str = "strict",
        ticker: str = "",
        trade_order_context: dict[str, Any] | None = None,
    ) -> AsyncGenerator[str, None]:
        async for event in self.stream_events(
            message,
            context=context,
            session_id=session_id,
            memory_mode=memory_mode,
            rigor=rigor,
            ticker=ticker,
            trade_order_context=trade_order_context,
        ):
            if event.get("type") == "CHUNK":
                yield str(event.get("content", ""))
            elif event.get("type") == "ERROR":
                yield f"[ERROR] {event.get('detail', '')}"

    def chat(self, message: str, context: str = "") -> Generator[str, None, None]:
        yield _run_async(self._chat_collect_async(message, context))

    async def _chat_collect_async(self, message: str, context: str = "") -> str:
        chunks: list[str] = []
        async for chunk in self.chat_async(message, context):
            chunks.append(chunk)
        return "".join(chunks)

    def chat_sync(self, message: str, context: str = "") -> str:
        return _run_async(self._chat_collect_async(message, context))

    def get_status(self) -> dict[str, Any]:
        return {
            "mode": "pipeline_v4_stategraph",
            "nodes": [
                "orchestrator_primary",
                "auto_full_analysis",
                "trinity",
                "math_hub",
                "guardrail_hub",
                "agent",
                "tool_executor",
                "explanation",
                "respond_blocked",
            ],
            "gateway_available": self.gateway is not None,
            "providers": ([p.name for p in self.gateway.providers] if self.gateway else []),
            "mandamentos_count": len(self.mandamentos),
        }


def _run_async(coro):
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)

    import concurrent.futures

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(asyncio.run, coro)
        return future.result()
