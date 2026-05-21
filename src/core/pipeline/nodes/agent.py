"""Agent node — the core LLM orchestrator using ReAct / Tool Calling."""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from langgraph.config import get_stream_writer

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """
You are Bob, the SuperEzio CEO and autonomous financial agent.
You must fulfill the user's request by deciding which tools to call.
You have access to the following tools:

1. collect_data
   Description: Fetches market prices, fundamentals, news, and technicals for a ticker.
   Input schema: {"ticker": "AAPL"}
   
2. f51_firewall
   Description: Runs the F51 risk and data veracity engine on collected data.
   Input schema: {}
   
3. pennylab
   Description: Runs forensic manipulation checks on penny stocks.
   Input schema: {}
   
4. run_experts
   Description: Invokes the expert committee (fundamental, technical, risk, macro, quant, sentiment).
   Input schema: {}
   
5. neural_decision
   Description: Runs the Neural Decision Expert to get regime and expected return.
   Input schema: {}
   
6. sdca_firewall
   Description: Runs the final SDCA Cognitive Risk Firewall before taking action.
   Input schema: {}
   
7. rag_forensics
   Description: Searches for historical fraud or manipulation patterns.
   Input schema: {}
   
8. market_scan
   Description: Scans the market for opportunities based on criteria.
   Input schema: {"query": "natural language query describing scan"}
   
9. final_answer
   Description: Provides the final natural language answer to the user.
   Input schema: {"content": "Your final verdict and analysis in the user's language."}

**CRITICAL INSTRUCTIONS**:
- You must ONLY output a valid JSON object. No other text.
- Format: {"tool": "tool_name", "args": {"arg1": "val1"}}
- Call one tool at a time.
- If you need market data, call collect_data first.
- If the user asks a general question that doesn't need data, you can just call final_answer directly.
- NEVER invent data.
"""

def _parse_tool_call(text: str) -> dict[str, Any] | None:
    try:
        # Extract JSON if there's markdown
        match = re.search(r"\{.*\}", text.strip(), re.DOTALL)
        if match:
            return json.loads(match.group(0))
        return json.loads(text.strip())
    except Exception:
        return None

async def node_agent(state: dict, *, gateway=None, config=None, mandamentos=None) -> dict:
    writer = get_stream_writer()
    run_id = state.get("run_id", "")
    iterations = state.get("agent_iterations", 0)

    if iterations > 7:
        # Failsafe
        writer({"type": "CHUNK", "content": "\n[SYSTEM] Agent loop timeout. Too many tool calls."})
        return {"agent_tool_call": {"tool": "final_answer", "args": {"content": "I apologize, but I encountered an error and could not complete the analysis in time."}}}

    writer(
        {
            "type": "PIPELINE_STEP",
            "run_id": run_id,
            "step": "ceo_primary",
            "status": "started",
        }
    )

    if gateway is None:
        return {"errors": state.get("errors", []) + ["no_gateway"]}

    # Build ReAct Prompt
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    messages.append({"role": "user", "content": f"User Request: {state.get('message', '')}"})
    
    # Inject current state context as observations
    observations = []
    if state.get("ticker"):
        observations.append(f"Current Ticker: {state.get('ticker')}")
    if state.get("data_context"):
        observations.append(f"Data Collected:\n{state.get('data_context')[:1500]}")
    if state.get("f51_verdict"):
        observations.append(f"F51 Verdict:\n{json.dumps(state.get('f51_verdict'))}")
    if state.get("expert_summary"):
        observations.append(f"Expert Committee:\n{state.get('expert_summary')}")
    if state.get("neural_decision"):
        observations.append(f"Neural Decision:\n{json.dumps(state.get('neural_decision'))}")
    if state.get("sdca_firewall"):
        observations.append(f"SDCA Firewall:\n{json.dumps(state.get('sdca_firewall'))}")
    if state.get("pennylab_result") or state.get("pennylab"):
        observations.append(f"PennyLab:\n{json.dumps(state.get('pennylab_result') or state.get('pennylab'))}")
    if state.get("scan"):
        observations.append(f"Market Scan Results:\n{json.dumps(state.get('scan').get('candidates', []))}")
        
    if observations:
        messages.append({"role": "user", "content": "Observations so far:\n" + "\n\n".join(observations)})
        
    messages.append({"role": "user", "content": "What is the next tool you want to call? Remember to output ONLY JSON."})

    try:
        from ...model_serving.providers import CEO_PROVIDER_NAME
        
        raw = await gateway.chat_completion(
            messages=messages,
            temperature=0.1,
            max_tokens=1024,
            preferred_provider=CEO_PROVIDER_NAME,
            json_mode=True
        )
        
        # Clean thinking blocks
        if "<think>" in raw:
            raw = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL).strip()
            
        tool_call = _parse_tool_call(raw)
        
        if tool_call and "tool" in tool_call:
            if tool_call["tool"] == "final_answer":
                # Final output
                content = tool_call.get("args", {}).get("content", "Analysis complete.")
                writer({"type": "CHUNK", "content": content})
                writer(
                    {
                        "type": "PIPELINE_STEP",
                        "run_id": run_id,
                        "step": "ceo_primary",
                        "status": "completed",
                    }
                )
                return {"final": content, "agent_tool_call": tool_call, "agent_iterations": iterations + 1}
            else:
                return {"agent_tool_call": tool_call, "agent_iterations": iterations + 1}
        else:
            # Fallback
            return {"agent_tool_call": {"tool": "final_answer", "args": {"content": "I couldn't decide on a tool. The request might be malformed."}}}
            
    except Exception as exc:
        logger.error(f"Agent error: {exc}")
        return {"agent_tool_call": {"tool": "final_answer", "args": {"content": f"Internal agent error: {exc}"}}}
