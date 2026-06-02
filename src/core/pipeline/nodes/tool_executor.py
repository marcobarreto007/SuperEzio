"""Tool Executor node — executes tools requested by the Agent."""

from __future__ import annotations

import logging
from datetime import datetime

from langgraph.config import get_stream_writer

from ..contracts import AgentToolCall
from .collector import node_collector
from .f51 import node_f51_verdict
from .experts import node_collect_experts, node_expert
from .neural_decision import node_neural_decision
from .sdca_firewall import node_sdca_firewall
from .rag import node_rag_forensics

logger = logging.getLogger(__name__)


_REPEATABLE_TOOLS = {"final_answer"}
_SEMI_REPEATABLE_LIMITS: dict[str, int] = {"collect_data": 2}


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
        "pennystocks", "wallstreetbets", "stocks", "investing",
        "CanadianInvestor", "StockMarket", "RobinHoodPennyStocks",
        "smallstreetbets", "Shortsqueeze", "Daytrading",
    ]
    search_term = ticker or query or ""
    if not search_term:
        return "(no ticker or query provided)"

    posts: list[str] = []

    def _fetch(subreddit: str) -> None:
        import urllib.request, json, urllib.parse
        try:
            url = (
                f"https://www.reddit.com/r/{subreddit}/search.json"
                f"?q={urllib.parse.quote_plus(search_term)}"
                f"&restrict_sr=1&sort=top&t=month&limit=15&raw_json=1"
            )
            req = urllib.request.Request(url, headers={"User-Agent": "SuperEzio/1.0 forensic-research"})
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
                dt = datetime.utcfromtimestamp(created).strftime("%Y-%m-%d %H:%M") if created else "?"
                posts.append(
                    f"[r/{subreddit}] u/{author} | {score}pts {upvote*100:.0f}%up | {comments}c | {dt}\n"
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
        f"{'='*70}\n\n"
    )
    return header + "\n---\n".join(posts)


async def _pennylab_stub(state: dict) -> dict:
    ticker = state.get("ticker", "")
    if not ticker:
        return {"pennylab": {}}
    try:
        from experts.pennylab.pipeline_hook import analyze_ticker_sync

        result = await __import__("asyncio").to_thread(analyze_ticker_sync, ticker)
        return {"pennylab": result}
    except Exception as exc:
        return {"pennylab": {"ticker": ticker, "decision": None, "error": str(exc)[:200]}}


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

        elif tool_name == "f51_firewall":
            result = await node_f51_verdict(state)

        elif tool_name == "pennylab":
            result = await _pennylab_stub(state)

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
                # Parse manipulation score from Gemini output
                import re
                manip_match = re.search(r"(?:Manipulation|Pump\s*&?\s*Dump)\s*Score:\s*(\d+)\s*/\s*100", response_text)
                if manip_match:
                    score = int(manip_match.group(1))
                    if score >= 70:
                        result["social_forensics_veto"] = {
                            "reason": f"social_forensics manipulation_score={score}",
                            "manipulation_score": score,
                            "expert": "social_forensics",
                        }
                    break
            # Also compute dynamic weights for this scenario
            result["expert_weights"] = {
                "social_forensics": 0.25,
                "sentiment": 0.15,
                "macro_risk": 0.15,
                "fundamental_value": 0.20,
                "momentum_technical": 0.15,
                "contrarian_opportunity": 0.10,
            }
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
