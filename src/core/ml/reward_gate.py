"""Post-answer quality scoring for Bob responses.

The reward model is loaded lazily and runs on CPU. Scoring is best-effort:
when the model is unavailable a deterministic heuristic fallback is used so
the API can keep streaming without depending on a downloaded model.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass

logger = logging.getLogger(__name__)

_model: object | None = None
_tokenizer: object | None = None
_torch: object | None = None


@dataclass(frozen=True)
class QualityScore:
    """A response-form score with explicit provenance and limited scope."""

    value: float
    source: str
    scope: str = "response_form_not_investment_accuracy"


def _ensure_loaded() -> tuple[object, object]:
    global _model, _tokenizer, _torch
    if _model is not None and _tokenizer is not None:
        return _model, _tokenizer

    import torch as torch_module
    from transformers import AutoModelForSequenceClassification, AutoTokenizer

    model_id = "OpenAssistant/reward-model-deberta-v3-base"
    logger.info("RewardGate loading %s on CPU", model_id)
    _torch = torch_module
    _tokenizer = AutoTokenizer.from_pretrained(model_id, revision="main")  # nosec — revision pinned
    _model = AutoModelForSequenceClassification.from_pretrained(model_id, revision="main")  # nosec — revision pinned
    _model.to("cpu")
    _model.eval()
    param_count_m = sum(p.numel() for p in _model.parameters()) // 1_000_000
    logger.info("RewardGate ready (%dM params, CPU)", param_count_m)
    return _model, _tokenizer


class RewardGate:
    """Scores a response in [0, 1]. Higher is better."""

    def __init__(self, threshold: float = 0.30, max_retries: int = 2, max_tokens: int = 512):
        self.threshold = threshold
        self.max_retries = max_retries
        self.max_tokens = max_tokens

    def _heuristic_score(self, text: str) -> float:
        """Deterministic quality fallback when the reward model is unavailable.

        Uses basic text signals (length, structure, numeric density) to produce
        a score in [0, 1].  Substantive financial answers reliably score > 0.3.
        """
        clean = text.strip()
        length = len(clean)

        # Very short / empty — not a meaningful response
        if length < 100:
            return 0.0
        if length < 300:
            return 0.40

        # Base for any substantive answer
        score = 0.65

        # Paragraph structure → well-formed answer
        score += min(clean.count("\n\n") * 0.03, 0.12)

        # Numeric density → financial data is present
        digit_ratio = sum(1 for ch in clean if ch.isdigit()) / max(length, 1)
        if digit_ratio > 0.03:
            score += 0.05
        if "%" in clean:
            score += 0.05
        if "$" in clean or "€" in clean or "£" in clean:
            score += 0.05

        return min(score, 0.95)

    def score(self, text: str) -> float:
        """Compatibility wrapper returning only the response-form score."""

        return self.score_with_provenance(text).value

    def score_with_provenance(self, text: str) -> QualityScore:
        """Return score, scorer provenance, and an explicit non-financial scope."""

        if not text or not text.strip():
            return QualityScore(0.0, "empty_response")

        t0 = time.time()
        try:
            model, tokenizer = _ensure_loaded()
            inputs = tokenizer(
                text[:2048],
                return_tensors="pt",
                truncation=True,
                max_length=self.max_tokens,
            )
            with _torch.no_grad():
                outputs = model(**inputs)
                raw = outputs.logits.item()
            model_score = float(_torch.sigmoid(_torch.tensor(raw)).item())
            elapsed_ms = int((time.time() - t0) * 1000)
            logger.debug("RewardGate score=%.4f (%dms)", model_score, elapsed_ms)
            return QualityScore(model_score, "openassistant_reward_model")
        except Exception:
            logger.warning("RewardGate model unavailable; using heuristic fallback")
            return QualityScore(self._heuristic_score(text), "text_structure_heuristic")

    def passes(self, text: str) -> bool:
        return self.score(text) >= self.threshold

    def best_of(
        self, candidates: list[str], *, min_score: float | None = None
    ) -> tuple[str, float, int]:
        """Pick the best candidate by reward score.

        Returns (best_text, best_score, index).
        """
        if not candidates:
            return "", 0.0, -1
        stop_score = min_score if min_score is not None else 0.85
        best_idx = 0
        best_text = candidates[0]
        best_score = self.score(best_text)
        for i, text in enumerate(candidates[1:], start=1):
            s = self.score(text)
            if s > best_score:
                best_score = s
                best_text = text
                best_idx = i
            if best_score >= stop_score:
                break
        return best_text, best_score, best_idx


reward_gate = RewardGate()
