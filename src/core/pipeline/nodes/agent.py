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


def _is_portuguese_request(message: str) -> bool:
    raw = (message or "").lower()
    return any(
        token in raw
        for token in (
            "bob",
            "voce",
            "você",
            "tenho",
            "investir",
            "risco",
            "mercado",
            "pesquisa",
            "pequeno",
            "comprar",
        )
    )


def _candidate_line(item: dict[str, Any]) -> str:
    ticker = item.get("ticker") or "?"
    price = item.get("price")
    provider = item.get("provider") or item.get("source") or "provider"
    if price is None:
        return f"- {ticker}: preco indisponivel no scan; fonte {provider}."
    return f"- {ticker}: preco observado {price}; fonte {provider}."


def _market_scan_answer(state: dict) -> str:
    message = state.get("message", "")
    scan = state.get("scan") or {}
    candidates = [c for c in scan.get("candidates", []) if isinstance(c, dict)]
    errors = scan.get("source_errors") or []

    if _is_portuguese_request(message):
        lines = [
            "Bob CEO: pesquisei o universo de mercado pequeno com perfil de alto risco, mas isso e watchlist para estudo, nao ordem de compra.",
            "",
        ]
        if candidates:
            lines.append("Candidatos retornados pelo scanner:")
            lines.extend(_candidate_line(item) for item in candidates[:6])
        else:
            lines.append(
                "O scanner nao retornou candidatos confiaveis agora. Eu nao vou inventar tickers."
            )
        if errors:
            lines.append("")
            lines.append("Limite de dados: " + "; ".join(str(err) for err in errors[:3]))
        lines.extend(
            [
                "",
                "Para 100 por posicao e risco alto, meu filtro pratico e:",
                "- liquidez suficiente para entrar e sair sem spread absurdo;",
                "- evitar empresa com diluicao agressiva, reverse split recente ou comunicados obscuros;",
                "- procurar catalisador verificavel, nao so hype social;",
                "- limitar perda maxima por posicao antes de clicar em qualquer coisa;",
                "- estudar filings/noticias antes de transformar a lista em compra.",
                "",
                "Proximo passo seguro: escolha 3 tickers dessa lista e me peca uma checagem ticker por ticker com risco, liquidez, manipulacao e plano de perda maxima.",
            ]
        )
        return "\n".join(lines)

    lines = [
        "Bob CEO: I scanned the small-cap/high-risk market universe, but this is a study watchlist, not a buy order.",
        "",
    ]
    if candidates:
        lines.append("Scanner candidates:")
        lines.extend(_candidate_line(item) for item in candidates[:6])
    else:
        lines.append("The scanner did not return reliable candidates right now. I will not invent tickers.")
    if errors:
        lines.append("")
        lines.append("Data limit: " + "; ".join(str(err) for err in errors[:3]))
    lines.extend(
        [
            "",
            "For 100 per position with high risk, filter for liquidity, dilution risk, recent filings, spread, real catalysts, and a predefined maximum loss.",
            "Next safe step: pick 3 tickers from the list and ask me for ticker-by-ticker risk, liquidity, manipulation, and loss-limit checks.",
        ]
    )
    return "\n".join(lines)


def _loop_failsafe_answer(state: dict) -> str:
    if state.get("scan"):
        return _market_scan_answer(state)
    if _is_portuguese_request(state.get("message", "")):
        return (
            "Bob CEO: encerrei o ciclo de ferramentas antes de gastar mais tempo. "
            "Ainda posso ajudar, mas preciso reduzir o escopo: mande um ticker, setor, pais ou diga se quer somente uma watchlist de estudo."
        )
    return (
        "Bob CEO: I stopped the tool cycle before wasting more time. "
        "Narrow the scope to a ticker, sector, country, or a study watchlist and I can continue."
    )


def _final_payload(content: str, iterations: int) -> dict[str, Any]:
    return {
        "final": content,
        "agent_tool_call": {"tool": "final_answer", "args": {"content": content}},
        "agent_iterations": iterations + 1,
    }


async def node_agent(state: dict, *, gateway=None, config=None, mandamentos=None) -> dict:
    writer = get_stream_writer()
    run_id = state.get("run_id", "")
    iterations = state.get("agent_iterations", 0)

    if iterations > 7:
        content = _loop_failsafe_answer(state)
        writer({"type": "CHUNK", "content": content})
        return _final_payload(content, iterations)

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

    if state.get("route") == "market_scan" and state.get("scan"):
        content = _market_scan_answer(state)
        writer({"type": "CHUNK", "content": content})
        writer(
            {
                "type": "PIPELINE_STEP",
                "run_id": run_id,
                "step": "ceo_primary",
                "status": "completed",
                "provider": "deterministic_market_scan",
            }
        )
        return _final_payload(content, iterations)

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
