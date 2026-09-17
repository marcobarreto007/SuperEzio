"""Bridge effective_universe OHLCV CSV cache → DailyMove (P1 archive).

CSV files under ``data/reference/effective_universe/ohlcv/`` follow Yahoo
download naming (``Date,Open,High,Low,Close,Volume``). Canadian listings use
``.TO`` suffix; Yahoo replaces dots in class shares with dashes before ``.TO``
(e.g. listing ``BTCX.B`` → cache file ``BTCX-B.TO.csv``). ``listing_guess_from_filename``
reverses that mapping for MIC/symbol inference only — identity still requires
``first_seen`` from the universe registry.
"""

from __future__ import annotations

import csv
from pathlib import Path

from core.heart.attribution import DailyMove
from core.heart.moves import daily_moves_from_bars
from core.heart.universe import ListingRow

_REQUIRED_COLUMNS = frozenset({"date", "open", "high", "low", "close", "volume"})


def bars_from_yahoo_csv(path: str | Path) -> list[dict]:
    """Parse a Yahoo-style OHLCV CSV into bar dicts for ``daily_moves_from_bars``.

    Returns an empty list when the file exists but contains no data rows (header
    only). Raises ``FileNotFoundError`` when ``path`` is missing.
    """
    csv_path = Path(path)
    if not csv_path.is_file():
        raise FileNotFoundError(f"ohlcv csv not found: {csv_path}")

    bars: list[dict] = []
    with csv_path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames:
            return []
        columns = {name.strip().lower() for name in reader.fieldnames}
        missing = _REQUIRED_COLUMNS - columns
        if missing:
            raise ValueError(f"ohlcv csv missing columns: {sorted(missing)}")

        for row in reader:
            lowered = {key.strip().lower(): (value or "").strip() for key, value in row.items()}
            if not lowered.get("date"):
                continue
            session_date = lowered["date"][:10]
            bars.append(
                {
                    "session_date": session_date,
                    "open": float(lowered["open"]),
                    "high": float(lowered["high"]),
                    "low": float(lowered["low"]),
                    "close": float(lowered["close"]),
                    "volume": float(lowered["volume"]),
                }
            )
    return bars


def listing_guess_from_filename(name: str) -> ListingRow:
    """Infer MIC and listing symbol from an effective_universe CSV basename.

    Rules:
    - ``*.TO.csv`` → ``mic_code=XTSX``; stem before ``.TO`` is the Yahoo ticker.
    - Yahoo CAN mapping replaces ``.`` with ``-`` in the symbol (``BTCX.B`` →
      ``BTCX-B.TO``); we reverse the first ``-`` back to ``.`` for ``symbol``.
    - All other basenames → ``mic_code=XNAS``; symbol is the stem without ``.csv``.
    """
    stem = Path(name).name
    if stem.lower().endswith(".csv"):
        stem = stem[:-4]

    if stem.upper().endswith(".TO"):
        mic_code = "XTSX"
        yahoo_stem = stem[:-3]
        symbol = yahoo_stem.replace("-", ".", 1) if "-" in yahoo_stem else yahoo_stem
        exchange = "TO"
    else:
        mic_code = "XNAS"
        symbol = stem
        exchange = "Q"

    return ListingRow(
        mic_code=mic_code,
        symbol=symbol,
        name=symbol,
        exchange=exchange,
        source="effective_universe_csv",
    )


def last_session_moves(
    csv_path: str | Path,
    listing: ListingRow,
    first_seen: str,
    *,
    last_n_sessions: int = 2,
) -> list[DailyMove]:
    """Build ``DailyMove`` rows from a local OHLCV CSV, keeping only the tail."""
    if last_n_sessions < 1:
        raise ValueError("last_n_sessions must be >= 1")
    bars = bars_from_yahoo_csv(csv_path)
    moves = daily_moves_from_bars(bars=bars, listing=listing, first_seen=first_seen)
    return moves[-last_n_sessions:]
