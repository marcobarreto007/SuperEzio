"""Tool Executor node — executes tools requested by the Agent."""

from __future__ import annotations

import logging


from .collector import node_collector
from .f51 import node_f51_verdict
from .experts import node_collect_experts, node_expert
from .neural_decision import node_neural_decision
from .sdca_firewall import node_sdca_firewall
from .rag import node_rag_forensics

logger = logging.getLogger(__name__)

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
    if not tool_call or "tool" not in tool_call:
        return {}

    tool_name = tool_call["tool"]
    args = tool_call.get("args", {})
    
    # We map tool names to the actual nodes.
    # The original nodes emit SSE PIPELINE_STEP events, so the UI will update correctly.
    
    try:
        if tool_name == "collect_data":
            # Set the route to ticker_analysis so collector knows what to do
            ticker = args.get("ticker", state.get("ticker", ""))
            return await node_collector({**state, "ticker": ticker, "route": "ticker_analysis"}, config=config)
            
        elif tool_name == "market_scan":
            # Set route to market_scan
            return await node_collector({**state, "route": "market_scan", "message": args.get("query", state.get("message"))}, config=config)
            
        elif tool_name == "f51_firewall":
            return await node_f51_verdict(state)
            
        elif tool_name == "pennylab":
            return await _pennylab_stub(state)
            
        elif tool_name == "run_experts":
            # Usually experts runs fan-out. We can just run a single expert stub that does the summary,
            # or we run node_expert for all roles in a loop to populate expert_results.
            # For simplicity, we just run the fundamental and technical experts directly, then run node_collect_experts logic.
            # But graph.py used Send() for experts. We will just run them sequentially here for the agent.
            roles = ["fundamental", "technical", "risk", "macro", "quant", "sentiment"]
            results = []
            for role in roles:
                res = await node_expert({**state, "role": role}, gateway=gateway)
                if "expert_results" in res:
                    results.extend(res["expert_results"])
            
            return await node_collect_experts({**state, "expert_results": results})
            
        elif tool_name == "neural_decision":
            return await node_neural_decision(state)
            
        elif tool_name == "sdca_firewall":
            return await node_sdca_firewall(state)
            
        elif tool_name == "rag_forensics":
            return await node_rag_forensics(state)
            
    except Exception as exc:
        logger.error(f"Tool execution failed: {exc}")
        return {"errors": state.get("errors", []) + [f"tool_{tool_name}:{exc}"]}
        
    return {}

def route_after_agent(state: dict) -> str:
    """Route from agent to tool_executor or to explanation based on tool_call."""
    tool_call = state.get("agent_tool_call")
    if not tool_call or "tool" not in tool_call:
        return "explanation"
        
    if tool_call["tool"] == "final_answer":
        return "explanation"
        
    return "tool_executor"
