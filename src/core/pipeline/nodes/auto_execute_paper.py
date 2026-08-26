"""Auto-execute paper orders — extracted from graph.py inner function.

Handles: ticker/qty resolution, position sizing, concentration gate,
kill switch, IBKR submission, paper journal, and learning cycle trigger.
"""

from __future__ import annotations

import json
import math
import re
import time
from collections import deque
from datetime import UTC, datetime
from pathlib import Path

from langgraph.config import get_stream_writer

from core.config.logging_config import bind_trace, get_logger
from core.idempotency import (
    claim_idempotency_keys,
    enqueue_dead_letter,
    is_duplicate,
    make_idempotency_keys,
)
from core.trading.execution_policy import (
    adaptive_sizing_config as _adaptive_sizing_config,
)
from core.trading.execution_policy import (
    evaluate_neural_execution_gate as _evaluate_neural_execution_gate,
)
from core.trading.execution_policy import (
    expert_consensus_block_reason as _expert_consensus_block_reason,
)

logger = get_logger(__name__)

# Dedup guard: memory cache for fast-reject within same process
_EXECUTED: deque[str] = deque(maxlen=64)
# Persistent dedup via idempotency keys in journal/dedup/
_IDEMPOTENCY_WINDOW_MINUTES = 5


async def auto_execute_paper(state: dict) -> dict:
    """Auto-submit paper orders when Bob produces a PAPER_TICKET.

    Parses the agent's final_answer for ticker/shares/action and
    calls the IBKR paper adapter to place the order in TWS.
    """
    from core.pipeline.nodes.tool_executor import _submit_paper_order

    # Paper order submission is controlled by SUPEREZIO_ENABLE_PAPER_ORDER_SUBMIT
    # env var or settings.superezio_enable_paper_order_submit (default False).
    # Do NOT set os.environ here — that would leak into the process environment
    # and override the operator's explicit config (e.g. docker-compose.yml).
    # tool_executor._submit_paper_order reads the env/settings downstream.

    writer = get_stream_writer()
    run_id = state.get("run_id", "")

    # Bind trace context for all logs in this pipeline run
    bind_trace(run_id=run_id)

    writer(
        {
            "type": "PIPELINE_STEP",
            "run_id": run_id,
            "step": "auto_execute_paper",
            "status": "started",
        }
    )

    # Dedup guard — memory cache (fast path)
    dedup_key = f"paper_{run_id}"
    if dedup_key in _EXECUTED:
        logger.info("auto_execute_skipped_dedup_memory", run_id=run_id)
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
    _EXECUTED.append(dedup_key)

    final = state.get("final_answer", "")
    scan = state.get("scan") or {}
    candidates = scan.get("candidates", []) if isinstance(scan, dict) else []

    # Gate: respect Bob's verdict
    ticker, qty, action = _resolve_trade_params(state, final, candidates)

    if ticker is None:
        return {}

    if not ticker:
        writer(
            {
                "type": "PIPELINE_STEP",
                "run_id": run_id,
                "step": "auto_execute_paper",
                "status": "skipped",
                "reason": "no_ticker_resolved",
            }
        )
        return {"paper_exec_note": "no ticker parsed"}

    consensus_block = _expert_consensus_block_reason(state)
    if consensus_block:
        writer(
            {
                "type": "PAPER_ORDER_BLOCKED",
                "run_id": run_id,
                "ticker": ticker,
                "step": "weighted_expert_consensus",
                "status": "blocked",
                "reason": consensus_block,
            }
        )
        return {
            "paper_exec_blocked": "WEIGHTED_EXPERT_CONSENSUS",
            "paper_exec_block_reason": consensus_block,
        }

    neural_gate = _evaluate_neural_execution_gate(state, action)
    if not neural_gate["allowed"]:
        writer(
            {
                "type": "PAPER_ORDER_BLOCKED",
                "run_id": run_id,
                "ticker": ticker,
                "step": "neural_execution_gate",
                "status": "blocked",
                "reason": neural_gate["code"],
                "evidence": neural_gate,
            }
        )
        return {
            "paper_exec_blocked": neural_gate["code"],
            "paper_exec_block_reason": "neural forecast is not execution-eligible",
            "neural_gate": neural_gate,
        }

    # ═══════════════════════════════════════════════════════════
    # F51 TRADE GATE — Central safety validator (ALL 10 gates)
    # Must pass BEFORE any order proceeds. Fails CLOSED.
    # ═══════════════════════════════════════════════════════════
    limit_price, data_age_s = _resolve_limit_price(state, scan, ticker)

    # ═══════════════════════════════════════════════════════════
    # IDEMPOTENCY CHECK — Persistent dedup across restarts
    # ═══════════════════════════════════════════════════════════
    idem_keys = make_idempotency_keys(
        ticker=ticker,
        qty=qty,
        limit_price=limit_price,
        window_minutes=_IDEMPOTENCY_WINDOW_MINUTES,
    )
    # idem_keys[0] is the current window and stays the key we log and report;
    # idem_keys[1] is the previous window, which closes the boundary hole where
    # a retry seconds later would otherwise mint a brand-new key.
    idem_key = idem_keys[0]
    if any(is_duplicate(key) for key in idem_keys):
        logger.warning(
            "auto_execute_duplicate_blocked",
            ticker=ticker,
            qty=qty,
            limit_price=limit_price,
            idempotency_key=idem_key,
        )
        writer(
            {
                "type": "PAPER_ORDER_BLOCKED",
                "run_id": run_id,
                "ticker": ticker,
                "step": "idempotency",
                "status": "blocked",
                "reason": f"Duplicate order detected: {idem_key}",
            }
        )
        return {
            "paper_exec_blocked": "DUPLICATE_ORDER",
            "paper_exec_block_reason": f"Idempotency key already processed: {idem_key}",
        }

    try:
        from core.pipeline.f51_trade_gate import evaluate_trade_gate, record_blocked_order

        message = str(state.get("message", "") or "")
        thesis_ticker = _extract_thesis_ticker(final, state, ticker)

        gate_decision = evaluate_trade_gate(
            message=message,
            ticker=ticker,
            thesis_ticker=thesis_ticker,
            qty=qty,
            limit_price=limit_price,
            run_id=run_id,
            # Idade da referencia de preco do scan (SCAN_CACHE_TTL de 5 min):
            # alimenta a banda do colar LIMIT_PRICE_COLLAR.
            data_age_s=data_age_s,
        )

        if gate_decision.status != "ALLOW":
            logger.info(
                "trade_gate_blocked",
                ticker=ticker,
                reason_code=gate_decision.reason_code,
                gates_failed=gate_decision.gates_failed,
            )
            writer(
                {
                    "type": "PAPER_ORDER_BLOCKED",
                    "run_id": run_id,
                    "ticker": ticker,
                    "step": "f51_trade_gate",
                    "status": "blocked",
                    "reason": gate_decision.reason,
                    "reason_code": gate_decision.reason_code,
                    "gates_failed": gate_decision.gates_failed,
                }
            )
            record_blocked_order(gate_decision, message=message, ticker=ticker, run_id=run_id)
            # Record idempotency key even for blocked orders (prevents retry spam)
            claim_idempotency_keys(
                idem_keys, {"status": "blocked", "reason": gate_decision.reason_code}
            )
            return {
                "paper_exec_blocked": gate_decision.reason_code,
                "paper_exec_block_reason": gate_decision.reason,
                "paper_exec_gates_failed": gate_decision.gates_failed,
            }
    except ImportError:
        logger.warning("trade_gate_unavailable_blocking_all")
        return {"paper_exec_blocked": "F51_TRADE_GATE_UNAVAILABLE"}
    # Fronteira fail-closed do trade gate: erro inesperado bloqueia a ordem
    # (nunca deixa passar) e devolve codigo auditavel no resultado.
    except Exception as exc:  # noqa: BLE001
        logger.error("trade_gate_error", error=str(exc)[:200])
        return {"paper_exec_blocked": f"f51_trade_gate_error:{str(exc)[:120]}"}

    # ═══════════════════════════════════════════════════════════
    # ATOMIC IDEMPOTENCY CLAIM — the ALLOW path was only protected by the
    # is_duplicate() pre-check above, which is a plain existence test (TOCTOU:
    # two concurrent requests for the same ticker/qty/price/window can both
    # pass it before either writes the marker). claim_idempotency_keys() now
    # claims EVERY key of this intent with an exclusive file create; only the
    # first caller to reach here proceeds to submit, and a lost race on any one
    # key counts as duplicate. Claiming just the current window would still let
    # two attempts either side of a window boundary each win their own key.
    # ═══════════════════════════════════════════════════════════
    if not claim_idempotency_keys(idem_keys, {"status": "allowed"}):
        logger.warning(
            "auto_execute_duplicate_blocked_race",
            ticker=ticker,
            qty=qty,
            limit_price=limit_price,
            idempotency_key=idem_key,
        )
        writer(
            {
                "type": "PAPER_ORDER_BLOCKED",
                "run_id": run_id,
                "ticker": ticker,
                "step": "idempotency",
                "status": "blocked",
                "reason": f"Duplicate order detected (concurrent claim lost): {idem_key}",
            }
        )
        return {
            "paper_exec_blocked": "DUPLICATE_ORDER",
            "paper_exec_block_reason": f"Idempotency key already claimed concurrently: {idem_key}",
        }

    # Position sizing (only reached if gate ALLOWED)
    from core.mission_context import get_mission_equity

    paper_equity = get_mission_equity()
    sizing_config = _adaptive_sizing_config(state)

    try:
        from core.trading.position_sizer import PositionSizer

        if limit_price > 0:
            if sizing_config["max_position_pct"] <= 0:
                return {"paper_exec_blocked": "adaptive_config:max_position_zero"}
            size = PositionSizer(equity=paper_equity, **sizing_config).size(entry_price=limit_price)
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
            if int(qty) > size.shares:
                qty = max(1, size.shares)
                writer(
                    {
                        "type": "POSITION_SIZE_ADJUSTED",
                        "run_id": run_id,
                        "ticker": ticker,
                        "requested_qty": int(qty),
                        "approved_qty": qty,
                        "reason": size.size_reason,
                    }
                )
    # Fronteira de melhor esforco: falha no sizing bloqueia a ordem com motivo
    # auditavel no journal, sem derrubar o pipeline.
    except Exception as exc:  # noqa: BLE001
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

    # Concentration gate
    if _check_concentration(ticker, position_value, run_id):
        return {"paper_exec_blocked": f"concentration:{ticker}"}

    # Kill switch
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
                }
            )
            return {
                "paper_exec_blocked": f"kill_switch:{reason}",
                "submit_paper_order_error": f"kill_switch_active:{reason}",
            }
    # Fronteira de melhor esforco: preflight do kill switch indisponivel vira
    # warning; a decisao real de bloqueio segue nos gates abaixo.
    except Exception as exc:  # noqa: BLE001
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
            "max_position_pct": sizing_config["max_position_pct"] * 100,
            "data_age_s": round(data_age_s, 1),
            "data_source": "datahub_scan" if limit_price > 0 else "fallback",
        }
    )

    # Submit paper order
    order_state = {**state, "ticket_allowed": True}
    # CRITICAL: No fallback to placeholder price. If limit_price <= 0, the
    # F51 Trade Gate (GATE 7) will BLOCK this order as PLACEHOLDER_PRICE.
    # The DataHub price from _resolve_limit_price is the single source of truth.

    result = await _submit_paper_order(
        order_state,
        {
            "ticker": ticker,
            "action": action,
            "qty": qty,
            "order_type": "LMT",
            "limit_price": limit_price,
            "stop_loss_price": limit_price * (1 - sizing_config["default_stop_pct"]),
        },
    )

    # Paper journal audit trail
    journal_entry = _journal_trade(state, result, ticker, action, qty, limit_price, run_id)

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


def _extract_thesis_ticker(final: str, state: dict, order_ticker: str) -> str:
    """Extract the ticker referenced in the thesis/context to compare with order ticker.

    Looks for patterns like 'TICKER XXXX:' in the message or final_answer,
    and returns the FIRST ticker mentioned. This is used to detect mismatches
    where the thesis discusses one ticker but the order is for another.
    """
    import re as _re

    thesis_text = str(state.get("message", "") or "")
    if final:
        thesis_text = f"{thesis_text} {final}"

    # Pattern: 'TICKER SYMB:' or 'TICKER SYMBOL:' at the beginning
    ticker_match = _re.search(r"TICKER\s+([A-Z]{1,5}(?:\.[A-Z]{2})?)", thesis_text, _re.IGNORECASE)
    if ticker_match:
        thesis_ticker = ticker_match.group(1).upper()
        if thesis_ticker != order_ticker.upper():
            return thesis_ticker

    # Also check the state ticker if different from order
    state_ticker = str(state.get("ticker", "")).upper()
    if state_ticker and state_ticker != order_ticker.upper():
        return state_ticker

    return ""


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

    # Strategy 2: Top scan candidate (requires explicit trade intent)
    if candidates and state.get("route") in ("market_scan",):
        top = candidates[0] if isinstance(candidates[0], dict) else {}
        ticker = str(top.get("ticker", top.get("symbol", ""))).upper()
        if not ticker:
            return None, 0, ""
        price = float(top.get("price", top.get("latest_price", 0)) or 0)
        if price <= 0:
            return None, 0, ""  # No price, no quantity — will be blocked by gate
        qty = max(1, int(1000 / price)) if price > 0 else 0
        if qty <= 0:
            return None, 0, ""
        return ticker, qty, "buy"

    # Strategy 3: Direct ticker order (requires explicit trade intent)
    if state.get("ticker") and state.get("route") in ("ticker_analysis",):
        # Only proceed if message contains EXPLICIT trade request
        msg = (final or state.get("message", "")).lower()
        has_explicit_trade = any(
            w in msg
            for w in (
                "comprar",
                "compre",
                "vender",
                "venda",
                "paper_ticket",
                "buy",
                "sell",
                "execute order",
                "submit order",
                "place trade",
            )
        )
        if not has_explicit_trade:
            return None, 0, ""
        ticker = str(state.get("ticker", "")).upper()
        qty_match = re.search(
            r"(\d+)\s*(?:share|acao|acoes|shares)",
            final or state.get("message", ""),
            re.IGNORECASE,
        )
        qty = int(qty_match.group(1)) if qty_match else 0
        if qty <= 0:
            return None, 0, ""  # No valid quantity — gate will block
        action = (
            "sell"
            if any(w in (final or "").lower() for w in ("venda", "vender", "sell", "short"))
            else "buy"
        )
        return ticker, qty, action

    # Strategy 4: Any ticker + explicit trade intent keywords
    if state.get("ticker") and any(
        w in (state.get("message", "")).lower()
        for w in (
            "comprar",
            "compre",
            "buy",
            "venda",
            "vender",
            "sell",
            "trade",
            "ordem",
            "paper_ticket",
        )
    ):
        ticker = str(state.get("ticker", "")).upper()
        qty_match = re.search(
            r"(\d+)\s*(?:share|acao|acoes|shares)",
            final or state.get("message", ""),
            re.IGNORECASE,
        )
        qty = int(qty_match.group(1)) if qty_match else 0
        if qty <= 0:
            return None, 0, ""  # No valid quantity — gate will block
        action = (
            "sell"
            if any(
                w in (final or state.get("message", "")).lower()
                for w in ("venda", "vender", "sell", "short")
            )
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
                        collected_dt = datetime.fromisoformat(str(collected))
                        data_age_s = (datetime.now(UTC) - collected_dt).total_seconds()
                    except (ValueError, TypeError):
                        # Timestamp invalido: mantem data_age_s = 0 e segue.
                        logger.debug("collected_at unparseable: %r", collected)
                break
    if limit_price <= 0:
        limit_price = float(state.get("latest_price", 0)) or 0
    return limit_price, data_age_s


_TICKER_SAFE_RE = re.compile(r"^[A-Z]{1,5}(?:\.(?:SA|TO|V|L))?$")


def _validate_ticker_for_subprocess(ticker: str) -> str:
    """Validate ticker is safe for subprocess call. Only [A-Z]{1,5} + optional .SA/.TO/.V/.L."""
    ticker = (ticker or "").strip().upper()
    if not ticker:
        raise ValueError("Empty ticker rejected")
    if not _TICKER_SAFE_RE.match(ticker):
        raise ValueError(f"Invalid ticker format: {ticker}")
    if len(ticker) > 9:
        raise ValueError(f"Ticker too long: {ticker}")
    return ticker


def _check_concentration(ticker: str, position_value: float, run_id: str) -> bool:
    """Check if adding this position would exceed 50% concentration. Returns True if blocked."""
    try:
        safe_ticker = _validate_ticker_for_subprocess(ticker)
    except ValueError as ve:
        logger.warning("Concentration check skipped — invalid ticker: %s", ve)
        return False

    try:
        import json as _json
        import subprocess as _sp
        import sys as _sys

        check_script = str(
            Path(__file__).resolve().parent.parent.parent.parent.parent
            / "scripts"
            / "_ibkr_position_check.py"
        )
        proc = _sp.run(
            [_sys.executable, check_script, safe_ticker],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,  # returncode é verificado abaixo (0 = posição lida OK)
        )
        if proc.returncode == 0:
            data = _json.loads(proc.stdout.strip())
            existing_pct = data.get("pct_of_equity", 0)
            from core.mission_context import get_mission_equity

            new_total_pct = existing_pct + (
                position_value / data.get("equity", get_mission_equity()) * 100
            )
            if new_total_pct > 50:
                get_stream_writer()(
                    {
                        "type": "PIPELINE_STEP",
                        "run_id": run_id,
                        "step": "auto_execute_paper",
                        "status": "skipped",
                        "reason": f"concentration_gate:{ticker}_at_{existing_pct:.0f}pct_would_be_{new_total_pct:.0f}pct",
                    }
                )
                return True
    # Fronteira de melhor esforco: checagem de concentracao indisponivel nao
    # bloqueia a ordem; falha vira log de debug e segue.
    except Exception as exc:  # noqa: BLE001
        logger.debug("concentration check failed: %s", exc)
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
    """Record trade in paper journal. Triggers learning cycle on close.

    On journal write failure, enqueues to dead letter queue for manual replay.
    """
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
                        ot["trade_id"],
                        exit_price=fill_price,
                        exit_reason="auto_sell",
                        exit_date=datetime.now(UTC).isoformat(),
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
                        # Background learning cycle
                        import threading

                        def _run_learning_cycle(ot=ot):
                            try:
                                from core.trading.feedback_loop import get_feedback_loop

                                fb = get_feedback_loop()
                                fb.run_learning_cycle()
                                logger.info("learning_cycle_completed", trade_id=ot["trade_id"])
                            # Fronteira de melhor esforco em thread de fundo:
                            # ciclo de aprendizado falho vira warning e nunca
                            # derruba a thread do journal.
                            except Exception as e:  # noqa: BLE001
                                logger.warning("learning_cycle_failed", error=str(e)[:200])

                        threading.Thread(target=_run_learning_cycle, daemon=True).start()
                        return f"closed:{ot['trade_id']}"
            return f"no_open_trade_for:{ticker}"
        else:
            learning_context = _extract_learning_context(state, qty, limit_price, action=action)
            trade = PaperTrade(
                trade_id=f"bob-{run_id[:12]}" if run_id else f"bob-{int(time.time())}",
                ticker=ticker,
                thesis=state.get("message", "Auto-executed paper trade")[:200],
                direction="long" if action.lower() == "buy" else "short",
                entry_date=datetime.now(UTC).isoformat(),
                entry_price=limit_price,
                shares=qty,
                entry_reasoning=f"auto_execute_paper | route={state.get('route', '?')} | run_id={run_id}",
                verdict_at_entry=state.get("trade_order_context", {}).get("decision", "auto"),
                risk_assessment=state.get("risk_tolerance", "moderada"),
                expected_holding_period="swing",
                **learning_context,
            )
            trade_id = journal.open_trade(trade)
            logger.info(
                "paper_trade_opened",
                trade_id=trade_id,
                ticker=ticker,
                action=action,
                qty=qty,
                limit_price=limit_price,
            )
            return trade_id
    # Fronteira de melhor esforco: falha de escrita no journal vai para a
    # dead letter queue para replay manual, sem derrubar a execucao.
    except Exception as exc:  # noqa: BLE001
        # Journal write failed → dead letter queue
        logger.error("journal_write_failed_dead_letter", ticker=ticker, error=str(exc)[:200])
        enqueue_dead_letter(
            ticker=ticker,
            qty=qty,
            limit_price=limit_price,
            action=action,
            reason=f"journal_write_error:{str(exc)[:120]}",
            state_snapshot={
                "run_id": run_id,
                "route": state.get("route", "?"),
            },
        )
        return f"journal_error_dead_letter:{exc}"


def _normalize_prediction_direction(value: object) -> str | None:
    token = str(value or "").strip().upper()
    if token in {"UP", "BUY", "LONG", "BULLISH", "UNDERVALUED", "SUPPORT"}:
        return "UP"
    if token in {"DOWN", "SELL", "SHORT", "BEARISH", "OVERVALUED", "BLOCK", "RISK_OFF"}:
        return "DOWN"
    if token in {"SIDEWAYS", "NEUTRAL", "WAIT", "HOLD", "FAIR_VALUE"}:
        return "SIDEWAYS"
    return None


def _finite_probability(value: object) -> float | None:
    try:
        probability = float(value)
    except (TypeError, ValueError):
        return None
    if probability > 1.0:
        probability /= 100.0
    if not math.isfinite(probability) or probability < 0.0 or probability > 1.0:
        return None
    return probability


def _extract_learning_context(
    state: dict, qty: int, entry_price: float, *, action: str | None = None
) -> dict:
    """Capture decision-time facts without producing a learning outcome."""
    attribution: dict[str, float] = {}
    predictions: dict[str, dict] = {}

    structured = state.get("expert_structured") or {}
    if isinstance(structured, dict):
        for name, payload in structured.items():
            if not isinstance(payload, dict):
                continue
            direction = _normalize_prediction_direction(
                payload.get("direction") or payload.get("decision") or payload.get("verdict")
            )
            confidence = _finite_probability(payload.get("confidence"))
            probabilities = payload.get("direction_prob")
            if direction is None or (confidence is None and not isinstance(probabilities, dict)):
                continue
            prediction: dict[str, object] = {"direction": direction}
            if isinstance(probabilities, dict):
                prediction["probabilities"] = probabilities
            else:
                prediction["confidence"] = confidence
            predictions[str(name)] = prediction
            if confidence is not None:
                attribution[str(name)] = confidence

    for result in state.get("expert_results") or []:
        if not isinstance(result, dict) or result.get("ok") is False:
            continue
        name = str(result.get("role") or result.get("expert") or result.get("name") or "").strip()
        if not name:
            continue
        payload = result
        raw_response = result.get("response")
        if isinstance(raw_response, str):
            clean = raw_response.strip().removeprefix("```json").removesuffix("```").strip()
            try:
                decoded = json.loads(clean)
                if isinstance(decoded, dict):
                    payload = {**result, **decoded}
            except json.JSONDecodeError:
                pass
        direction = _normalize_prediction_direction(
            payload.get("direction") or payload.get("decision") or payload.get("verdict")
        )
        confidence = _finite_probability(payload.get("confidence"))
        probabilities = payload.get("direction_prob")
        if direction is None or (confidence is None and not isinstance(probabilities, dict)):
            continue
        if name not in predictions:
            prediction = {"direction": direction}
            if isinstance(probabilities, dict):
                prediction["probabilities"] = probabilities
            else:
                prediction["confidence"] = confidence
            predictions[name] = prediction
        if confidence is not None:
            attribution[name] = confidence

    neural = state.get("neural_decision") or {}
    calibration_status = str(neural.get("calibration_status") or "unknown").lower()
    model_id = str(neural.get("model_id") or "")
    prediction_class = _normalize_prediction_direction(neural.get("decision"))
    expected_class = (
        "UP"
        if str(action or "").lower() in {"buy", "long"}
        else "DOWN"
        if action is not None
        else None
    )
    prediction_probability = None
    direction_prob = neural.get("direction_prob")
    if (
        neural.get("status") == "ready"
        and calibration_status in {"calibrated", "validated_oos"}
        and prediction_class is not None
        and (expected_class is None or prediction_class == expected_class)
        and isinstance(direction_prob, dict)
    ):
        prediction_probability = _finite_probability(direction_prob.get(prediction_class.lower()))

    stop_loss_pct = _adaptive_sizing_config(state)["default_stop_pct"]

    return {
        "confidence_at_entry": prediction_probability,
        "prediction_probability_at_entry": prediction_probability,
        "prediction_class_at_entry": prediction_class,
        "calibration_status": calibration_status,
        "model_id": model_id,
        "forecast_as_of": str(neural.get("as_of") or ""),
        "forecast_horizon": neural.get("horizon"),
        "risk_at_entry": abs(float(entry_price) * int(qty)) * stop_loss_pct,
        "expert_attribution": attribution,
        "expert_predictions": predictions,
    }
