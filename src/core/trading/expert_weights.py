"""Expert weight router — dynamic performance-based weight adjustment."""

from __future__ import annotations

import math
import time
from dataclasses import dataclass


@dataclass
class ExpertRecord:
    name: str
    total_calls: int = 0
    correct_calls: int = 0
    total_confidence: float = 0.0
    last_called_at: float = 0.0
    weight: float = 1.0


class ExpertWeightRouter:
    """Tracks expert performance and adjusts routing weights.

    Experts that consistently produce accurate predictions get higher
    weights. Experts that underperform get decayed weights.

    Weight formula: base_weight * accuracy_multiplier * recency_multiplier
    """

    def __init__(
        self,
        min_weight: float = 0.1,
        max_weight: float = 3.0,
        decay_factor: float = 0.95,
        recency_window: float = 86400.0,
        initial_weight: float = 1.0,
    ):
        self.min_weight = min_weight
        self.max_weight = max_weight
        self.decay_factor = decay_factor
        self.recency_window = recency_window
        self.initial_weight = initial_weight
        self._experts: dict[str, ExpertRecord] = {}

    def record_call(
        self,
        expert_name: str,
        confidence: float,
        correct: bool | None = None,
    ) -> ExpertRecord:
        rec = self._experts.get(expert_name)
        if rec is None:
            rec = ExpertRecord(name=expert_name, weight=self.initial_weight)
            self._experts[expert_name] = rec

        rec.total_calls += 1
        rec.total_confidence += confidence
        rec.last_called_at = time.time()

        if correct is not None and correct:
            rec.correct_calls += 1

        self._update_weight(rec)
        return rec

    def get_weight(self, expert_name: str) -> float:
        rec = self._experts.get(expert_name)
        if rec is None:
            return self.initial_weight
        return rec.weight

    def get_all_weights(self) -> dict[str, float]:
        return {name: rec.weight for name, rec in self._experts.items()}

    def get_normalized_weights(self) -> dict[str, float]:
        weights = self.get_all_weights()
        total = sum(weights.values())
        if total == 0:
            return {k: 1.0 / len(weights) for k in weights} if weights else {}
        return {k: v / total for k, v in weights.items()}

    def get_record(self, expert_name: str) -> ExpertRecord | None:
        return self._experts.get(expert_name)

    def get_all_records(self) -> dict[str, ExpertRecord]:
        return dict(self._experts)

    def _update_weight(self, rec: ExpertRecord) -> None:
        accuracy_mult = 1.0
        if rec.total_calls > 0:
            accuracy = rec.correct_calls / rec.total_calls
            accuracy_mult = 0.5 + accuracy

        recency_mult = 1.0
        if rec.last_called_at > 0:
            elapsed = time.time() - rec.last_called_at
            recency_mult = math.exp(-elapsed / self.recency_window)

        rec.weight = max(
            self.min_weight,
            min(
                self.max_weight,
                self.initial_weight * accuracy_mult * recency_mult,
            ),
        )

    def decay_all(self) -> None:
        for rec in self._experts.values():
            rec.weight *= self.decay_factor
            rec.weight = max(self.min_weight, rec.weight)

    def reset(self, expert_name: str | None = None) -> None:
        if expert_name:
            self._experts.pop(expert_name, None)
        else:
            self._experts.clear()
