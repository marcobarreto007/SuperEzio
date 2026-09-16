"""Reconcile Yahoo split events against as-traded prices.

The archive price always wins: an event without a jump is not applied twice.
A jump without an event is investigated, not silently rewritten.
"""

from __future__ import annotations

from dataclasses import dataclass

FLAT_TOLERANCE = 0.05
RATIO_TOLERANCE = 0.15


@dataclass(frozen=True, slots=True)
class SplitEvent:
    numerator: float
    denominator: float

    @classmethod
    def from_yahoo_ratio(cls, ratio: str) -> SplitEvent:
        left, right = ratio.split(":", 1)
        return cls(numerator=float(left), denominator=float(right))

    @property
    def price_factor(self) -> float:
        if self.numerator == 0:
            raise ValueError("split numerator cannot be zero")
        return self.denominator / self.numerator


@dataclass(frozen=True, slots=True)
class SplitDecision:
    kind: str
    apply_to_archive: bool


def classify_split_day(
    prev_close: float,
    close: float,
    event: SplitEvent | None,
) -> SplitDecision:
    if prev_close <= 0 or close <= 0:
        raise ValueError("prices must be positive")
    observed = close / prev_close
    if event is None:
        if abs(observed - 1.0) >= FLAT_TOLERANCE:
            return SplitDecision(kind="unexplained_move", apply_to_archive=False)
        return SplitDecision(kind="normal_day", apply_to_archive=False)

    expected = event.price_factor
    if abs(observed - 1.0) < FLAT_TOLERANCE:
        return SplitDecision(kind="already_adjusted", apply_to_archive=False)
    if abs(observed - expected) <= RATIO_TOLERANCE * abs(expected):
        return SplitDecision(kind="confirmed_split", apply_to_archive=True)
    return SplitDecision(kind="unexplained_move", apply_to_archive=False)


def freeze_on_yahoo_missing(status: int) -> bool:
    return status == 404
