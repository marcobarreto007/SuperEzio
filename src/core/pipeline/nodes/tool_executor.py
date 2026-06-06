"""Tool Executor node — executes tools requested by the Agent."""

from __future__ import annotations

import logging
import os
from typing import Any

from langgraph.config import get_stream_writer

from ..contracts import AgentToolCall
from .collector import node_collector
from .f51 import node_f51_verdict
from .experts import node_collect_experts, node_expert
from .neural_decision import node_neural_decision
from .sdca_firewall import node_sdca_firewall
from .rag import node_rag_forensics
from core.math.penny_momentum import PennyMomentumConfig, simulate_penny_momentum_backtest

# PennyLab: imported at module level — no lazy import on hot tool path
try:
    from experts.pennylab.pipeline_hook import analyze_ticker_sync as _pennylab_analyze

    _PENNYLAB_AVAILABLE = True
except ImportError:
    _PENNYLAB_AVAILABLE = False

    def _pennylab_analyze(ticker: str):  # type: ignore[misc]
        return {"ticker": ticker, "decision": None, "error": "pennylab_module_not_found"}


logger = logging.getLogger(__name__)


_REPEATABLE_TOOLS = {"final_answer"}
_SEMI_REPEATABLE_LIMITS: dict[str, int] = {"collect_data": 2}


def _paper_order_submission_error(state: dict, args: dict) -> str:
    if os.getenv("SUPEREZIO_ENABLE_PAPER_ORDER_SUBMIT", "0").strip().lower() not in {
        "1",
        "true",
        "yes",
        "on",
    }:
        return "paper_order_submission_disabled_by_env"
    if not state.get("ticket_allowed", False):
        return "paper_order_not_allowed_by_cognitive_contract"
    order_type = str(args.get("order_type") or args.get("type") or "").strip().upper()
    if order_type != "LMT":
        return "limit_order_required"
    try:
        if float(args.get("limit_price") or 0) <= 0:
            return "missing_limit_price"
    except (TypeError, ValueError):
        return "invalid_limit_price"
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
            with urllib.request.urlopen(req, timeout=8) as resp:
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
                    datetime.utcfromtimestamp(created).strftime("%Y-%m-%d %H:%M")
                    if created
                    else "?"
                )
                posts.append(
                    f"[r/{subreddit}] u/{author} | {score}pts {upvote * 100:.0f}%up | {comments}c | {dt}\n"
                    f"TITLE: {title[:300]}\n"
                    f"BODY: {selftext[:400]}\n"
                )
        except Exception as e:
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
    except Exception as exc:
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

    if not ohlcv_by_symbol:
        content = (
            "[MATHCORE BACKTEST ERROR]\n"
            "strategy=penny_momentum_breakout\n"
            "status=missing_ohlcv\n"
            "reason=Provide ohlcv_by_symbol, explicit tickers, or run market_scan first."
        )
        return {
            "penny_momentum_backtest": {
                "error": "missing_ohlcv",
                "strategy": "penny_momentum_breakout",
            },
            "data_context": _append_context(state.get("data_context", ""), content),
            "errors": state.get("errors", []) + ["penny_momentum_backtest:missing_ohlcv"],
        }

    result = simulate_penny_momentum_backtest(
        ohlcv_by_symbol,
        config=_penny_config_from_args(args),
    )
    context = _format_penny_backtest_context(result)
    return {
        "penny_momentum_backtest": result,
        "data_context": _append_context(state.get("data_context", ""), context),
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
    except Exception:
        return {}

    out: dict[str, list[dict[str, Any]]] = {}
    for ticker in tickers:
        try:
            result = hub.get_candles(ticker, timeframe=timeframe)
            candles = result.get("candles") or result.get("ohlcv") or []
            if candles:
                out[ticker] = candles
        except Exception as exc:
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
    return (
        "[MATHCORE BACKTEST]\n"
        f"strategy={result.get('strategy')}\n"
        f"verdict={result.get('verdict')}\n"
        f"total_return={result.get('total_return_pct')}%\n"
        f"sharpe={result.get('sharpe')}\n"
        f"max_drawdown={result.get('max_drawdown_pct')}%\n"
        f"win_rate={result.get('win_rate_pct')}%\n"
        f"trade_count={result.get('trade_count')}\n"
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
    import asyncio as _asyncio

    permission_error = _paper_order_submission_error(state, args)
    if permission_error:
        return {"submit_paper_order_error": permission_error}

    symbol = str(args.get("ticker", args.get("symbol", ""))).upper()
    action = str(args.get("action", args.get("side", "buy"))).lower()
    qty = float(args.get("qty", args.get("quantity", args.get("shares", 10))))
    limit_price = float(args.get("limit_price"))

    if not symbol:
        return {"submit_paper_order_error": "missing_ticker"}

    def _do_order():
        import asyncio as _aio
        from ib_insync import IB, LimitOrder, Stock

        # ib_insync needs an event loop; create one in this thread
        loop = _aio.new_event_loop()
        _aio.set_event_loop(loop)

        ib = IB()
        ib.connect("127.0.0.1", 7497, clientId=99)
        contract = Stock(symbol, "SMART", "USD")
        ib.qualifyContracts(contract)
        trade = ib.placeOrder(
            contract,
            LimitOrder("BUY" if action in ("buy", "long") else "SELL", qty, limit_price),
        )
        ib.sleep(3)
        result = {
            "order_id": trade.order.orderId,
            "symbol": symbol,
            "action": "BUY" if action in ("buy", "long") else "SELL",
            "qty": qty,
            "order_type": "LMT",
            "limit_price": limit_price,
            "status": trade.orderStatus.status,
            "filled": trade.orderStatus.filled,
            "avg_price": trade.orderStatus.avgFillPrice,
        }
        for p in ib.positions():
            if p.contract.symbol == symbol:
                result["position"] = f"{p.position} shares @ avg {p.avgCost}"
        ib.disconnect()
        loop.close()
        return result

    try:
        result = await _asyncio.to_thread(_do_order)
        return {"submit_paper_order_result": result}
    except Exception as exc:
        return {"submit_paper_order_error": str(exc)[:200]}


async def node_tool_executor(state: dict, *, gateway=None, config=None) -> dict:
    tool_call = state.get("agent_tool_call")
    if not tool_call:
        return {}

    try:
        validated_call = AgentToolCall.model_validate(tool_call)
    except Exception as exc:
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
    if tool_name == "submit_paper_order" and tool_name in executed_tools:
        if not paper_order_has_broker_result:
            executed_tools = [tool for tool in executed_tools if tool != tool_name]
            executed_tool_counts = {
                key: value for key, value in executed_tool_counts.items() if key != tool_name
            }
            semi_count = 0
    if tool_name in executed_tools and not repeatable:
        if semi_limit is None or semi_count >= semi_limit:
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
            roles = [
                "macro_risk",
                "fundamental_value",
                "momentum_technical",
                "contrarian_opportunity",
                "sentiment",
            ]
            results = []
            for role in roles:
                res = await node_expert({**state, "role": role}, gateway=gateway)
                if "expert_results" in res:
                    results.extend(res["expert_results"])

            result = await node_collect_experts({**state, "expert_results": results})

        elif tool_name == "neural_decision":
            result = await node_neural_decision(state)

        elif tool_name == "sdca_firewall":
            result = await node_sdca_firewall(state)

        elif tool_name == "rag_forensics":
            result = await node_rag_forensics(state)

        elif tool_name == "submit_paper_order":
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
            result["expert_weights"] = {
                "social_forensics": 0.25,
                "sentiment": 0.15,
                "macro_risk": 0.15,
                "fundamental_value": 0.20,
                "momentum_technical": 0.15,
                "contrarian_opportunity": 0.10,
            }

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
        else:
            return _tool_blocked_payload(state, tool_name, "it is not executable here")

        return {
            **result,
            "executed_tools": next_executed_tools,
            "executed_tool_counts": next_executed_tool_counts,
        }

    except Exception as exc:
        logger.error(f"Tool execution failed: {exc}")
        return {
            "executed_tools": next_executed_tools,
            "executed_tool_counts": next_executed_tool_counts,
            "errors": state.get("errors", []) + [f"tool_{tool_name}:{exc}"],
        }

    return {}


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
