"""As-traded daily bars → DailyMove. Missing axes stay 0.0 this cycle."""

from __future__ import annotations

from core.heart.attribution import DailyMove
from core.heart.universe import ListingRow
from core.math.risk import log_return


def daily_moves_from_bars(
    *,
    bars: list[dict],
    listing: ListingRow,
    first_seen: str,
) -> list[DailyMove]:
    ordered = sorted(bars, key=lambda bar: str(bar["session_date"]))
    moves: list[DailyMove] = []
    prev_close: float | None = None
    for bar in ordered:
        close = float(bar["close"])
        gross_ret = 0.0 if prev_close is None else log_return(close, prev_close)
        moves.append(
            {
                "mic_code": listing.mic_code,
                "symbol": listing.symbol,
                "first_seen": first_seen,
                "session_date": str(bar["session_date"]),
                "abnormal_ret": 0.0,
                "gross_ret": gross_ret,
                "surprise_q": 0.0,
                "ewma_vol": 0.0,
            }
        )
        prev_close = close
    return moves
