"""Post-answer quality scoring for Bob responses.

The reward model is loaded lazily and runs on CPU. Scoring is best-effort:
any model/cache/transformers error returns 0.0 so the API can keep streaming.
"""

from __future__ import annotations

import logging
import time

logger = logging.getLogger(__name__)

_model: object | None = None
_tokenizer: object | None = None
_torch: object | None = None


def _ensure_loaded() -> tuple[object, object]:
    global _model, _tokenizer, _torch
    if _model is not None and _tokenizer is not None:
        return _model, _tokenizer

    import torch as torch_module
    from transformers import AutoModelForSequenceClassification, AutoTokenizer

    model_id = "OpenAssistant/reward-model-deberta-v3-base"
    logger.info("RewardGate loading %s on CPU", model_id)
    _torch = torch_module
    _tokenizer = AutoTokenizer.from_pretrained(model_id)
    _model = AutoModelForSequenceClassification.from_pretrained(model_id)
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

    def score(self, text: str) -> float:
        """Return a quality score in [0, 1], or 0.0 if scoring is unavailable."""
        if not text or not text.strip():
            return 0.0

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
            score = float(_torch.sigmoid(_torch.tensor(raw)).item())
            elapsed_ms = int((time.time() - t0) * 1000)
            logger.debug("RewardGate score=%.4f (%dms)", score, elapsed_ms)
            return score
        except Exception:
            logger.exception("RewardGate scoring failed; returning 0.0")
            return 0.0

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
