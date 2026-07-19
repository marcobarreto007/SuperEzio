"""Fail-closed compatibility boundary for the retired pseudo-RL policy.

The former implementation initialized a random network, synthesized a market
state and exposed BUY/SELL actions before observing a validated trajectory.  A
random policy is not learning.  Durable adaptation now happens in
``outcome_learning`` from immutable terminal trades and proper scoring rules.
"""

from __future__ import annotations

from typing import Any


class NeuralPolicy:
    """Compatibility object that can only abstain.

    The old public methods remain importable so stale callers fail safely rather
    than silently reactivating random order advice.
    """

    def __init__(self, lr: float = 0.01) -> None:
        self.lr = float(lr)
        self.episodes = 0
        self.total_reward = 0.0
        self.baseline = 0.0

    def choose_action(self, state: dict[str, Any]) -> tuple[str, float]:
        del state
        return "WAIT", 0.0

    def get_best_action(self, state: dict[str, Any]) -> tuple[str, float]:
        del state
        return "WAIT", 0.0

    def update(self, state: dict[str, Any], action: str, reward: float) -> None:
        del state, action, reward
        raise RuntimeError(
            "legacy neural_rl updates are retired; use OutcomeLearningEngine "
            "with durable terminal trades and ex-ante forecast provenance"
        )

    def save(self) -> None:
        """No-op: the retired random policy has no trustworthy state to persist."""

    def get_stats(self) -> dict[str, Any]:
        return {
            "status": "retired",
            "episodes": 0,
            "avg_reward": 0.0,
            "baseline": 0.0,
            "method": "none",
            "reason": "random_policy_had_no_validated_trajectory_schema",
            "replacement": "OutcomeLearningEngine.directional_brier_skill",
        }


_policy: NeuralPolicy | None = None


def get_neural_policy() -> NeuralPolicy:
    """Return the fail-closed compatibility singleton."""
    global _policy
    if _policy is None:
        _policy = NeuralPolicy()
    return _policy
