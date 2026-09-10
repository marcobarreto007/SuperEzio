"""Tool Executor node — executes tools requested by the Agent."""

from __future__ import annotations

import asyncio
import os
from datetime import UTC
from typing import Any

from langgraph.config import get_stream_writer

from core.config.logging_config import get_logger
from core.config.settings import get_settings
from core.math.penny_momentum import PennyMomentumConfig, simulate_penny_momentum_backtest

from ..contracts import AgentToolCall
from .collector import node_collector
from .experts import EXPERT_ROLES, node_collect_experts, node_expert, run_experts_parallel
from .f51 import node_f51_verdict
from .neural_decision import node_neural_decision
from .rag import node_rag_forensics
from .sdca_firewall import node_sdca_firewall

# PennyLab: imported at module level — no lazy import on hot tool path
try:
    from experts.pennylab.pipeline_hook import analyze_ticker_sync as _pennylab_analyze

    _PENNYLAB_AVAILABLE = True
except ImportError:
    _PENNYLAB_AVAILABLE = False

    def _pennylab_analyze(ticker: str):  # type: ignore[misc]
        return {"ticker": ticker, "decision": None, "error": "pennylab_module_not_found"}


logger = get_logger(__name__)


def _check_lesson_block(ticker: str) -> dict[str, Any] | None:
    """Check if ticker has a blocking lesson from learning_log.jsonl.

    Returns the lesson dict if blocking, None otherwise.
    """
    from core.paths import resolve_project_path

    learning_log_path = resolve_project_path("data/learning_log.jsonl")
    if not learning_log_path.exists():
        return None

    ticker = ticker.upper()
    try:
        for line in learning_log_path.read_text(encoding="utf-8").strip().splitlines():
            if not line:
                continue
            try:
                lesson = __import__("json").loads(line)
                if not isinstance(lesson, dict):
                    continue
                # Check if lesson applies to this ticker
                applicable_tickers = lesson.get("applicable_tickers", [])
                if not isinstance(applicable_tickers, list):
                    continue
                if ticker in [t.upper() for t in applicable_tickers]:
                    # Block if lesson is about broken thesis or loss
                    title = lesson.get("title", "").lower()
                    if any(kw in title for kw in ("incorreta", "broken", "loss", "preju", "erro")):
                        return lesson
            except (TypeError, ValueError, __import__("json").JSONDecodeError):
                continue
    # Leitura do learning log é melhor esforço: falha aqui não pode bloquear a ordem.
    # Tipos possíveis: OSError (leitura), ValueError (UnicodeDecodeError), AttributeError (estrutura inesperada).
    except (OSError, ValueError, AttributeError) as exc:
        logger.debug("learning_log_read_failed", error=str(exc)[:200])
    return None


_REPEATABLE_TOOLS = {"final_answer"}
_SEMI_REPEATABLE_LIMITS: dict[str, int] = {
    "collect_data": 2,
    "calculate": 5,
    "run_experts": 2,
}


def _paper_order_submission_error(state: dict, args: dict) -> str:
    # Runtime env override takes precedence so tests and operational toggles
    # are reflected immediately without requiring settings singleton reload.
    env_override = os.getenv("SUPEREZIO_ENABLE_PAPER_ORDER_SUBMIT")
    if env_override is None:
        settings = get_settings()
        paper_submit_enabled = bool(settings.superezio_enable_paper_order_submit)
    else:
        paper_submit_enabled = env_override.strip().lower() in {"1", "true", "yes", "on"}

    if not paper_submit_enabled:
        return "paper_order_submission_disabled_by_env"
    if not state.get("ticket_allowed", False) and not args.get("_forced_by_case"):
        return "paper_order_not_allowed_by_cognitive_contract"
    order_type = str(args.get("order_type") or args.get("type") or "").strip().upper()
    if order_type != "LMT":
        return "limit_order_required"
    try:
        if float(args.get("limit_price") or 0) <= 0:
            return "missing_limit_price"
    except (TypeError, ValueError):
        return "invalid_limit_price"
    try:
        from core.trading.kill_switch import get_kill_switch

        kill_state = get_kill_switch().check()
        if kill_state.is_active:
            reason = kill_state.reason.value if kill_state.reason else "unknown"
            return f"kill_switch_active:{reason}"
    # Preflight do kill switch é melhor esforço: indisponibilidade não bloqueia a submissão.
    except Exception as exc:  # noqa: BLE001
        logger.warning("kill_switch_preflight_unavailable", error=str(exc)[:200])
    return ""


def _tool_permission_error(state: dict, tool_name: str, args: dict) -> str:
    allowed_tools = set(state.get("allowed_tools") or [])
    if not allowed_tools or tool_name == "final_answer":
        return ""
    if tool_name not in allowed_tools:
        mode = state.get("cognitive_mode", "unknown")
        return f"not_allowed_by_cognitive_contract:{mode}"
    if tool_name == "market_scan" and not state.get("scanner_allowed", False):
        mode = state.get("cognitive_mode", "unknown")
        return f"scanner_not_allowed_by_cognitive_contract:{mode}"
    if tool_name == "collect_data":
        ticker = str(args.get("ticker") or state.get("ticker") or "").strip()
        if not state.get("ticker_allowed", False) or not ticker:
            mode = state.get("cognitive_mode", "unknown")
            return f"ticker_data_not_allowed_by_cognitive_contract:{mode}"
    if tool_name == "submit_paper_order":
        return _paper_order_submission_error(state, args)
    return ""


def _tool_blocked_payload(state: dict, tool_name: str, reason: str) -> dict:
    executed_tools = list(state.get("executed_tools") or [])
    executed_tool_counts = dict(state.get("executed_tool_counts") or {})
    content = (
        f"Tool '{tool_name}' was blocked because {reason}. "
        "Use the results already present in state and produce final_answer."
    )
    return {
        "executed_tools": executed_tools,
        "executed_tool_counts": executed_tool_counts,
        "tool_blocked": {
            "tool": tool_name,
            "reason": reason,
            "instruction": "Choose a different tool or call final_answer.",
        },
        "agent_tool_call": {"tool": "final_answer", "args": {"content": content}},
        "errors": state.get("errors", []) + [f"tool_blocked:{tool_name}:{reason}"],
    }


async def _gather_social_context(ticker: str, query: str) -> str:
    """Collect Reddit posts across subreddits for social forensic analysis."""
    import asyncio

    subreddits = [
        "pennystocks",
        "wallstreetbets",
        "stocks",
        "investing",
        "CanadianInvestor",
        "StockMarket",
        "RobinHoodPennyStocks",
        "smallstreetbets",
        "Shortsqueeze",
        "Daytrading",
    ]
    search_term = ticker or query or ""
    if not search_term:
        return "(no ticker or query provided)"

    posts: list[str] = []

    def _fetch(subreddit: str) -> None:
        import json
        import urllib.parse
        import urllib.request

        try:
            url = (
                f"https://www.reddit.com/r/{subreddit}/search.json"
                f"?q={urllib.parse.quote_plus(search_term)}"
                f"&restrict_sr=1&sort=top&t=month&limit=15&raw_json=1"
            )
            req = urllib.request.Request(
                url, headers={"User-Agent": "SuperEzio/1.0 forensic-research"}
            )
            # URL is constructed from fixed subreddit list — safe for urlopen
            with urllib.request.urlopen(req, timeout=8) as resp:  # nosec: B310 — restricted to reddit.com
                data = json.loads(resp.read())
            for child in data.get("data", {}).get("children", []):
                d = child.get("data", {})
                title = d.get("title", "")
                selftext = (d.get("selftext") or "")[:500]
                author = d.get("author", "unknown")
                score = d.get("score", 0)
                comments = d.get("num_comments", 0)
                upvote = d.get("upvote_ratio", 0)
                created = d.get("created_utc", 0)
                from datetime import datetime

                dt = (
                    datetime.fromtimestamp(created, tz=UTC).strftime("%Y-%m-%d %H:%M")
                    if created
                    else "?"
                )
                posts.append(
                    f"[r/{subreddit}] u/{author} | {score}pts {upvote * 100:.0f}%up | {comments}c | {dt}\n"
                    f"TITLE: {title[:300]}\n"
                    f"BODY: {selftext[:400]}\n"
                )
        # Falha de rede/parse num subreddit não derruba a coleta social.
        # Tipos possíveis: OSError (urlopen/timeout), ValueError (JSON), TypeError/AttributeError (JSON não confiável).
        except (OSError, TypeError, ValueError, AttributeError) as e:
            posts.append(f"[r/{subreddit}] FETCH_ERROR: {e}")

    await asyncio.to_thread(lambda: [_fetch(s) for s in subreddits])

    if not posts:
        return f"No Reddit posts found for '{search_term}' in the last month."

    header = (
        f"REDDIT SOCIAL FORENSICS — {len(posts)} posts about '{search_term}' "
        f"across {len(subreddits)} subreddits (top/month)\n"
        f"{'=' * 70}\n\n"
    )
    return header + "\n---\n".join(posts)


async def _run_pennylab(state: dict) -> dict:
    """Execute PennyLab forensic analysis and surface mathcore_verdict to Bob.

    Uses the real experts.pennylab.pipeline_hook (not a stub).
    The mathcore_verdict is injected into data_context so Bob can cite it
    as authoritative math evidence in his final answer.
    """
    import asyncio

    ticker = state.get("ticker", "")
    if not ticker:
        logger.warning("pennylab called without ticker in state")
        return {"pennylab": {}, "data_context": ""}

    if not _PENNYLAB_AVAILABLE:
        logger.warning("pennylab module not available — skipping forensic analysis")
        return {
            "pennylab": {"ticker": ticker, "decision": None, "error": "pennylab_module_not_found"}
        }

    try:
        result: dict = await asyncio.to_thread(_pennylab_analyze, ticker)

        # Surface the mathcore_verdict into Bob's observation context
        verdict = result.get("mathcore_verdict", "")
        context_parts = []
        if verdict:
            context_parts.append(f"[MATH CORE VERDICT — {ticker}]\n{verdict}")

        scores = result.get("scores", {})
        if scores:
            context_parts.append(
                f"[PENNYLAB SCORES — {ticker}]\n"
                + "\n".join(f"  {k}: {v}" for k, v in scores.items())
            )

        data_context = "\n\n".join(context_parts) if context_parts else ""

        return {
            "pennylab": result,
            "data_context": data_context,
        }
    # Análise PennyLab é fronteira de melhor esforço: hook externo pode levantar qualquer erro.
    except Exception as exc:  # noqa: BLE001
        logger.error("pennylab analysis failed for %s: %s", ticker, exc)
        return {
            "pennylab": {"ticker": ticker, "decision": None, "error": str(exc)[:200]},
        }


async def _run_penny_momentum_backtest(state: dict, args: dict[str, Any]) -> dict:
    """Run the math-core penny momentum backtest for injected or fetched OHLCV."""
    import asyncio

    ohlcv_by_symbol = args.get("ohlcv_by_symbol") or state.get("ohlcv_by_symbol") or {}
    tickers = _extract_backtest_tickers(state, args)

    if not ohlcv_by_symbol and tickers:
        ohlcv_by_symbol = await asyncio.to_thread(
            _fetch_backtest_ohlcv,
            tickers,
            str(args.get("timeframe") or "5Y"),
        )
        missing_tickers = sorted(set(tickers) - {str(key).upper() for key in ohlcv_by_symbol})
        if missing_tickers:
            return _penny_backtest_error(
                state,
                "missing_ohlcv_for_requested_tickers:" + ",".join(missing_tickers),
            )

    if not ohlcv_by_symbol:
        return _penny_backtest_error(state, "missing_ohlcv")

    try:
        result = simulate_penny_momentum_backtest(
            ohlcv_by_symbol,
            config=_penny_config_from_args(args),
        )
    except ValueError as exc:
        return _penny_backtest_error(state, str(exc))
    context = _format_penny_backtest_context(result)
    return {
        "penny_momentum_backtest": result,
        "data_context": _append_context(state.get("data_context", ""), context),
    }


def _penny_backtest_error(state: dict, reason: str) -> dict:
    content = (
        "[MATHCORE BACKTEST ERROR]\n"
        "strategy=penny_momentum_breakout\n"
        f"status={reason}\n"
        "reason=Historical OHLCV is mandatory and every requested symbol must have valid data."
    )
    return {
        "penny_momentum_backtest": {
            "error": reason,
            "strategy": "penny_momentum_breakout",
        },
        "data_context": _append_context(state.get("data_context", ""), content),
        "errors": state.get("errors", []) + [f"penny_momentum_backtest:{reason}"],
    }


def _extract_backtest_tickers(state: dict, args: dict[str, Any]) -> list[str]:
    raw = args.get("tickers") or args.get("symbols") or []
    if isinstance(raw, str):
        tickers = [part.strip().upper() for part in raw.split(",") if part.strip()]
    else:
        tickers = [str(item).strip().upper() for item in raw if str(item).strip()]

    if tickers:
        return tickers[:25]

    scan = state.get("scan") or {}
    candidates = scan.get("candidates") or []
    for item in candidates:
        ticker = item.get("ticker") or item.get("symbol")
        if ticker:
            tickers.append(str(ticker).strip().upper())
    return tickers[:25]


def _fetch_backtest_ohlcv(tickers: list[str], timeframe: str) -> dict[str, list[dict[str, Any]]]:
    try:
        from data.data_hub import hub
    # Import opcional de melhor esforço: hub indisponível apenas devolve dados vazios.
    except Exception:  # noqa: BLE001
        return {}

    out: dict[str, list[dict[str, Any]]] = {}
    for ticker in tickers:
        try:
            result = hub.get_candles(ticker, timeframe=timeframe)
            candles = result.get("candles") or result.get("ohlcv") or []
            if candles:
                out[ticker] = candles
        # Fetch por ticker é melhor esforço: falha num ticker não derruba o backtest.
        except Exception as exc:  # noqa: BLE001
            logger.warning("penny momentum candle fetch failed for %s: %s", ticker, exc)
    return out


def _penny_config_from_args(args: dict[str, Any]) -> PennyMomentumConfig:
    config_values = dict(PennyMomentumConfig().__dict__)
    casts = {
        "starting_capital": float,
        "min_price": float,
        "max_price": float,
        "min_avg_dollar_volume": float,
        "volume_spike_ratio": float,
        "max_positions": int,
        "target_weight": float,
        "hold_days": int,
        "stop_loss_pct": float,
        "commission_bps": float,
        "slippage_bps": float,
    }
    for key, caster in casts.items():
        if key not in args:
            continue
        try:
            config_values[key] = caster(args[key])
        except (TypeError, ValueError):
            logger.warning("invalid penny momentum arg %s=%r", key, args[key])
    return PennyMomentumConfig(**config_values)


def _format_penny_backtest_context(result: dict[str, Any]) -> str:
    benchmark = result.get("benchmarks", {}).get("buy_and_hold_equal_weight", {})
    costs = result.get("costs", {})
    return (
        "[MATHCORE BACKTEST]\n"
        f"strategy={result.get('strategy')}\n"
        f"verdict={result.get('verdict')}\n"
        f"total_return={result.get('total_return_pct')}%\n"
        f"sharpe={result.get('sharpe')}\n"
        f"max_drawdown={result.get('max_drawdown_pct')}%\n"
        f"win_rate={result.get('win_rate_pct')}%\n"
        f"trade_count={result.get('trade_count')}\n"
        f"buy_hold_return={benchmark.get('total_return')}\n"
        f"excess_return_vs_buy_hold={result.get('excess_return_vs_buy_and_hold')}\n"
        f"commission_bps={costs.get('commission_bps')}\n"
        f"slippage_bps={costs.get('slippage_bps')}\n"
        f"mathcore_verdict={result.get('mathcore_verdict')}"
    )


def _append_context(existing: str, addition: str) -> str:
    if existing and addition:
        return existing + "\n\n" + addition
    return existing or addition


async def _submit_paper_order(state: dict, args: dict) -> dict:
    """Submit a paper trade order to IBKR via the InteractiveBrokersAdapter.

    Only works when IBKR paper TWS is connected on port 7497.
    Disabled by default; enabled only by explicit paper-submit env.
    """

    from core.trading.execution_policy import (
        adaptive_sizing_config,
        evaluate_neural_execution_gate,
        expert_consensus_block_reason,
    )

    consensus_block = expert_consensus_block_reason(state)
    if consensus_block:
        return {"submit_paper_order_error": f"weighted_expert_consensus:{consensus_block}"}

    neural_gate = evaluate_neural_execution_gate(
        state, str(args.get("action", args.get("side", "buy")))
    )
    if not neural_gate["allowed"]:
        return {
            "submit_paper_order_error": f"neural_execution_gate:{neural_gate['code']}",
            "neural_gate": neural_gate,
        }

    permission_error = _paper_order_submission_error(state, args)
    if permission_error:
        return {"submit_paper_order_error": permission_error}

    symbol = str(args.get("ticker", args.get("symbol", ""))).upper()
    action = str(args.get("action", args.get("side", "buy"))).lower()
    qty = float(args.get("qty", args.get("quantity", args.get("shares", 10))))
    limit_price = float(args.get("limit_price"))

    if not symbol:
        return {"submit_paper_order_error": "missing_ticker"}

    requested_qty = int(qty)
    sizing_config = adaptive_sizing_config(state)
    if sizing_config["max_position_pct"] <= 0:
        return {"submit_paper_order_error": "adaptive_config:max_position_zero"}
    # Stop is ALWAYS derived from entry price and the adaptive default.
    # A model-proposed stop_loss_price in args is intentionally ignored:
    # honoring it let the model shrink the calculated risk and slip under
    # the approval_gate auto-approval threshold (risk <= $500) without a human.
    stop_loss_price = float(limit_price * (1 - sizing_config["default_stop_pct"]))

    # ── Approval gate FIRST (before position sizing) ──
    # The gate must evaluate the REQUESTED risk, not the capped risk,
    # otherwise position sizer capping auto-approves trades that should be pending.
    try:
        from core.trading.approval_gate import (
            ApprovalStatus,
            approval_request_to_dict,
            get_approval_gate,
        )

        risk_amount = abs(limit_price - stop_loss_price) * requested_qty
        approval = get_approval_gate().submit(
            symbol=symbol,
            side=action,
            qty=float(requested_qty),
            entry_price=limit_price,
            stop_loss_price=stop_loss_price,
            risk_amount=risk_amount,
            reason=f"submit_paper_order run_id={state.get('run_id', '')}",
        )
        approval_payload = approval_request_to_dict(approval)
        if approval.status == ApprovalStatus.PENDING:
            # Still run position sizing for info even when pending
            pos_sizing = {}
            try:
                from core.mission_context import get_mission_equity
                from core.trading.position_sizer import PositionSizer

                paper_equity = float(
                    state.get("paper_equity") or state.get("equity") or get_mission_equity()
                )
                open_positions = int(
                    state.get("open_positions") or state.get("positions_count") or 0
                )
                size = PositionSizer(equity=paper_equity, **sizing_config).size(
                    entry_price=limit_price,
                    stop_loss_price=stop_loss_price,
                    open_positions=open_positions,
                )
                pos_sizing = {
                    "requested_qty": requested_qty,
                    "approved_qty": size.shares,
                    "max_shares": size.shares,
                    "notional_value": round(float(size.shares) * limit_price, 2),
                    "risk_per_share": size.risk_per_share,
                    "stop_loss_price": stop_loss_price,
                    "max_notional_value": size.max_notional_value,
                    "capped": requested_qty > size.shares or size.capped,
                    "reason": size.size_reason,
                }
            # Fallback deliberado: sizer indisponível não bloqueia a submissão pendente.
            except Exception:  # noqa: BLE001
                pos_sizing = {
                    "requested_qty": requested_qty,
                    "approved_qty": 0,
                    "reason": "sizer_unavailable",
                }
            return {
                "submit_paper_order_error": f"approval_pending:{approval.id}",
                "paper_approval_request": approval_payload,
                "position_sizing": pos_sizing,
            }
    # Fronteira de melhor esforço: erro inesperado no approval gate vira payload de erro, sem derrubar o pipeline.
    except Exception as exc:  # noqa: BLE001
        return {"submit_paper_order_error": f"approval_gate_error:{str(exc)[:160]}"}

    # ── Position sizing ──
    try:
        from core.mission_context import get_mission_equity
        from core.trading.position_sizer import PositionSizer

        paper_equity = float(
            state.get("paper_equity") or state.get("equity") or get_mission_equity()
        )
        open_positions = int(state.get("open_positions") or state.get("positions_count") or 0)
        size = PositionSizer(equity=paper_equity, **sizing_config).size(
            entry_price=limit_price,
            stop_loss_price=stop_loss_price,
            open_positions=open_positions,
        )
        if size.shares <= 0:
            return {
                "submit_paper_order_error": f"position_sizer_blocked:{size.size_reason}",
                "position_sizing": {
                    "requested_qty": requested_qty,
                    "approved_qty": 0,
                    "reason": size.size_reason,
                },
            }
        if requested_qty > size.shares:
            logger.warning(
                "paper order qty capped by PositionSizer: %s requested=%s approved=%s",
                symbol,
                requested_qty,
                size.shares,
            )
            qty = float(size.shares)
    # Fronteira de melhor esforço: erro no position sizer vira payload de erro, sem derrubar o pipeline.
    except Exception as exc:  # noqa: BLE001
        return {"submit_paper_order_error": f"position_sizer_error:{str(exc)[:160]}"}

    try:
        from adapters.broker.ibkr_adapter import InteractiveBrokersAdapter
        from core.pipeline.f51_trade_gate import (
            build_order_gate_metadata,
            evaluate_trade_gate,
        )
        from core.trading.broker import Order, OrderSide, OrderStatus, OrderType

        consensus = state.get("expert_consensus") or {}
        decision = evaluate_trade_gate(
            message=str(state.get("message") or "prepared paper order"),
            ticker=symbol,
            thesis_ticker=str(state.get("ticker") or symbol),
            qty=int(qty),
            limit_price=limit_price,
            run_id=str(state.get("run_id") or approval.id),
        )
        metadata = build_order_gate_metadata(
            decision,
            order_symbol=symbol,
            approval_id=approval.id,
            consensus_decision=str(consensus.get("decision") or ""),
            neural_gate=neural_gate,
        )
        order = Order(
            id=f"prepared-{approval.id}",
            symbol=symbol,
            side=OrderSide.BUY if action in ("buy", "long") else OrderSide.SELL,
            order_type=OrderType.LIMIT,
            qty=float(qty),
            status=OrderStatus.PENDING,
            limit_price=limit_price,
            stop_price=stop_loss_price,
            gate_metadata=metadata,
        )
        submitted = await asyncio.to_thread(InteractiveBrokersAdapter().submit_order, order)
        if submitted.status == OrderStatus.REJECTED:
            return {"submit_paper_order_error": f"broker_rejected:{submitted.id}"}
        return {
            "submit_paper_order_result": {
                "order_id": submitted.id,
                "symbol": submitted.symbol,
                "action": submitted.side.value,
                "qty": submitted.qty,
                "limit_price": submitted.limit_price,
                "status": submitted.status.value,
                "perm_id": submitted.perm_id,
                "tws_order_id": submitted.tws_order_id,
                "client_id": submitted.client_id,
                "gate_checked": True,
            }
        }
    except ValueError as exc:
        return {"submit_paper_order_error": f"prepared_order_invalid:{str(exc)[:160]}"}
    # Fronteira de melhor esforço: falha na ponte de execução vira payload de erro, sem derrubar o pipeline.
    except Exception as exc:  # noqa: BLE001
        return {"submit_paper_order_error": f"bridge_error:{str(exc)[:200]}"}


async def node_tool_executor(state: dict, *, gateway=None, config=None) -> dict:
    tool_call = state.get("agent_tool_call")
    if not tool_call:
        return {}

    try:
        validated_call = AgentToolCall.model_validate(tool_call)
    # ValidationError do Pydantic v2 é subclasse de ValueError — único erro esperado de model_validate.
    except ValueError as exc:
        return {
            "tool_blocked": {
                "tool": str(tool_call.get("tool", "invalid"))
                if isinstance(tool_call, dict)
                else "invalid",
                "reason": f"invalid_tool_call:{exc}",
                "instruction": "Call final_answer with a useful explanation.",
            },
            "agent_tool_call": {
                "tool": "final_answer",
                "args": {
                    "content": "Bob could not execute the requested tool because the tool call was invalid."
                },
            },
            "errors": state.get("errors", []) + [f"invalid_tool_call:{exc}"],
        }

    tool_name = validated_call.tool
    args = validated_call.args
    executed_tools = list(state.get("executed_tools") or [])
    executed_tool_counts = dict(state.get("executed_tool_counts") or {})

    permission_error = _tool_permission_error(state, tool_name, args)
    if permission_error:
        writer = get_stream_writer()
        writer(
            {
                "type": "PIPELINE_STEP",
                "run_id": state.get("run_id", ""),
                "step": tool_name,
                "status": "blocked_by_cognitive_contract",
                "reason": permission_error,
            }
        )
        return _tool_blocked_payload(state, tool_name, permission_error)

    repeatable = tool_name in _REPEATABLE_TOOLS
    semi_limit = _SEMI_REPEATABLE_LIMITS.get(tool_name)
    semi_count = executed_tool_counts.get(tool_name, 0)
    paper_order_has_broker_result = bool(
        state.get("submit_paper_order_result") or state.get("submit_paper_order_error")
    )
    if (
        tool_name == "submit_paper_order"
        and tool_name in executed_tools
        and not paper_order_has_broker_result
    ):
        executed_tools = [tool for tool in executed_tools if tool != tool_name]
        executed_tool_counts = {
            key: value for key, value in executed_tool_counts.items() if key != tool_name
        }
        semi_count = 0
    if (
        tool_name in executed_tools
        and not repeatable
        and (semi_limit is None or semi_count >= semi_limit)
    ):
        writer = get_stream_writer()
        writer(
            {
                "type": "PIPELINE_STEP",
                "run_id": state.get("run_id", ""),
                "step": tool_name,
                "status": "blocked_duplicate",
            }
        )
        return _tool_blocked_payload(state, tool_name, "it already executed in this run")
        # else: within semi-repeatable limit — allow again

    next_executed_tool_counts = dict(executed_tool_counts)
    if not repeatable:
        next_executed_tool_counts[tool_name] = next_executed_tool_counts.get(tool_name, 0) + 1

    next_executed_tools = executed_tools
    if tool_name not in _REPEATABLE_TOOLS:
        next_executed_tools = [*executed_tools, tool_name]

    # We map tool names to the actual nodes.
    # The original nodes emit SSE PIPELINE_STEP events, so the UI will update correctly.

    try:
        if tool_name == "collect_data":
            # Set the route to ticker_analysis so collector knows what to do
            ticker = args.get("ticker", state.get("ticker", ""))
            result = await node_collector(
                {**state, "ticker": ticker, "route": "ticker_analysis"},
                config=config,
            )

        elif tool_name == "collect_data":
            ticker = args.get("ticker", state.get("ticker", ""))
            if ticker:
                result = await node_collector(
                    {**state, "ticker": ticker, "route": "ticker_analysis"}, config=config
                )
            else:
                result = {"error": "collect_data requires ticker"}
        elif tool_name == "market_scan":
            # Set route to market_scan
            result = await node_collector(
                {
                    **state,
                    "route": "market_scan",
                    "message": args.get("query", state.get("message")),
                },
                config=config,
            )

        elif tool_name == "penny_momentum_backtest":
            result = await _run_penny_momentum_backtest(state, args)

        elif tool_name == "f51_firewall":
            result = await node_f51_verdict(state)

        elif tool_name == "pennylab":
            result = await _run_pennylab(state)

        elif tool_name == "run_experts":
            # Usually experts runs fan-out. We can just run a single expert stub that does the summary,
            # or we run node_expert for all roles in a loop to populate expert_results.
            # For simplicity, we just run the fundamental and technical experts directly, then run node_collect_experts logic.
            # But graph.py used Send() for experts. We will just run them sequentially here for the agent.
            doubt = str(args.get("question") or args.get("doubt") or "").strip()
            expert_state = dict(state)
            if doubt:
                prior = str(expert_state.get("data_context") or "")
                expert_state["data_context"] = (
                    prior
                    + "\n\nBOB FOLLOW-UP DOUBT (resolve this before any buy/sell verdict): "
                    + doubt
                )
                expert_state["expert_consult_question"] = doubt
            # Comite em paralelo na nuvem (2026-09-05): o loop serial era heranca
            # do slot unico do llama-server local; experts rodam na API DeepSeek.
            results = await run_experts_parallel(expert_state, EXPERT_ROLES, gateway=gateway)

            result = await node_collect_experts({**expert_state, "expert_results": results})
            if doubt:
                result = {
                    **result,
                    "expert_consult_question": doubt,
                    "data_context": expert_state.get("data_context"),
                }

        elif tool_name == "neural_decision":
            result = await node_neural_decision(state)

        elif tool_name == "sdca_firewall":
            result = await node_sdca_firewall(state)

        elif tool_name == "rag_forensics":
            result = await node_rag_forensics(state)

        elif tool_name == "submit_paper_order":
            # ═══════════════════════════════════════════════════════
            # F51 TRADE GATE — Central safety validator
            # Must pass BEFORE any paper order can proceed.
            # ═══════════════════════════════════════════════════════
            try:
                from core.idempotency import (
                    claim_idempotency_keys,
                    is_duplicate,
                    make_idempotency_keys,
                )
                from core.pipeline.f51_trade_gate import evaluate_trade_gate, record_blocked_order

                ticker_raw = args.get("ticker", "").upper()
                qty_raw = int(
                    float(args.get("qty", args.get("quantity", args.get("shares", 0)) or 0))
                )
                price_raw = float(args.get("limit_price", 0) or 0)
                msg = str(state.get("message", "") or "")
                thesis_ticker = str(state.get("ticker", "") or "").upper()
                run_id = state.get("run_id", "")

                # Idempotency check across the current AND previous window: the
                # window is truncated against the wall clock, so a retry seconds
                # later can otherwise mint a brand-new key and submit twice.
                idem_keys = make_idempotency_keys(ticker_raw, qty_raw, price_raw)
                idem_key = idem_keys[0]
                if any(is_duplicate(key) for key in idem_keys):
                    logger.warning(
                        "tool_executor_duplicate_blocked",
                        ticker=ticker_raw,
                        idempotency_key=idem_key,
                    )
                    return {
                        "blocked": True,
                        "reason": "f51_trade_gate:DUPLICATE_ORDER",
                        "message": f"Ordem duplicada detectada: {idem_key}",
                    }

                gate_decision = evaluate_trade_gate(
                    message=msg,
                    ticker=ticker_raw,
                    thesis_ticker=thesis_ticker,
                    qty=qty_raw,
                    limit_price=price_raw,
                    run_id=run_id,
                )
                if gate_decision.status != "ALLOW":
                    writer = get_stream_writer()
                    writer(
                        {
                            "type": "PAPER_ORDER_BLOCKED",
                            "run_id": run_id,
                            "ticker": ticker_raw,
                            "step": "f51_trade_gate",
                            "status": "blocked",
                            "reason": gate_decision.reason,
                            "reason_code": gate_decision.reason_code,
                            "gates_failed": gate_decision.gates_failed,
                        }
                    )
                    record_blocked_order(
                        gate_decision, message=msg, ticker=ticker_raw, run_id=run_id
                    )
                    claim_idempotency_keys(
                        idem_keys, {"status": "blocked", "reason": gate_decision.reason_code}
                    )
                    logger.info(
                        "tool_executor_gate_blocked",
                        ticker=ticker_raw,
                        reason_code=gate_decision.reason_code,
                        gates_failed=gate_decision.gates_failed,
                    )
                    result = {
                        "blocked": True,
                        "reason": f"f51_trade_gate:{gate_decision.reason_code}",
                        "reason_code": gate_decision.reason_code,
                        "message": f"Ordem bloqueada pelo F51 Trade Gate: {gate_decision.reason}",
                    }
                    return result

                # ALLOW path: atomic idempotency claim
                # The is_duplicate() pre-check above is a plain existence test with TOCTOU:
                # two concurrent requests for the same key can both pass it before either
                # writes the marker. claim_idempotency_keys() now claims EVERY key of
                # this intent with exclusive file create (O_CREAT|O_EXCL); only the first
                # caller wins, and a lost race on any one key counts as duplicate rather
                # than a silent re-submission. Claiming just the current window would
                # still let two attempts either side of a boundary each win their own.
                if not claim_idempotency_keys(idem_keys, {"status": "allowed"}):
                    logger.warning(
                        "tool_executor_duplicate_blocked_race",
                        ticker=ticker_raw,
                        idempotency_key=idem_key,
                    )
                    writer = get_stream_writer()
                    writer(
                        {
                            "type": "PAPER_ORDER_BLOCKED",
                            "run_id": run_id,
                            "ticker": ticker_raw,
                            "step": "idempotency",
                            "status": "blocked",
                            "reason": f"Concurrent claim lost for key: {idem_key}",
                        }
                    )
                    return {
                        "blocked": True,
                        "reason": "f51_trade_gate:DUPLICATE_ORDER",
                        "message": f"Ordem duplicada detectada (concurrent claim lost): {idem_key}",
                    }
            except ImportError:
                logger.warning("tool_executor_gate_unavailable")
                return {
                    "blocked": True,
                    "reason": "f51_trade_gate_unavailable",
                    "message": "Ordem bloqueada: F51 Trade Gate indisponível.",
                }
            # Fronteira fail-closed do F51 Trade Gate: erro inesperado bloqueia a ordem.
            except Exception as exc:  # noqa: BLE001
                logger.error("tool_executor_gate_error", error=str(exc)[:200])
                return {
                    "blocked": True,
                    "reason": f"f51_trade_gate_error:{str(exc)[:80]}",
                    "message": "Ordem bloqueada por erro no F51 Trade Gate.",
                }

            # FORCE expert committee before ANY paper order.
            # Bob cannot shoot without consulting his advisors.
            ticker = args.get("ticker", "").upper()

            # ── Lesson-based block: if this ticker already lost money, BLOCK ──
            blocked_lesson = _check_lesson_block(ticker)
            if blocked_lesson:
                writer = get_stream_writer()
                writer(
                    {
                        "type": "PIPELINE_STEP",
                        "step": "tool_executor",
                        "status": "blocked",
                        "reason": f"lesson_based_block: {blocked_lesson['title']}",
                    }
                )
                result = {
                    "blocked": True,
                    "reason": "lesson_based_block",
                    "lesson": blocked_lesson,
                    "message": f"Ordem bloqueada por lição aprendida: {blocked_lesson['title']}. "
                    f"Este ticker já causou prejuízo por: {blocked_lesson['content'][:100]}...",
                }
                return result

            # ── FeedbackLoop: check_before_trade — bloqueia se tese repete erro ──
            thesis = args.get("thesis", args.get("reason", ""))
            if thesis:
                try:
                    from core.trading.feedback_loop import get_feedback_loop

                    fb = get_feedback_loop()
                    block_reason = fb.check_before_trade(ticker, thesis)
                    if block_reason:
                        writer = get_stream_writer()
                        writer(
                            {
                                "type": "PIPELINE_STEP",
                                "step": "tool_executor",
                                "status": "blocked",
                                "reason": f"feedback_loop_block: {block_reason}",
                            }
                        )
                        result = {
                            "blocked": True,
                            "reason": "feedback_loop_block",
                            "message": f"Ordem bloqueada pelo FeedbackLoop: {block_reason}",
                        }
                        return result
                # FeedbackLoop indisponível não bloqueia o trade (fronteira de melhor esforço).
                except Exception as exc:  # noqa: BLE001
                    logger.debug("feedback_loop_unavailable", error=str(exc)[:200])

            if ticker and state.get("_experts_ran_for", "") != ticker:
                writer = get_stream_writer()
                writer(
                    {
                        "type": "PIPELINE_STEP",
                        "step": "tool_executor",
                        "status": "running",
                        "mode": "forcing_expert_committee",
                    }
                )
                # Comite em paralelo (2026-09-05): o loop serial era heranca do
                # slot unico do llama-server local; experts rodam na API.
                expert_results = await run_experts_parallel(
                    {
                        **state,
                        "ticker": ticker,
                        "data_context": state.get("data_context", ""),
                    },
                    EXPERT_ROLES,
                    gateway=gateway,
                )
                state["expert_results"] = expert_results
                state["_experts_ran_for"] = ticker
                collected = await node_collect_experts(state)
                state.update(collected)
                result = await _submit_paper_order(state, args)
            else:
                result = await _submit_paper_order(state, args)

        elif tool_name == "social_forensics":
            # Gather Reddit posts across multiple subreddits with higher limit
            ticker = args.get("ticker", state.get("ticker", ""))
            query = args.get("query", state.get("message", ""))
            social_context = await _gather_social_context(ticker, query)
            state["data_context"] = social_context
            state["role"] = "social_forensics"
            result = await node_expert(state, gateway=gateway)

            # Extract manipulation score from expert response and set veto
            expert_results = result.get("expert_results", [])
            for er in expert_results:
                response_text = er.get("response", "")
                import re

                manip_match = re.search(
                    r"(?:Manipulation|Pump\s*&?\s*Dump)\s*Score:\s*(\d+)\s*/\s*100", response_text
                )
                if manip_match:
                    score = int(manip_match.group(1))
                    if score >= 70:
                        result["social_forensics_veto"] = {
                            "reason": f"social_forensics manipulation_score={score}",
                            "manipulation_score": score,
                            "expert": "social_forensics",
                        }
                    break
            from core.trading.outcome_learning import get_effective_expert_weights

            result["expert_weights"] = get_effective_expert_weights()

        elif tool_name == "bob_search":
            # Bob wants to search for current information.
            # Uses RAG forensics + web context as his "caderninho".
            query = args.get("query", state.get("message", ""))
            state["rag_query"] = query
            result = await node_rag_forensics(state)
            # Also inject a note that Bob should treat this as supplementary
            rag_context = result.get("rag_context", "")
            if rag_context:
                result["data_context"] = f"[BOB SEARCH RESULTS for '{query}']:\n{rag_context}"
        elif tool_name == "query_expert":
            role = args.get("role")
            query = args.get("query", state.get("message", ""))
            if not role:
                result = {"error": "query_expert requires role"}
            else:
                expert_state = {
                    **state,
                    "role": role,
                    "message": query,
                    "data_context": state.get("data_context", query),
                }
                res = await node_expert(expert_state, gateway=gateway)
                expert_results = res.get("expert_results", [])
                expert_response = ""
                for er in expert_results:
                    if er.get("role") == role:
                        expert_response = er.get("response", "")
                        break
                result = {
                    "role": role,
                    "query": query,
                    "response": expert_response or "Expert returned no response",
                    "expert_results": expert_results,
                    "last_tool_result": f"Expert '{role}' response to query '{query}':\n{expert_response}",
                }

        elif tool_name == "call_math_calculator":
            ticker = args.get("ticker", state.get("ticker", "")).upper()
            if not ticker:
                result = {"error": "call_math_calculator requires ticker"}
            else:
                from core.math.math_hub import MathHub

                math_hub = MathHub()
                calc_state = {**state, "ticker": ticker}
                math_report = math_hub.calculate_all(calc_state)
                math_prompt = math_hub.to_deepseek_prompt(math_report)
                result = {
                    "ticker": ticker,
                    "math_report": math_report,
                    "math_prompt": math_prompt,
                    "last_tool_result": f"Math Calculator results for ticker {ticker}:\n{math_prompt}",
                }

        elif tool_name == "get_live_financial_data":
            ticker = args.get("ticker", state.get("ticker", "")).upper()
            if not ticker:
                result = {"error": "get_live_financial_data requires ticker"}
            else:
                from core.data_collector.collector import (
                    tool_calculate_risk_metrics,
                    tool_get_market_price,
                )

                try:
                    price_data = await tool_get_market_price(ticker)
                # Fronteira de melhor esforço: falha no fetch de preço vira payload de erro.
                except Exception as e:  # noqa: BLE001
                    price_data = {"error": f"price_fetch_failed: {e}"}
                try:
                    risk_data = await tool_calculate_risk_metrics(ticker)
                # Fronteira de melhor esforço: falha no cálculo de risco vira payload de erro.
                except Exception as e:  # noqa: BLE001
                    risk_data = {"error": f"risk_calc_failed: {e}"}

                collector_res = await node_collector(
                    {**state, "ticker": ticker, "route": "ticker_analysis"}, config=config
                )

                result = {
                    "ticker": ticker,
                    "live_price": price_data,
                    "risk_metrics": risk_data,
                    "data_context": collector_res.get("data_context", ""),
                    "last_tool_result": f"Live Financial Data for {ticker}:\n- Price Data: {price_data}\n- Risk Metrics: {risk_data}\n- Context details: {collector_res.get('data_context', '')[:1000]}...",
                }

        elif tool_name == "calculate":
            expression = str(args.get("expression", "")).strip()
            if not expression:
                result = {"error": "calculate requires 'expression' argument"}
            else:
                try:
                    from tools.custom_tools import register_custom_tools

                    class _ToolReg:
                        def register(self, **kw):
                            if kw.get("name") == "calculate":
                                self.calc_fn = kw["func"]

                    reg = _ToolReg()
                    register_custom_tools(reg)
                    calc_result = reg.calc_fn(expression)
                    result = {
                        "expression": expression,
                        "result": calc_result,
                        "last_tool_result": f"calculate('{expression}') = {calc_result}",
                    }
                # Fronteira de melhor esforço: falha na calculadora vira payload de erro.
                except Exception as e:  # noqa: BLE001
                    result = {"error": f"calculate_failed: {e}"}

        else:
            return _tool_blocked_payload(state, tool_name, "it is not executable here")

        return {
            **result,
            "executed_tools": next_executed_tools,
            "executed_tool_counts": next_executed_tool_counts,
            "route": state.get("route", ""),  # Preserve route for forced tool checks
            "ticker": state.get("ticker", ""),  # Preserve ticker
        }

    # Fronteira externa do executor: qualquer falha de tool vira payload de erro para o agente.
    except Exception as exc:  # noqa: BLE001
        logger.error("tool_execution_failed", tool=tool_name, error=str(exc)[:200])
        return {
            "executed_tools": next_executed_tools,
            "executed_tool_counts": next_executed_tool_counts,
            "errors": state.get("errors", []) + [f"tool_{tool_name}:{exc}"],
        }


_MAX_AGENT_ITERATIONS = 8


def route_after_agent(state: dict) -> str:
    """Route from agent to tool_executor or to explanation based on tool_call."""
    tool_call = state.get("agent_tool_call")
    iterations = state.get("agent_iterations", 0)

    if iterations >= _MAX_AGENT_ITERATIONS:
        logger.warning("Agent loop limit reached (%d iterations), forcing final_answer", iterations)
        return "explanation"

    if not tool_call or "tool" not in tool_call:
        return "explanation"

    if tool_call["tool"] == "final_answer":
        return "explanation"

    return "tool_executor"
