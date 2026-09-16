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


def decide_path(
    bars: Sequence[Mapping[str, Any]],
    *,
    entry_index: int,
    spec: PathSpec,
    side: str = "long",
) -> PathDecision:
    entry_close = float(bars[entry_index]["close"])
    stop_w, profit_w = barrier_widths(SPINE_LABEL_SIGMA, 1.0, 1.0)
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
