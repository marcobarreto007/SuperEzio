"""CEO node — model-agnostic final analysis generation."""

from __future__ import annotations

import asyncio
import os
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


async def _regenerate_with_coverage_pain(
    *,
    provider_name: str,
    state: dict,
    previous_output: str,
    missing_modules: list[str],
    gateway,
    mandamentos: list,
) -> str:
    """Force CEO to regenerate when it omitted required module sections."""
    correction = (
        "REINFORCEMENT PENALTY: previous CEO output failed mandatory module coverage.\n"
        f"Missing modules: {', '.join(missing_modules)}\n"
        "Regenerate from scratch with explicit section headers for ALL available modules.\n"
        "Do not omit any available module.\n\n"
        "[PREVIOUS_INVALID_OUTPUT]\n"
        f"{previous_output[:6000]}\n\n"
        "[ORIGINAL_PROMPT]\n"
        f"{build_ceo_prompt(state, mandamentos, model_family='deepseek')[:22000]}"
    )

    return await gateway.chat_completion(
        messages=[
            {
                "role": "system",
                "content": ceo_system_prompt(model_family="deepseek"),
            },
            {"role": "user", "content": correction},
        ],
        temperature=float(os.getenv("SUPEREZIO_CEO_TEMPERATURE", "0.2")),
        max_tokens=int(os.getenv("SUPEREZIO_CEO_MAX_TOKENS", "4096")),
        preferred_provider=provider_name,
    )


async def node_ceo(
    state: dict,
    *,
    gateway=None,
    config=None,
    mandamentos: list | None = None,
) -> dict:
    """Generate the CEO analysis using the configured model provider.

    Uses local Gemma-4-26B (Q4_K_M via llama-cpp) as primary.
    Falls back to cloud DeepSeek if local is unavailable.
    """
    writer = get_stream_writer()
    run_id = state.get("run_id", "")
    mandamentos = mandamentos or []

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

    # ── Select provider ──
    ceo_provider = None
    local_ready = False
    cloud_ready = False

    if gateway is not None:
        for p in gateway.providers:
            if p.name == CEO_PROVIDER_NAME:
                ceo_provider = CEO_PROVIDER_NAME
                try:
                    local_ready = await _check_health(p.base_url)
                except Exception:
                    pass
                break

    if not ceo_provider:
        cloud_ready = gateway is not None
        if cloud_ready:
            from ...model_serving.providers import PRIMARY_PROVIDER_NAME

            ceo_provider = PRIMARY_PROVIDER_NAME

    if not gateway or not ceo_provider:
        text = missing_ceo_text(
            ticker=state.get("ticker", ""),
            route=state.get("route", "general"),
            local_ready=local_ready,
            cloud_ready=cloud_ready,
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
    use_local = ceo_provider == CEO_PROVIDER_NAME
    model_family = "gemma" if use_local else "deepseek"

    prompt = build_ceo_prompt(state, mandamentos, model_family=model_family)
    system = ceo_system_prompt(model_family=model_family)
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
            "cloud_ready": cloud_ready,
        }
    )

    raw_text = ""
    t0 = time.time()
    ceo_timeout = float(
        os.getenv("SUPEREZIO_CEO_TIMEOUT", "180" if use_local else "120")
    )

    try:
        async with asyncio.timeout(ceo_timeout):
            raw_text = await gateway.chat_completion(
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": prompt},
                ],
                temperature=float(
                    os.getenv(
                        "SUPEREZIO_CEO_TEMPERATURE", "0.4" if use_local else "0.2"
                    )
                ),
                max_tokens=int(
                    os.getenv(
                        "SUPEREZIO_CEO_MAX_TOKENS", "8192" if use_local else "4096"
                    )
                ),
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

    # ── Module coverage check ──
    required, missing = _evaluate_module_coverage(final, state)
    if required and missing and not use_local:
        writer(
            {
                "type": "CEO_MODULE_PENALTY",
                "required_modules": required,
                "missing_modules": missing,
                "pain_score": len(missing),
                "provider": ceo_provider,
            }
        )
        try:
            corrected = await _regenerate_with_coverage_pain(
                provider_name=ceo_provider,
                state=state,
                previous_output=final,
                missing_modules=missing,
                gateway=gateway,
                mandamentos=mandamentos,
            )
            corrected = sanitize_output(_strip_thinking(corrected).strip())
            _, missing_after = _evaluate_module_coverage(corrected, state)
            if not missing_after and corrected:
                final = corrected
            elif missing_after:
                penalty = (
                    "[REINFORCEMENT_PAIN] CEO output penalized for missing modules: "
                    + ", ".join(missing_after)
                    + ".\n"
                )
                final = penalty + corrected
        except Exception:
            pass

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
