"""CEO node — Qwen3.6-35B local analysis via llama.cpp."""

from __future__ import annotations

import asyncio
import os
import re
import time
from langgraph.config import get_stream_writer

from ..prompts.builder import (
    _ceo_assistant_prefix,
    _evaluate_module_coverage,
    build_ceo_prompt,
    ceo_system_prompt,
    missing_ceo_text,
)
from ..security import sanitize_output

CEO_PROVIDER_NAME = "ceo"


def capabilities_text(message: str = "") -> str:
    """Deterministic answer for natural-language capability/tool questions."""
    if _is_portuguese_request(message):
        return (
            "Bob CEO: eu consigo responder perguntas financeiras em linguagem natural, "
            "mas eu nao executo corretora e nao transformo conversa em ordem de compra ou venda.\n\n"
            "O que posso fazer por voce:\n"
            "- Explicar um ticker, grafico ou risco em portugues simples.\n"
            "- Montar checklist antes de comprar, vender, esperar ou estudar melhor.\n"
            "- Verificar dados de preco, tecnicos, fundamentos, noticias, sentimento, macro, quant e risco.\n"
            "- Rodar F51, SDCA Firewall, NeuralDecisionExpert, comite de especialistas e RAG forense.\n"
            "- Apontar sinais de FOMO, alavancagem, hype social, baixa qualidade de dados e possivel manipulacao.\n\n"
            "Como usar: pergunte como pessoa. Exemplo: "
            "'Bob, quais riscos devo olhar antes de comprar AAPL?' ou "
            "'Explique esse grafico e me diga o que estudar antes de agir.'\n\n"
            "Limite importante: eu dou suporte de decisao, evidencias e proximos passos defensivos. "
            "A decisao final e sua; nenhuma acao de broker e executada."
        )
    return (
        "I can answer natural-language questions, but SuperEzio is not a generic chat toy. "
        "For market analysis, I use a deterministic pipeline before the CEO verdict.\n\n"
        "Tools/modules I use:\n"
        "- Orchestrator: classifies the request, ticker, horizon, and required route.\n"
        "- DataCollector: collects price, fundamentals, technicals, news sentiment, social pulse, "
        "macro context, quant data, and risk inputs.\n"
        "- F51 gate: checks veracity, consensus, proxy reward, robustness, uncertainty, and danger.\n"
        "- Expert committee: runs fundamental, technical, risk, macro, quant, and sentiment experts.\n"
        "- NeuralDecisionExpert: estimates directional probability, expected return, drawdown risk, "
        "uncertainty, and market regime.\n"
        "- RAG forensics: compares the setup against historical manipulation and fraud patterns.\n"
        "- CEO/Qwen: converts the evidence into a natural-language decision-support brief.\n\n"
        "Important: I do not let the local Qwen model freely call tools by itself. "
        "The application runs the tools first, then sends the verified evidence to the CEO. "
        "That is deliberate: it prevents the model from inventing data or fake tool calls."
    )


def _strip_thinking(text: str) -> str:
    """Remove <think> blocks from model output."""
    if not text:
        return ""
    result = text
    while True:
        lower = result.lower()
        start = lower.find("<think>")
        if start == -1:
            break
        end = lower.find("</think>", start + 7)
        if end == -1:
            result = result[:start] + result[start + 7 :]
            break
        result = result[:start] + result[end + 8 :]
    return result.replace("</think>", "")


_DIRECT_TRADE_PATTERN = re.compile(
    r"\b(VERDICT\s*:|BUY|SELL|SHORT|LONG|STOP\s+LOSS|TARGET\s*:|ENTRY\s*:)\b",
    re.IGNORECASE,
)


def _is_portuguese_request(message: str) -> bool:
    raw = (message or "").lower()
    return any(
        token in raw
        for token in (
            "voce",
            "você",
            "portugues",
            "português",
            "comprar",
            "risco",
            "explique",
            "dicas",
            "conselho",
        )
    )


def _asks_capabilities(message: str) -> bool:
    raw = (message or "").lower()
    return any(
        token in raw
        for token in (
            "what can you do",
            "o que voce pode fazer",
            "o que vocÃª pode fazer",
            "como copiloto financeiro",
            "como voce pode me ajudar",
            "como vocÃª pode me ajudar",
        )
    )


def _safe_advisor_text(state: dict, generated: str) -> str:
    """Replace direct trading verdicts with advisory language."""
    ticker = state.get("ticker") or "the asset"
    neural = state.get("neural_decision") or {}
    sdca = state.get("sdca_firewall") or {}
    f51 = state.get("f51_verdict") or {}
    data = state.get("data") or {}
    technicals = data.get("technicals") if isinstance(data, dict) else {}
    price = data.get("price") if isinstance(data, dict) else {}
    message = state.get("message", "")

    rsi = None
    if isinstance(technicals, dict):
        rsi = technicals.get("rsi") or technicals.get("rsi_14")
    current = None
    if isinstance(price, dict):
        current = price.get("price") or price.get("current") or price.get("close")

    confidence = f51.get("confidence")
    uncertainty = neural.get("uncertainty")
    drawdown = neural.get("drawdown_risk")
    regime = neural.get("regime")
    sdca_decision = sdca.get("decision")

    if _is_portuguese_request(message):
        lines = [
            f"Bob CEO: eu nao vou transformar isso em ordem de trade para {ticker}.",
            "",
            "Leitura simples: o sistema encontrou dados suficientes para discutir risco e contexto, "
            "mas a decisao ainda deve ser tratada como analise, nao execucao.",
        ]
        if current is not None:
            lines.append(f"- Preco observado: {current}.")
        if rsi is not None:
            lines.append(
                f"- RSI/forca tecnica: {rsi}. Se estiver muito alto, o risco de pullback aumenta."
            )
        if regime:
            lines.append(f"- NeuralDecisionExpert: regime {regime}, incerteza {uncertainty}.")
        if drawdown is not None:
            lines.append(f"- Risco de drawdown estimado: {drawdown}.")
        if sdca_decision:
            lines.append(f"- SDCA Firewall: {sdca_decision}; isso nao executa corretora.")
        if confidence is not None:
            lines.append(f"- F51: confianca {confidence}, ainda dependente da qualidade dos dados.")
        lines.extend(
            [
                "",
                "Antes de agir, olhe: fundamentos faltantes, RSI/overbought, volatilidade, liquidez, "
                "noticias recentes, tamanho da posicao e quanto voce aceita perder.",
                "Proximo passo pratico: estudar/revisar e definir um plano pequeno e defensivo se a tese continuar valida.",
            ]
        )
        return "\n".join(lines)

    lines = [
        f"Bob CEO: I will not turn this into a trade order for {ticker}.",
        "",
        "Plain read: the system has enough evidence to discuss risk and context, but this is analysis, not execution.",
    ]
    if current is not None:
        lines.append(f"- Observed price: {current}.")
    if rsi is not None:
        lines.append(f"- RSI/technical strength: {rsi}. If it is elevated, pullback risk rises.")
    if regime:
        lines.append(f"- NeuralDecisionExpert: regime {regime}, uncertainty {uncertainty}.")
    if drawdown is not None:
        lines.append(f"- Estimated drawdown risk: {drawdown}.")
    if sdca_decision:
        lines.append(f"- SDCA Firewall: {sdca_decision}; no broker execution is performed.")
    if confidence is not None:
        lines.append(f"- F51 confidence: {confidence}, still limited by data quality.")
    lines.extend(
        [
            "",
            "Before acting, check missing fundamentals, overbought signals, volatility, liquidity, recent news, "
            "position sizing, and your maximum acceptable loss.",
            "Practical next step: study/review and define a small defensive plan only if the thesis remains valid.",
        ]
    )
    return "\n".join(lines)


def enforce_advisor_boundary(text: str, state: dict) -> str:
    """Keep Bob in advisory mode even if the local model emits a trade command."""
    if not text:
        return text
    head = text[:600]
    if _DIRECT_TRADE_PATTERN.search(head):
        return _safe_advisor_text(state, text)
    return text


async def node_ceo(
    state: dict,
    *,
    gateway=None,
    config=None,
    mandamentos: list | None = None,
) -> dict:
    """Generate the CEO analysis using local Qwen3.6-35B via llama.cpp."""
    writer = get_stream_writer()
    run_id = state.get("run_id", "")
    mandamentos = mandamentos or []

    if state.get("intent") == "explain_capabilities" or _asks_capabilities(
        state.get("message", "")
    ):
        text = capabilities_text(state.get("message", ""))
        writer(
            {
                "type": "PIPELINE_STEP",
                "run_id": run_id,
                "step": "ceo_primary",
                "status": "started",
                "provider": "deterministic",
                "local_ready": True,
            }
        )
        writer({"type": "CHUNK", "content": text})
        writer(
            {
                "type": "PIPELINE_STEP",
                "run_id": run_id,
                "step": "ceo_primary",
                "status": "completed",
                "provider": "deterministic",
                "elapsed_ms": 0,
            }
        )
        return {"final": text}

    if state.get("final"):
        writer(
            {
                "type": "PIPELINE_STEP",
                "run_id": run_id,
                "step": "ceo_primary",
                "status": "skipped_duplicate",
            }
        )
        return {}

    # ── Check local CEO health ──
    ceo_provider = None
    local_ready = False

    if gateway is not None:
        for p in gateway.providers:
            if p.name == CEO_PROVIDER_NAME:
                ceo_provider = CEO_PROVIDER_NAME
                try:
                    local_ready = await _check_health(p.base_url)
                except Exception:
                    pass
                break

    if not gateway or not ceo_provider:
        text = missing_ceo_text(
            ticker=state.get("ticker", ""),
            route=state.get("route", "general"),
            local_ready=False,
        )
        writer({"type": "MODEL_MISSING", "role": "ceo", "detail": "CEO unavailable"})
        writer({"type": "CHUNK", "content": text})
        writer(
            {
                "type": "PIPELINE_STEP",
                "run_id": run_id,
                "step": "ceo_primary",
                "status": "blocked",
            }
        )
        return {
            "final": text,
            "errors": state.get("errors", []) + ["ceo_unreachable"],
        }

    # ── Build prompt ──
    prompt = build_ceo_prompt(state, mandamentos)
    system = ceo_system_prompt()
    assistant_prefix = _ceo_assistant_prefix(state)

    # ── Generate ──
    writer(
        {
            "type": "PIPELINE_STEP",
            "run_id": run_id,
            "step": "ceo_primary",
            "status": "started",
            "provider": ceo_provider,
            "local_ready": local_ready,
        }
    )

    raw_text = ""
    t0 = time.time()
    ceo_timeout = float(os.getenv("SUPEREZIO_CEO_TIMEOUT", "180"))

    try:
        async with asyncio.timeout(ceo_timeout):
            raw_text = await gateway.chat_completion(
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": prompt},
                ],
                temperature=float(os.getenv("SUPEREZIO_CEO_TEMPERATURE", "0.4")),
                max_tokens=int(os.getenv("SUPEREZIO_CEO_MAX_TOKENS", "8192")),
                preferred_provider=ceo_provider,
                assistant_prefix=assistant_prefix,
            )
    except Exception as exc:
        writer(
            {
                "type": "ERROR",
                "run_id": run_id,
                "detail": f"CEO generation failed: {exc}",
            }
        )
        degraded = (
            "CEO runtime is temporarily degraded and could not produce a full "
            "local verdict for this request. Please retry with a shorter scope."
        )
        writer({"type": "CHUNK", "content": degraded})
        writer(
            {
                "type": "PIPELINE_STEP",
                "run_id": run_id,
                "step": "ceo_primary",
                "status": "error",
            }
        )
        return {
            "final": degraded,
            "errors": state.get("errors", []) + [f"ceo:{exc}"],
        }

    elapsed = time.time() - t0
    final = sanitize_output(_strip_thinking(raw_text).strip())
    final = enforce_advisor_boundary(final, state)

    # Module coverage audit — if the quantized model skipped modules,
    # deterministically append a module-by-module summary so the user
    # always sees the full pipeline evidence.
    required, missing = _evaluate_module_coverage(final, state)
    if missing:
        writer(
            {
                "type": "MODULE_COVERAGE",
                "required": required,
                "covered": [m for m in required if m not in missing],
                "missing": missing,
                "warning": f"CEO output missing {len(missing)}/{len(required)} modules: {missing}",
            }
        )
        appendix = _build_module_appendix(state, missing)
        if appendix:
            final = final + "\n\n" + appendix

    writer({"type": "CHUNK", "content": final})
    writer(
        {
            "type": "PIPELINE_STEP",
            "run_id": run_id,
            "step": "ceo_primary",
            "status": "completed",
            "provider": ceo_provider,
            "elapsed_ms": int(elapsed * 1000),
        }
    )

    return {"final": final}


def _build_module_appendix(state: dict, missing: list[str]) -> str:
    """Deterministic module-by-module summary for modules the CEO skipped.

    Ensures the user always sees the full pipeline evidence, even when
    the quantized model truncates its response.
    """
    lines: list[str] = []
    line = lines.append

    # DATA
    if "price" in missing:
        data = state.get("data") or {}
        ticker = state.get("ticker") or data.get("ticker", "")
        price = data.get("price", {})
        price_val = price.get("price") if isinstance(price, dict) else None
        if price_val:
            line(
                f"## DATA\nPrice for {ticker}: ${price_val} (source: {price.get('provider', 'market')})."
            )
        else:
            scan = state.get("scan") or {}
            candidates = scan.get("candidates", [])
            if candidates:
                top = candidates[0]
                line(
                    f"## DATA\nMarket scan returned {len(candidates)} candidates. "
                    f"Top: {top.get('ticker', '?')} at ${top.get('price', 'N/A')}."
                )
            else:
                line("## DATA\nNo ticker-specific data collected.")

    # F51
    if "f51" in missing:
        f51 = state.get("f51_verdict") or {}
        if f51:
            line(
                f"## F51_VERDICT\nPassed: {f51.get('passed')}. "
                f"Confidence: {f51.get('confidence', 'N/A')}. "
                f"Hub risk score: {f51.get('hub_risk_score', 'N/A')}."
            )
        else:
            line("## F51_VERDICT\nNot run (no ticker data).")

    # MACRO
    if "macro" in missing:
        data = state.get("data") or {}
        macro = data.get("macro", {})
        if isinstance(macro, dict) and macro.get("treasury"):
            treas = macro["treasury"]
            line(
                f"## MACRO\nTreasury rates: Fed={treas.get('fed_funds', 'N/A')}%, "
                f"10Y={treas.get('10y', 'N/A')}%, 30Y={treas.get('30y', 'N/A')}%."
            )
        else:
            line("## MACRO\nMacro data not available for this scan.")

    # SENTIMENT
    if "sentiment" in missing:
        data = state.get("data") or {}
        sentiment = data.get("sentiment", {})
        if isinstance(sentiment, dict):
            label = sentiment.get("sentiment_label") or sentiment.get("label") or "neutral"
            line(f"## SENTIMENT\nNews sentiment: {label}.")
        else:
            line("## SENTIMENT\nSentiment data not available.")

    # SDCA
    if "sdca_firewall" in missing:
        sdca = state.get("sdca_firewall") or {}
        if sdca:
            line(
                f"## SDCA_FIREWALL\nDecision: {sdca.get('decision')}. "
                f"Confidence: {sdca.get('confidence')}. "
                f"Ghost tokens: {sdca.get('ghost_tokens', [])}."
            )
        else:
            line("## SDCA_FIREWALL\nFirewall not run.")

    # RAG
    if "rag_forensics" in missing:
        rag = state.get("rag_context") or ""
        matches = len(re.findall(r"\[CASE:", rag)) if rag else 0
        if matches:
            line(f"## RAG_FORENSICS\n{matches} historical fraud/risk patterns matched.")
        else:
            line("## RAG_FORENSICS\nNo historical patterns matched.")

    # EXPERTS
    if "experts" in missing:
        summary = state.get("expert_summary", "")
        if summary:
            line(f"## EXPERTS\n{summary[:600]}")
        else:
            line("## EXPERTS\nExpert committee not run.")

    # NEURAL
    if "neural" in missing:
        neural = state.get("neural_decision") or {}
        if neural and "error" not in neural:
            direction = neural.get("direction_prob", {})
            line(
                f"## NEURAL_DECISION\n"
                f"Direction: up={direction.get('up', '?')} down={direction.get('down', '?')} "
                f"sideways={direction.get('sideways', '?')}. "
                f"Regime: {neural.get('regime', '?')}. "
                f"Expected return: {neural.get('expected_return', '?')}. "
                f"Drawdown risk: {neural.get('drawdown_risk', '?')}."
            )
        else:
            line("## NEURAL_DECISION\nNot available for this request.")

    # TECHNICALS
    if "technical" in missing:
        data = state.get("data") or {}
        technicals = data.get("technicals", {})
        if isinstance(technicals, dict) and technicals:
            line(
                f"## TECHNICALS\nRSI: {technicals.get('rsi_14', 'N/A')}, "
                f"MACD: {technicals.get('macd', 'N/A')}, "
                f"EMA20: {technicals.get('ema_20', 'N/A')}."
            )
        else:
            line("## TECHNICALS\nTechnical data not available.")

    # PROFILE
    if "profile" in missing:
        data = state.get("data") or {}
        profile = data.get("profile", {})
        if isinstance(profile, dict) and profile:
            line(
                f"## PROFILE\nSector: {profile.get('sector', 'N/A')}, "
                f"Market cap: {profile.get('market_cap', 'N/A')}, "
                f"Industry: {profile.get('industry', 'N/A')}."
            )
        else:
            line("## PROFILE\nCompany profile not available.")

    # QUANT
    if "quant" in missing:
        data = state.get("data") or {}
        quant = data.get("quant", {})
        if isinstance(quant, dict) and quant:
            line(f"## QUANT\nQuant data available: {list(quant.keys())[:5]}.")
        else:
            line("## QUANT\nQuantitative models not run.")

    # RISK
    if "risk" in missing:
        data = state.get("data") or {}
        risk = data.get("risk", {})
        if isinstance(risk, dict) and risk:
            line(
                f"## RISK\nVaR: {risk.get('var', 'N/A')}, "
                f"CVaR: {risk.get('cvar', 'N/A')}, "
                f"Volatility: {risk.get('volatility', 'N/A')}."
            )
        else:
            line("## RISK\nRisk metrics not available.")

    # REDDIT
    if "reddit" in missing:
        data = state.get("data") or {}
        reddit = data.get("reddit", {})
        if isinstance(reddit, dict) and reddit:
            mentions = reddit.get("mentions", 0)
            sentiment = reddit.get("sentiment", "neutral")
            line(f"## REDDIT\nSocial mentions: {mentions}, sentiment: {sentiment}.")
        else:
            line("## REDDIT\nSocial data not available.")

    # PENNYLAB
    if "pennylab" in missing:
        penny = state.get("pennylab") or state.get("pennylab_result") or {}
        if penny and penny.get("decision"):
            line(f"## PENNYLAB\nDecision: {penny.get('decision')}.")
        else:
            line("## PENNYLAB\nNot run (no ticker or no forensic signal).")

    if not lines:
        return ""
    return "\n\n".join(lines)


async def _check_health(base_url: str) -> bool:
    """Check if the CEO server is responding."""
    import aiohttp

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"{base_url.rstrip('/')}/models", timeout=aiohttp.ClientTimeout(total=3)
            ) as resp:
                return resp.status == 200
    except Exception:
        return False
