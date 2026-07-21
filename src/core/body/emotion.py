"""Emotion — PAD (Pleasure-Arousal-Dominance) engine for the CORPO layer.

Maps numerical market conditions to an emotional state that modulates DNA
parameters.  Eight discrete states are derived from the three continuous
dimensions:

  P  Pleasure   (-1 .. +1)   how well the system is performing
  A  Arousal    ( 0 ..  1)   how volatile / exciting the environment is
  D  Dominance  (-1 .. +1)   how much control the system perceives

The combination produces a qualitative label used by downstream modules.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

# ── Emotional state labels ──────────────────────────────────────────────────
EMOTION_LABELS: dict[tuple[str, str, str], str] = {
    ("high", "high", "high"): "euphoria",
    ("high", "high", "low"): "anxiety",
    ("high", "low", "high"): "contentment",
    ("high", "low", "low"): "serenity",
    ("low", "high", "high"): "dominance",
    ("low", "high", "low"): "fear",
    ("low", "low", "high"): "boredom",
    ("low", "low", "low"): "apathy",
}


@dataclass(frozen=True)
class EmotionalState:
    """A snapshot of the system's emotional state."""

    label: str
    pleasure: float  # -1 .. +1
    arousal: float  # 0 .. 1
    dominance: float  # -1 .. +1


# ---------------------------------------------------------------------------
# PAD Engine
# ---------------------------------------------------------------------------


class PADEngine:
    """Pleasure-Arousal-Dominance affective model for the CORPO layer."""

    def __init__(
        self,
        pleasure: float = 0.0,
        arousal: float = 0.3,
        dominance: float = 0.0,
    ) -> None:
        self.pleasure = _clamp_p(pleasure)
        self.arousal = _clamp_a(arousal)
        self.dominance = _clamp_d(dominance)
        self._history: list[EmotionalState] = []

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def update(
        self,
        win_rate: float | None = None,
        volatility: float | None = None,
        capital_vs_initial: float | None = None,
    ) -> EmotionalState:
        """Update the emotional state from market/trading signals.

        Parameters
        ----------
        win_rate : float or None
            Recent win rate (0..1).  Drives pleasure.
        volatility : float or None
            Recent market volatility (0..1 normalised).  Drives arousal.
        capital_vs_initial : float or None
            Ratio of current capital to initial capital.  Drives dominance.
        """
        if win_rate is not None:
            # Map win_rate 0..1 -> pleasure -1..+1
            self.pleasure = _clamp_p((win_rate - 0.5) * 2.0)

        if volatility is not None:
            # Volatility directly maps to arousal
            self.arousal = _clamp_a(volatility)

        if capital_vs_initial is not None:
            # Ratio 1.0 -> dominance 0.0; above 1 -> positive; below -> negative
            self.dominance = _clamp_d(math.tanh(capital_vs_initial - 1.0) * 1.5)

        state = self._current_state()
        self._history.append(state)
        return state

    def modulate_dna(self, dna: dict[str, float]) -> dict[str, float]:
        """Adjust DNA parameters based on current emotional state.

        Returns a new dict with modulated values (does not mutate the input).
        """
        modulated = dict(dna)
        state = self._current_state()

        # Euphoria — tend toward risk-seeking
        if state.label == "euphoria":
            modulated["risk.kelly_multiplier"] = _modulate(
                dna.get("risk.kelly_multiplier", 0.25), +0.10, 0.05, 1.0
            )
            modulated["risk.conviction_threshold"] = _modulate(
                dna.get("risk.conviction_threshold", 70.0), -5.0, 30.0, 95.0
            )

        # Fear / anxiety — tend toward risk-averse
        elif state.label in ("fear", "anxiety"):
            modulated["risk.kelly_multiplier"] = _modulate(
                dna.get("risk.kelly_multiplier", 0.25), -0.08, 0.05, 1.0
            )
            modulated["risk.max_position_pct"] = _modulate(
                dna.get("risk.max_position_pct", 0.05), -0.01, 0.01, 0.25
            )
            modulated["mangala.high_conviction"] = _modulate(
                dna.get("mangala.high_conviction", 80.0), +5.0, 50.0, 100.0
            )

        # Apathy / boredom — increase scan frequency
        elif state.label in ("apathy", "boredom"):
            modulated["scan.frequency"] = _modulate(
                dna.get("scan.frequency", 60.0), -10.0, 15.0, 240.0
            )

        # Contentment / serenity — slight conservative bias
        elif state.label in ("contentment", "serenity"):
            modulated["trade.max_hold_days"] = _modulate(
                dna.get("trade.max_hold_days", 5.0), +1.0, 1.0, 30.0
            )

        # Dominance — increase conviction threshold (confidence is high)
        elif state.label == "dominance":
            modulated["mangala.high_conviction"] = _modulate(
                dna.get("mangala.high_conviction", 80.0), -3.0, 50.0, 100.0
            )

        return modulated

    def current_state(self) -> EmotionalState:
        """Return the current emotional state without modifying it."""
        return self._current_state()

    def history(self) -> list[EmotionalState]:
        """Return the full history of emotional states."""
        return list(self._history)

    def reset(self) -> None:
        """Reset the engine to neutral."""
        self.pleasure = 0.0
        self.arousal = 0.3
        self.dominance = 0.0
        self._history.clear()

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _current_state(self) -> EmotionalState:
        pleasure_cat = "high" if self.pleasure >= 0.0 else "low"
        arousal_cat = "high" if self.arousal >= 0.5 else "low"
        dominance_cat = "high" if self.dominance >= 0.0 else "low"
        label = EMOTION_LABELS.get((pleasure_cat, arousal_cat, dominance_cat), "neutral")
        return EmotionalState(
            label=label,
            pleasure=self.pleasure,
            arousal=self.arousal,
            dominance=self.dominance,
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _clamp_p(value: float) -> float:
    return max(-1.0, min(1.0, value))


def _clamp_a(value: float) -> float:
    return max(0.0, min(1.0, value))


def _clamp_d(value: float) -> float:
    return max(-1.0, min(1.0, value))


def _modulate(
    current: float,
    delta: float,
    lo: float,
    hi: float,
) -> float:
    return max(lo, min(hi, current + delta))


__all__ = [
    "EMOTION_LABELS",
    "EmotionalState",
    "PADEngine",
]
