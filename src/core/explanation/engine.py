"""
f51 Explanation Engine — translates deterministic motor verdicts into
plain language without hallucinating.

Uses Qwen2.5-1.5B-Instruct (or base + LoRA) locally in 4-bit.
Lazy-loaded so it does not slow down pipeline boot.

Usage:
    from core.explanation import ExplainEngine
    explainer = ExplainEngine()
    async for chunk in explainer.stream(f51_result, agent_text="..."):
        yield chunk
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, AsyncGenerator

import torch

_transformers = None
_model = None
_tokenizer = None
_model_path: str = os.getenv(
    "SUPEREZIO_NURSE_MODEL",
    "Qwen/Qwen2.5-1.5B-Instruct",
)
_lora_path: str | None = os.getenv(
    "SUPEREZIO_NURSE_LORA_PATH",
    "models/nurse-qwen2.5-1.5b-lora",
)
_device: str = "cuda:0" if torch.cuda.is_available() else "cpu"


def _resolve_lora_path(path: str | None) -> str | None:
    if not path:
        return None
    candidate = Path(path).expanduser()
    if not candidate.is_absolute():
        candidate = Path.cwd() / candidate
    if candidate.is_dir() and (candidate / "adapter_config.json").exists():
        return str(candidate)
    return None


def _get_transformers():
    global _transformers
    if _transformers is None:
        import transformers as _t

        _transformers = _t
    return _transformers


def _load_model():
    global _model, _tokenizer
    if _model is not None:
        return _model, _tokenizer

    _get_transformers()
    from transformers import AutoModelForCausalLM, AutoTokenizer

    tokenizer = AutoTokenizer.from_pretrained(_model_path, trust_remote_code=True)
    tokenizer.padding_side = "left"
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    model = AutoModelForCausalLM.from_pretrained(
        _model_path,
        device_map={"": _device},
        trust_remote_code=True,
        torch_dtype=torch.bfloat16,
    )

    resolved_lora_path = _resolve_lora_path(_lora_path)
    if resolved_lora_path:
        from peft import PeftModel

        model = PeftModel.from_pretrained(model, resolved_lora_path)

    model.eval()
    _model = model
    _tokenizer = tokenizer
    return model, tokenizer


_SYSTEM_PROMPT = (
    "You are a financial triage nurse. Your job is to explain a deterministic "
    "analysis engine's verdict to a normal human investor.\n\n"
    "RULES:\n"
    "1. NEVER give buy/sell advice.\n"
    "2. Use the engine's numbers exactly — do not make up numbers.\n"
    "3. Be calm, direct, and concise (3-5 sentences).\n"
    "4. If confidence is low, say WHY (missing data, high risk, etc).\n"
    "5. If danger flags exist, mention them clearly but without panic.\n"
    "6. Use simple language. No jargon unless you explain it.\n"
)


def _env_enabled(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _format_percent(value: Any) -> str:
    try:
        return f"{float(value) * 100:.1f}%"
    except (TypeError, ValueError):
        return "unknown"


def _format_score(value: Any) -> str:
    try:
        return f"{float(value):.2f}"
    except (TypeError, ValueError):
        return "unknown"


def _deterministic_explanation(f51_result: dict[str, Any], agent_text: str = "") -> str:
    """Explain F51 gate output without asking a generative model for new text."""
    confidence = f51_result.get("confidence")
    passed = bool(f51_result.get("passed", False))
    factors = f51_result.get("factors", {}) or {}
    hub_risk = f51_result.get("hub_risk", {}) or {}
    triggered = hub_risk.get("triggered_rules", []) or []
    risk_score = hub_risk.get("risk_score")

    status = "cleared" if passed else "did not clear"
    sentences = [
        f"F51 gate {status} with confidence {_format_percent(confidence)}.",
        f"Hub risk score is {_format_score(risk_score)}.",
    ]

    factor_notes = []
    for name in ("danger", "uncertainty", "novelty", "contradiction"):
        if name in factors:
            factor_notes.append(f"{name}={_format_score(factors.get(name))}")
    if factor_notes:
        sentences.append("Gate factors: " + ", ".join(factor_notes) + ".")

    if triggered:
        sentences.append("Triggered rules: " + ", ".join(str(item) for item in triggered) + ".")
    else:
        sentences.append("No F51 triggered rule was reported.")

    if agent_text:
        sentences.append(
            "The Decision Room brief above remains the controlling answer; "
            "this note adds no new financial claims."
        )

    return " ".join(sentences)


def _format_prompt(f51_result: dict[str, Any], agent_text: str = "") -> str:
    """Builds the structured prompt from motor output."""
    passed = f51_result.get("passed", False)
    factors = f51_result.get("factors", {})
    hub_risk = f51_result.get("hub_risk", {})

    triggered = hub_risk.get("triggered_rules", [])
    risk_score = hub_risk.get("risk_score", 0)

    parts = []
    if passed:
        parts.append("confidence is above threshold")
    else:
        parts.append("confidence is low")

    if factors.get("danger", 0) > 0.5:
        parts.append("danger is high")
    else:
        parts.append("danger is low")

    if factors.get("uncertainty", 0) > 0.3:
        parts.append("uncertainty is high")

    if triggered:
        parts.append(f"fraud rules triggered: {', '.join(triggered)}")
        parts.append(f"hub risk score: {risk_score:.2f}")

    factors_desc = ", ".join(parts) if parts else "factors mixed"
    lines = [f"Engine factors: {factors_desc}. Explain to the user."]

    if agent_text:
        lines.append(f"Agent summary: {agent_text[:400]}")

    return " ".join(lines)


class ExplainEngine:
    """Local 1.5B LLM that explains f51 verdicts."""

    def __init__(self, model_path: str | None = None, lora_path: str | None = None):
        global _model_path, _lora_path
        if model_path:
            _model_path = model_path
        if lora_path:
            _lora_path = lora_path
        self._loaded = False

    def _ensure_loaded(self):
        if not self._loaded:
            _load_model()
            self._loaded = True

    def explain(self, f51_result: dict[str, Any], agent_text: str = "") -> str:
        """Synchronous single-shot explanation."""
        if not _env_enabled("SUPEREZIO_EXPLANATION_USE_LLM", False):
            return _deterministic_explanation(f51_result, agent_text=agent_text)

        self._ensure_loaded()
        model, tokenizer = _model, _tokenizer
        if model is None or tokenizer is None:
            return "[Nurse model not loaded]"

        prompt = _format_prompt(f51_result, agent_text)
        messages = [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ]
        text = tokenizer.apply_chat_template(
            messages,
            tokenize=False,
            add_generation_prompt=True,
        )
        inputs = tokenizer(text, return_tensors="pt").to(_device)
        input_len = inputs["input_ids"].shape[1]

        with torch.no_grad():
            outputs = model.generate(
                **inputs,
                max_new_tokens=256,
                do_sample=False,
                pad_token_id=tokenizer.pad_token_id,
            )
        return tokenizer.decode(outputs[0][input_len:], skip_special_tokens=True).strip()

    async def stream(
        self, f51_result: dict[str, Any], agent_text: str = ""
    ) -> AsyncGenerator[str, None]:
        """Streaming explanation, yielding word-by-word or sentence chunks."""
        import asyncio

        if not _env_enabled("SUPEREZIO_EXPLANATION_USE_LLM", False):
            text = _deterministic_explanation(f51_result, agent_text=agent_text)
            for sentence in text.split(". "):
                if not sentence:
                    continue
                yield sentence if sentence.endswith(".") else f"{sentence}."
                await asyncio.sleep(0)
            return

        self._ensure_loaded()
        model, tokenizer = _model, _tokenizer
        if model is None or tokenizer is None:
            yield "[Nurse model not loaded]"
            return

        prompt = _format_prompt(f51_result, agent_text)
        messages = [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ]
        text = tokenizer.apply_chat_template(
            messages,
            tokenize=False,
            add_generation_prompt=True,
        )
        inputs = tokenizer(text, return_tensors="pt").to(_device)

        max_tokens = 256
        buffer = ""
        word_break = set(" \n")

        with torch.no_grad():
            past_key_values = None
            current_ids = inputs["input_ids"]

            for _ in range(max_tokens):
                outputs = model(
                    input_ids=current_ids,
                    past_key_values=past_key_values,
                    use_cache=True,
                )
                past_key_values = outputs.past_key_values
                next_token_logits = outputs.logits[:, -1, :]
                next_token_id = torch.argmax(next_token_logits, dim=-1).unsqueeze(0)

                token_text = tokenizer.decode(next_token_id[0], skip_special_tokens=True)
                buffer += token_text

                if any(c in word_break for c in token_text):
                    yield buffer
                    buffer = ""

                if next_token_id[0, 0].item() == tokenizer.eos_token_id:
                    break
                current_ids = next_token_id
                await asyncio.sleep(0)

        if buffer:
            yield buffer
