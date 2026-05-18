"""CEO node — Qwen3.6-35B local analysis via llama.cpp."""

from __future__ import annotations

import asyncio
import os
import time
from langgraph.config import get_stream_writer

from ..prompts.builder import (
    _ceo_assistant_prefix,
    build_ceo_prompt,
    ceo_system_prompt,
    missing_ceo_text,
)
from ..security import sanitize_output

CEO_PROVIDER_NAME = "ceo"


def capabilities_text() -> str:
    """Deterministic answer for natural-language capability/tool questions."""
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
        "- CEO/Qwen: converts the evidence into a final BUY, SELL, or HOLD style verdict.\n\n"
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

    if state.get("intent") == "explain_capabilities":
        text = capabilities_text()
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
