"""Deterministic spine PathDecision. No LightGBM, no river, no paid APIs."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from core.heart.labels import (
    barrier_widths,
    label_with_existing_barrier,
    vertical_bars_for_sessions,
)
from core.heart.paths import PathDecision, PathSpec

SPINE_LABEL_SIGMA = 0.05


def _effective_sigma(sigma: float | None) -> float:
    if sigma is not None and sigma > 0:
        return sigma
    return SPINE_LABEL_SIGMA


def decide_path(
    bars: Sequence[Mapping[str, Any]],
    *,
    entry_index: int,
    spec: PathSpec,
    side: str = "long",
    sigma: float | None = None,
) -> PathDecision:
    entry_close = float(bars[entry_index]["close"])
    stop_w, profit_w = barrier_widths(_effective_sigma(sigma), 1.0, 1.0)
    stop = entry_close * (1 - stop_w)
    target = entry_close * (1 + profit_w)
    touch = label_with_existing_barrier(
        bars,
        side=side,
        stop_loss_price=stop,
        take_profit_price=target,
        time_horizon_bars=vertical_bars_for_sessions(1),
        start_index=entry_index,
    )
    if touch is not None and touch.is_profit:
        return PathDecision(path_id=spec.path_id, status="kept", weight=1.0)
    return PathDecision(path_id=spec.path_id, status="killed", weight=0.0)


def decide_from_bars_tail(
    bars: Sequence[Mapping[str, Any]],
    spec: PathSpec,
    *,
    side: str = "long",
    sigma: float | None = None,
) -> PathDecision:
    """Production entry: penultimate bar when len>=2, else bar 0."""
    entry_index = len(bars) - 2 if len(bars) >= 2 else 0
    return decide_path(
        bars,
        entry_index=entry_index,
        spec=spec,
        side=side,
        sigma=sigma,
    )
