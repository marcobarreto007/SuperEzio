"""Heart labels reuse the production triple-barrier evaluator. Do not fork it."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from core.trading.triple_barrier import BarrierTouch, evaluate_triple_barrier


def label_with_existing_barrier(
    bars: Sequence[Mapping[str, Any]],
    *,
    side: object = "long",
    stop_loss_price: float,
    take_profit_price: float,
    time_horizon_bars: int,
    start_index: int = 0,
) -> BarrierTouch | None:
    return evaluate_triple_barrier(
        bars,
        side=side,
        stop_loss_price=stop_loss_price,
        take_profit_price=take_profit_price,
        time_horizon_bars=time_horizon_bars,
        start_index=start_index,
    )


def barrier_widths(
    ewma_or_garch_sigma: float,
    stop_mult: float,
    profit_mult: float,
) -> tuple[float, float]:
    """Scale horizontal barriers from conditional volatility (GARCH/EWMA)."""
    if ewma_or_garch_sigma < 0:
        raise ValueError("sigma must be non-negative")
    stop = ewma_or_garch_sigma * stop_mult
    target = ewma_or_garch_sigma * profit_mult
    return stop, target


def vertical_bars_for_sessions(n_sessions: int) -> int:
    """Session-aligned vertical barrier count (identity for daily session bars)."""
    if n_sessions < 1:
        raise ValueError("n_sessions must be at least 1")
    return n_sessions
