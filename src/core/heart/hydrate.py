"""Hydrate in-memory HeartView from on-disk heart + OHLCV artifacts."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from core.heart.event_book import EventBook, MarketEvent
from core.heart.moves import daily_moves_from_bars
from core.heart.universe import ListingRow

_MAX_CSV_WITHOUT_EVENTS = 20


def _resolve_bars_loader() -> Callable[[Path], list[dict[str, Any]]] | None:
    try:
        from core.heart.ohlcv_csv import bars_from_yahoo_csv
    except ImportError:
        return None
    return bars_from_yahoo_csv


def _resolve_listing_guess() -> Callable[[str], ListingRow] | None:
    try:
        from core.heart.ohlcv_csv import listing_guess_from_filename
    except ImportError:
        return None
    return listing_guess_from_filename


def _resolve_last_session_moves() -> Callable[..., list[Any]] | None:
    try:
        from core.heart.ohlcv_csv import last_session_moves
    except ImportError:
        return None
    return last_session_moves


def _safe_bars(
    bars_from_yahoo_csv: Callable[[Path], list[dict[str, Any]]],
    csv_path: Path,
) -> list[dict[str, Any]] | None:
    try:
        return bars_from_yahoo_csv(csv_path)
    except (OSError, ValueError, FileNotFoundError):
        return None


def _first_seen_from_bars(bars: list[dict[str, Any]]) -> str:
    if not bars:
        return "1970-01-01"
    ordered = sorted(bars, key=lambda bar: str(bar["session_date"]))
    return str(ordered[0]["session_date"])


def _listing_for_csv(
    csv_path: Path,
    *,
    listing_guess: Callable[[str], ListingRow] | None,
    events: list[MarketEvent],
) -> ListingRow:
    if listing_guess is not None:
        listing = listing_guess(csv_path.name)
    else:
        symbol = csv_path.stem.upper()
        listing = ListingRow(
            mic_code="XNAS",
            symbol=symbol,
            name=symbol,
            exchange="Q",
            source="hydrate",
        )
    mic = _mic_for_symbol(listing.symbol, events)
    if mic:
        listing = ListingRow(
            mic_code=mic,
            symbol=listing.symbol,
            name=listing.name,
            exchange=listing.exchange,
            source=listing.source,
        )
    return listing


def _event_symbols(events: list[MarketEvent]) -> set[str]:
    symbols: set[str] = set()
    for event in events:
        if event.symbol:
            symbols.add(event.symbol.upper())
    return symbols


def _mic_for_symbol(symbol: str, events: list[MarketEvent]) -> str | None:
    target = symbol.upper()
    for event in events:
        if event.symbol and event.symbol.upper() == target and event.mic_code:
            return event.mic_code
    return None


def _load_moves_from_ohlcv(
    *,
    ohlcv_dir: Path,
    bars_from_yahoo_csv: Callable[[Path], list[dict[str, Any]]],
    listing_guess: Callable[[str], ListingRow] | None,
    events: list[MarketEvent],
    last_session_moves: Callable[..., list[Any]] | None,
) -> list[Any]:
    csv_paths = sorted(ohlcv_dir.glob("*.csv"))
    if not csv_paths:
        return []

    event_symbols = _event_symbols(events)
    moves: list[Any] = []

    if event_symbols:
        for csv_path in csv_paths:
            listing = _listing_for_csv(csv_path, listing_guess=listing_guess, events=events)
            if listing.symbol.upper() not in event_symbols:
                continue
            bars = _safe_bars(bars_from_yahoo_csv, csv_path)
            if not bars:
                continue
            first_seen = _first_seen_from_bars(bars)
            moves.extend(
                daily_moves_from_bars(bars=bars, listing=listing, first_seen=first_seen)
            )
        return moves

    for csv_path in csv_paths[:_MAX_CSV_WITHOUT_EVENTS]:
        listing = _listing_for_csv(csv_path, listing_guess=listing_guess, events=events)
        if last_session_moves is not None:
            bars = _safe_bars(bars_from_yahoo_csv, csv_path)
            if not bars:
                continue
            first_seen = _first_seen_from_bars(bars)
            try:
                moves.extend(last_session_moves(csv_path, listing, first_seen))
            except (OSError, ValueError, FileNotFoundError):
                continue
            continue
        bars = _safe_bars(bars_from_yahoo_csv, csv_path)
        if not bars:
            continue
        first_seen = _first_seen_from_bars(bars)
        tail = daily_moves_from_bars(bars=bars, listing=listing, first_seen=first_seen)
        moves.extend(tail[-2:])
    return moves


def _bars_for_first_luld(
    events: list[MarketEvent],
    *,
    ohlcv_dir: Path,
    bars_from_yahoo_csv: Callable[[Path], list[dict[str, Any]]],
) -> list[dict[str, Any]]:
    for event in events:
        if event.event_type != "nyse.luld_pause" or not event.symbol:
            continue
        csv_path = ohlcv_dir / f"{event.symbol.upper()}.csv"
        if not csv_path.exists():
            alt = ohlcv_dir / f"{event.symbol.upper().replace('.', '-')}.csv"
            csv_path = alt if alt.exists() else csv_path
        if not csv_path.exists():
            return []
        bars = _safe_bars(bars_from_yahoo_csv, csv_path)
        return list(bars) if bars else []
    return []


def refresh_heart_view(
    view: Any,
    *,
    heart_root: Path,
    ohlcv_dir: Path | None,
) -> None:
    """Populate ``view`` from disk. Never invent OHLCV; leave empty on missing data."""
    view.moves = []
    view.events = []
    view.bars = []

    events_path = Path(heart_root) / "events.jsonl"
    if events_path.exists():
        view.events = EventBook(events_path).read_all()

    bars_loader = _resolve_bars_loader()
    if bars_loader is None or ohlcv_dir is None:
        return

    ohlcv_path = Path(ohlcv_dir)
    if not ohlcv_path.is_dir():
        return

    view.moves = _load_moves_from_ohlcv(
        ohlcv_dir=ohlcv_path,
        bars_from_yahoo_csv=bars_loader,
        listing_guess=_resolve_listing_guess(),
        events=list(view.events),
        last_session_moves=_resolve_last_session_moves(),
    )
    view.bars = _bars_for_first_luld(
        list(view.events),
        ohlcv_dir=ohlcv_path,
        bars_from_yahoo_csv=bars_loader,
    )
