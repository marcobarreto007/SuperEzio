"""Auto-execute paper orders — extracted from graph.py inner function.

Handles: ticker/qty resolution, position sizing, concentration gate,
kill switch, IBKR submission, paper journal, and learning cycle trigger.
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
import subprocess
import sys
import time
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from langgraph.config import get_stream_writer

logger = logging.getLogger(__name__)

# Dedup guard: only execute once per run_id
_EXECUTED: deque[str] = deque(maxlen=32)


async def auto_execute_paper(state: dict) -> dict:
    """Auto-submit paper orders when Bob produces a PAPER_TICKET.

    Parses the agent's final_answer for ticker/shares/action and
    calls the IBKR paper adapter to place the order in TWS.
    """
    import json as _json
    from core.pipeline.nodes.tool_executor import _submit_paper_order

    # Enable paper order submission for this pipeline execution
    os.environ.setdefault("SUPEREZIO_ENABLE_PAPER_ORDER_SUBMIT", "1")

    writer = get_stream_writer()
    run_id = state.get("run_id", "")

    writer({
        "type": "PIPELINE_STEP",
        "run_id": run_id,
        "step": "auto_execute_paper",
        "status": "started",
    })

    # Dedup guard
    dedup_key = f"paper_{run_id}"
    if dedup_key in _EXECUTED:
        writer({
            "type": "PIPELINE_STEP", "run_id": run_id,
            "step": "auto_execute_paper", "status": "skipped",
            "reason": "already_executed_for_this_run",
        })
        return {}
    _EXECUTED.append(dedup_key)

    final = state.get("final_answer", "")
    scan = state.get("scan") or {}
    candidates = scan.get("candidates", []) if isinstance(scan, dict) else []

    # Gate: respect Bob's verdict
    ticker, qty, action = _resolve_trade_params(state, final, candidates)

    if ticker is None:
        return {}

    if not ticker:
        writer({
            "type": "PIPELINE_STEP", "run_id": run_id,
            "step": "auto_execute_paper", "status": "skipped",
            "reason": "no_ticker_resolved",
        })
        return {"paper_exec_note": "no ticker parsed"}

    # Position sizing
    limit_price, data_age_s = _resolve_limit_price(state, scan, ticker)
    from core.mission_context import get_mission_equity
    paper_equity = get_mission_equity()

    try:
        from core.trading.position_sizer import PositionSizer
        if limit_price > 0:
            size = PositionSizer(equity=paper_equity).size(entry_price=limit_price)
            if size.shares <= 0:
                writer({
                    "type": "PIPELINE_STEP", "run_id": run_id,
                    "step": "auto_execute_paper", "status": "skipped",
                    "reason": f"position_sizer_blocked:{size.size_reason}",
                })
                return {"paper_exec_blocked": f"position_sizer:{size.size_reason}"}
            if int(qty) > size.shares:
                qty = max(1, size.shares)
                writer({
                    "type": "POSITION_SIZE_ADJUSTED", "run_id": run_id,
                    "ticker": ticker, "requested_qty": int(qty),
                    "approved_qty": qty, "reason": size.size_reason,
                })
    except Exception as exc:
        writer({
            "type": "PIPELINE_STEP", "run_id": run_id,
            "step": "auto_execute_paper", "status": "skipped",
            "reason": f"position_sizer_error:{str(exc)[:120]}",
        })
        return {"paper_exec_blocked": f"position_sizer_error:{exc}"}

    position_value = qty * (limit_price if limit_price > 0 else 100)

    # Concentration gate
    if _check_concentration(ticker, position_value, run_id):
        return {"paper_exec_blocked": f"concentration:{ticker}"}

    # Kill switch
    try:
        from core.trading.kill_switch import get_kill_switch
        kill_state = get_kill_switch().check()
        if kill_state.is_active:
            reason = kill_state.reason.value if kill_state.reason else "unknown"
            writer({
                "type": "PAPER_ORDER_BLOCKED", "run_id": run_id,
                "ticker": ticker, "step": "auto_execute_paper",
                "status": "blocked", "reason": f"kill_switch_active:{reason}",
            })
            return {
                "paper_exec_blocked": f"kill_switch:{reason}",
                "submit_paper_order_error": f"kill_switch_active:{reason}",
            }
    except Exception as exc:
        logger.warning("kill switch preflight unavailable: %s", exc)

    writer({
        "type": "PAPER_EXEC", "run_id": run_id, "ticker": ticker,
        "action": action, "qty": qty, "limit_price": limit_price,
        "position_value": round(position_value, 2),
        "max_position_pct": 10, "data_age_s": round(data_age_s, 1),
        "data_source": "datahub_scan" if limit_price > 0 else "fallback",
    })

    # Submit paper order
    order_state = {**state, "ticket_allowed": True}
    if limit_price <= 0:
        limit_price = 99.0

    result = await _submit_paper_order(
        order_state,
        {
            "ticker": ticker, "action": action, "qty": qty,
            "order_type": "LMT", "limit_price": limit_price,
        },
    )

    # Paper journal audit trail
    journal_entry = _journal_trade(state, result, ticker, action, qty, limit_price, run_id)

    writer({
        "type": "PIPELINE_STEP", "run_id": run_id,
        "step": "auto_execute_paper", "status": "completed",
        "result": result, "journal_entry": journal_entry,
    })

    return {
        "paper_exec_result": result,
        "paper_exec_ticker": ticker,
        "paper_exec_qty": qty,
        "paper_journal_entry": journal_entry,
    }


def _resolve_trade_params(
    state: dict, final: str, candidates: list[dict]
) -> tuple[str | None, int, str]:
    """Resolve ticker, qty, and action from state/final_answer/candidates."""
    # Gate: respect Bob's verdict
    trade_ctx = state.get("trade_order_context") or {}
    bob_decision = str(trade_ctx.get("decision", "")).upper()
    final_text = (state.get("final") or state.get("final_answer") or "").lower()
    bob_says_wait_or_reject = (
        bob_decision in ("WAIT", "REJECT_ALL")
        or re.search(r"(?:final|model)\s*verdict\s*:\s*(?:wait|reject)", final_text)
        or re.search(r"decisao\s*(?:final|correta)\s*[:\w]*\s*(?:wait|reject)", final_text)
    )
    if bob_says_wait_or_reject:
        return None, 0, ""

    # Strategy 0: Tool already executed
    if state.get("submit_paper_order_result"):
        result = state["submit_paper_order_result"]
        ticker = str(result.get("symbol", result.get("ticker", ""))).upper()
        qty = int(result.get("qty", result.get("quantity", 10)) or 10)
        action = str(result.get("action", "buy")).lower()
        if ticker and qty > 0:
            return ticker, qty, action

    # Strategy 1: PAPER_TICKET in Bob's response
    if final and "PAPER_TICKET" in final:
        ticker_match = re.search(r"(?:Ticker|ticker):\s*([A-Z]{1,5}(?:\.[A-Z]{2})?)", final)
        ticker = ticker_match.group(1) if ticker_match else state.get("ticker", "")
        qty_match = re.search(r"(?:quantity|qty|shares|Estimated quantity):\s*([\d,.]+)", final)
        qty = float(qty_match.group(1).replace(",", "")) if qty_match else 10
        action = "sell" if "SELL" in final or "short" in final.lower() else "buy"
        return str(ticker).upper(), int(qty), action

    # Strategy 2: Top scan candidate
    if candidates and state.get("route") in ("market_scan",):
        top = candidates[0] if isinstance(candidates[0], dict) else {}
        ticker = str(top.get("ticker", top.get("symbol", ""))).upper()
        if not ticker:
            return None, 0, ""
        price = float(top.get("price", top.get("latest_price", 0)) or 0)
        qty = max(1, int(1000 / price)) if price > 0 else 10
        return ticker, qty, "buy"

    # Strategy 3: Direct ticker order
    if state.get("ticker") and state.get("route") in ("ticker_analysis",):
        ticker = str(state.get("ticker", "")).upper()
        qty_match = re.search(
            r"(\d+)\s*(?:share|acao|acoes|shares)",
            final or state.get("message", ""), re.IGNORECASE,
        )
        qty = int(qty_match.group(1)) if qty_match else 5
        action = (
            "sell" if any(w in (final or "").lower() for w in ("venda", "vender", "sell", "short"))
            else "buy"
        )
        return ticker, qty, action

    # Strategy 4: Any ticker + trade intent
    if state.get("ticker") and any(
        w in (state.get("message", "")).lower()
        for w in ("compr", "buy", "venda", "sell", "trade", "ordem", "paper")
    ):
        ticker = str(state.get("ticker", "")).upper()
        qty_match = re.search(
            r"(\d+)\s*(?:share|acao|acoes|shares)",
            final or state.get("message", ""), re.IGNORECASE,
        )
        qty = int(qty_match.group(1)) if qty_match else 10
        action = (
            "sell" if any(w in (final or state.get("message","")).lower()
                         for w in ("venda", "vender", "sell", "short"))
            else "buy"
        )
        return ticker, qty, action

    return None, 0, ""


def _resolve_limit_price(state: dict, scan: dict, ticker: str) -> tuple[float, float]:
    """Resolve limit price from scan data. Returns (price, data_age_seconds)."""
    limit_price = 0.0
    data_age_s = 0
    if isinstance(scan, dict):
        for c in scan.get("candidates") or []:
            if isinstance(c, dict) and str(c.get("ticker", "")).upper() == ticker:
                limit_price = float(c.get("price", c.get("latest_price", 0)) or 0)
                collected = c.get("collected_at") or scan.get("collected_at") or ""
                if collected:
                    try:
                        collected_dt = datetime.fromisoformat(str(collected).replace("Z", "+00:00"))
                        data_age_s = (datetime.now(timezone.utc) - collected_dt).total_seconds()
                    except Exception:
                        pass
                break
    if limit_price <= 0:
        limit_price = float(state.get("latest_price", 0)) or 0
    return limit_price, data_age_s


def _check_concentration(ticker: str, position_value: float, run_id: str) -> bool:
    """Check if adding this position would exceed 50% concentration. Returns True if blocked."""
    try:
        import subprocess as _sp
        import sys as _sys
        import json as _json

        check_script = str(
            Path(__file__).resolve().parent.parent.parent.parent.parent
            / "scripts" / "_ibkr_position_check.py"
        )
        proc = _sp.run(
            [_sys.executable, check_script, ticker],
            capture_output=True, text=True, timeout=10,
        )
        if proc.returncode == 0:
            data = _json.loads(proc.stdout.strip())
            existing_pct = data.get("pct_of_equity", 0)
            from core.mission_context import get_mission_equity
            new_total_pct = existing_pct + (position_value / data.get("equity", get_mission_equity()) * 100)
            if new_total_pct > 50:
                get_stream_writer()({
                    "type": "PIPELINE_STEP", "run_id": run_id,
                    "step": "auto_execute_paper", "status": "skipped",
                    "reason": f"concentration_gate:{ticker}_at_{existing_pct:.0f}pct_would_be_{new_total_pct:.0f}pct",
                })
                return True
    except Exception:
        pass
    return False


def _journal_trade(
    state: dict,
    result: dict,
    ticker: str,
    action: str,
    qty: int,
    limit_price: float,
    run_id: str,
) -> str | None:
    """Record trade in paper journal. Triggers learning cycle on close."""
    try:
        from core.trading.paper_journal import PaperJournal, PaperTrade

        journal = PaperJournal()

        if action in ("sell", "SELL"):
            open_trades = journal.list_open()
            for ot in open_trades:
                if ot.get("ticker") == ticker:
                    fill_price = limit_price
                    so = result.get("submit_paper_order_result", {})
                    if so.get("avg_price") and so["avg_price"] > 0:
                        fill_price = float(so["avg_price"])
                    closed = journal.close_trade(
                        ot["trade_id"], exit_price=fill_price,
                        exit_reason="auto_sell",
                        exit_date=datetime.now(timezone.utc).isoformat(),
                    )
                    if closed:
                        journal.add_reflection(
                            ot["trade_id"],
                            thesis_correct=(closed.outcome == "win"),
                            what_went_right="Auto-closed by sell order" if closed.outcome == "win" else "",
                            what_went_wrong="Auto-closed — loss" if closed.outcome == "loss" else "",
                            lesson_learned=f"Auto trade: {ticker} {'won' if closed.outcome == 'win' else 'lost'} ${abs(closed.pnl_amount or 0):.2f}",
                        )
                        # Background learning cycle
                        import threading
                        def _run_learning_cycle():
                            try:
                                from core.trading.feedback_loop import get_feedback_loop
                                fb = get_feedback_loop()
                                fb.run_learning_cycle()
                                logger.info("[learning] Cycle completed after closing %s", ot["trade_id"])
                            except Exception as e:
                                logger.warning("[learning] Cycle failed: %s", e)
                        threading.Thread(target=_run_learning_cycle, daemon=True).start()
                        return f"closed:{ot['trade_id']}"
            return f"no_open_trade_for:{ticker}"
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
                verdict_at_entry=state.get("trade_order_context", {}).get("decision", "auto"),
                risk_assessment=state.get("risk_tolerance", "moderada"),
                expected_holding_period="swing",
            )
            journal.open_trade(trade)
            return trade.trade_id
    except Exception as exc:
        return f"journal_error:{exc}"
