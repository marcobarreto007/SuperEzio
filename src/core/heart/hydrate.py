"""Hydrate in-memory HeartView from on-disk heart + OHLCV artifacts."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from core.heart.attribution import session_impact_date
from core.heart.event_book import EventBook, MarketEvent
from core.heart.moves import daily_moves_from_bars
from core.heart.universe import ListingRow

_MAX_CSV_WITHOUT_EVENTS = 20
_US_MICS = frozenset({"XNAS", "XNYS", "ARCX", "XASE", "BATS", "XNMS", "XNCM"})
_CA_MICS = frozenset({"XTSX", "XTSV", "XTSE", "NEOE"})


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
) -> ListingRow:
    if listing_guess is not None:
        return listing_guess(csv_path.name)
    symbol = csv_path.stem.upper()
    return ListingRow(
        mic_code="XNAS",
        symbol=symbol,
        name=symbol,
        exchange="Q",
        source="hydrate",
    )


def _mic_compatible(listing_mic: str, event_mic: str | None) -> bool:
    listing = (listing_mic or "").upper()
    event = (event_mic or "").upper() or None
    if event:
        return listing == event
    if listing in _CA_MICS:
        return False
    return listing in _US_MICS or not listing


def _impact_dates_for_listing(listing: ListingRow, events: list[MarketEvent]) -> set[str]:
    dates: set[str] = set()
    symbol = listing.symbol.upper()
    for event in events:
        if not event.symbol or event.symbol.upper() != symbol:
            continue
        if not _mic_compatible(listing.mic_code, event.mic_code):
            continue
        dates.add(session_impact_date(event.occurred_at).isoformat())
    return dates


def _has_symbol_events(events: list[MarketEvent]) -> bool:
    return any(event.symbol for event in events)


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

    moves: list[Any] = []

    if _has_symbol_events(events):
        for csv_path in csv_paths:
            listing = _listing_for_csv(csv_path, listing_guess=listing_guess)
            dates = _impact_dates_for_listing(listing, events)
            if not dates:
                continue
            bars = _safe_bars(bars_from_yahoo_csv, csv_path)
            if not bars:
                continue
            first_seen = _first_seen_from_bars(bars)
            for move in daily_moves_from_bars(bars=bars, listing=listing, first_seen=first_seen):
                if str(move["session_date"]) in dates:
                    moves.append(move)
        return moves

    for csv_path in csv_paths[:_MAX_CSV_WITHOUT_EVENTS]:
        listing = _listing_for_csv(csv_path, listing_guess=listing_guess)
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


def _csv_candidates_for_event(event: MarketEvent) -> list[str]:
    symbol = (event.symbol or "").upper()
    names = [f"{symbol}.csv", f"{symbol.replace('.', '-')}.csv"]
    if (event.mic_code or "").upper() in _CA_MICS:
        names.insert(0, f"{symbol}.TO.csv")
    return names


def _bars_for_first_luld(
    events: list[MarketEvent],
    *,
    ohlcv_dir: Path,
    bars_from_yahoo_csv: Callable[[Path], list[dict[str, Any]]],
    listing_guess: Callable[[str], ListingRow] | None = None,
) -> list[dict[str, Any]]:
    for event in events:
        if event.event_type != "nyse.luld_pause" or not event.symbol:
            continue
        for name in _csv_candidates_for_event(event):
            csv_path = ohlcv_dir / name
            if not csv_path.exists():
                continue
            if listing_guess is not None:
                listing = listing_guess(csv_path.name)
                if not _mic_compatible(listing.mic_code, event.mic_code):
                    continue
            bars = _safe_bars(bars_from_yahoo_csv, csv_path)
            if bars:
                return list(bars)
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

    guess = _resolve_listing_guess()
    view.moves = _load_moves_from_ohlcv(
        ohlcv_dir=ohlcv_path,
        bars_from_yahoo_csv=bars_loader,
        listing_guess=guess,
        events=list(view.events),
        last_session_moves=_resolve_last_session_moves(),
    )
    view.bars = _bars_for_first_luld(
        list(view.events),
        ohlcv_dir=ohlcv_path,
        bars_from_yahoo_csv=bars_loader,
        listing_guess=guess,
    )
