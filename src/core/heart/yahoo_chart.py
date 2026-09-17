"""Fetch Yahoo daily chart and persist as-traded OHLCV for the Heart store.

Close is ``indicators.quote.close``, never ``adjclose``. Splits stay as a
price jump in the series — that is the archive, not a defect.

CLI (from repo root with ``src`` on PYTHONPATH)::

    python -m core.heart.yahoo_chart --from-events --limit 3
    python -m core.heart.yahoo_chart --symbol SPY
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

from core.heart.corporate_actions import freeze_on_yahoo_missing
from core.heart.event_book import EventBook
from core.heart.http import HeartHttpError
from core.heart.raw_recorder import DEFAULT_HEART_ROOT

CHART_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"


def bars_from_chart_payload(payload: dict[str, Any]) -> list[dict[str, Any]]:
    chart = payload.get("chart") or {}
    results = chart.get("result") or []
    if not results:
        return []
    result = results[0]
    timestamps = result.get("timestamp") or []
    quote = ((result.get("indicators") or {}).get("quote") or [{}])[0]
    opens = quote.get("open") or []
    highs = quote.get("high") or []
    lows = quote.get("low") or []
    closes = quote.get("close") or []
    volumes = quote.get("volume") or []
    bars: list[dict[str, Any]] = []
    for index, ts in enumerate(timestamps):
        close = _num_at(closes, index)
        if close is None:
            continue
        session = datetime.fromtimestamp(int(ts), tz=UTC).date().isoformat()
        bars.append(
            {
                "session_date": session,
                "open": _num_at(opens, index) if _num_at(opens, index) is not None else close,
                "high": _num_at(highs, index) if _num_at(highs, index) is not None else close,
                "low": _num_at(lows, index) if _num_at(lows, index) is not None else close,
                "close": close,
                "volume": _num_at(volumes, index) or 0.0,
            }
        )
    return bars


def _num_at(values: list[Any], index: int) -> float | None:
    if index >= len(values) or values[index] is None:
        return None
    return float(values[index])


def write_as_traded_csv(path: Path, bars: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["Date", "Open", "High", "Low", "Close", "Volume"])
        for bar in bars:
            writer.writerow(
                [
                    bar["session_date"],
                    bar["open"],
                    bar["high"],
                    bar["low"],
                    bar["close"],
                    bar["volume"],
                ]
            )


def fetch_chart_payload(symbol: str, client: httpx.Client) -> dict[str, Any]:
    ua = os.getenv("SUPEREZIO_HEART_USER_AGENT", "").strip()
    if not ua:
        raise HeartHttpError(403, reason="SUPEREZIO_HEART_USER_AGENT is required")
    url = CHART_URL.format(symbol=symbol)
    response = client.get(
        url,
        params={
            "period1": "0",
            "period2": "9999999999",
            "interval": "1d",
            "events": "split|div",
            "includeAdjustedClose": "true",
        },
        headers={"User-Agent": ua},
        timeout=30.0,
    )
    if freeze_on_yahoo_missing(response.status_code):
        raise HeartHttpError(response.status_code, response.content, reason=f"yahoo chart missing {symbol}")
    if response.status_code != 200:
        raise HeartHttpError(response.status_code, response.content, reason=f"yahoo chart {symbol}")
    return response.json()


def fetch_and_store(symbol: str, ohlcv_dir: Path, *, client: httpx.Client) -> Path:
    payload = fetch_chart_payload(symbol, client)
    bars = bars_from_chart_payload(payload)
    if not bars:
        raise HeartHttpError(422, reason=f"yahoo chart {symbol}: empty bars")
    dest = Path(ohlcv_dir) / f"{symbol.upper()}.csv"
    write_as_traded_csv(dest, bars)
    return dest


_CA_MICS = frozenset({"XTSX", "XTSV", "XTSE", "NEOE"})


def luld_symbols_for_us_tape(events: list[Any], *, limit: int = 20) -> list[str]:
    """First-seen LULD tickers that are not explicitly Canadian."""
    ordered: list[str] = []
    seen: set[str] = set()
    for event in events:
        event_type = getattr(event, "event_type", "")
        symbol = getattr(event, "symbol", None)
        mic = (getattr(event, "mic_code", None) or "").upper()
        if event_type != "nyse.luld_pause" or not symbol:
            continue
        if mic in _CA_MICS:
            continue
        key = str(symbol).upper()
        if key in seen:
            continue
        seen.add(key)
        ordered.append(key)
        if len(ordered) >= limit:
            break
    return ordered


def seed_from_events(
    events: list[Any],
    ohlcv_dir: Path,
    *,
    client: httpx.Client,
    limit: int = 20,
) -> dict[str, Any]:
    """Download as-traded CSVs. Failures are counted, never invented."""
    symbols = luld_symbols_for_us_tape(events, limit=limit)
    stored: list[str] = []
    failed: list[dict[str, str]] = []
    for symbol in symbols:
        try:
            fetch_and_store(symbol, ohlcv_dir, client=client)
            stored.append(symbol)
        except (HeartHttpError, httpx.HTTPError, OSError, ValueError) as exc:
            failed.append({"symbol": symbol, "error": str(exc)})
    return {"requested": symbols, "stored": stored, "failed": failed}


def resolve_ohlcv_dir(explicit: Path | None = None) -> Path:
    if explicit is not None:
        return Path(explicit)
    override = os.getenv("SUPEREZIO_HEART_OHLCV_DIR", "").strip()
    if override:
        return Path(override)
    return DEFAULT_HEART_ROOT / "ohlcv"


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Fetch as-traded Yahoo daily bars into Heart OHLCV CSVs.")
    parser.add_argument(
        "--ohlcv-dir",
        type=Path,
        default=None,
        help="Output directory (default: data/heart/ohlcv or SUPEREZIO_HEART_OHLCV_DIR).",
    )
    parser.add_argument(
        "--events-path",
        type=Path,
        default=None,
        help="EventBook JSONL (default: data/heart/events.jsonl).",
    )
    parser.add_argument("--from-events", action="store_true", help="Seed symbols from LULD events on disk.")
    parser.add_argument("--symbol", action="append", default=[], help="Ticker to fetch (repeatable).")
    parser.add_argument("--limit", type=int, default=3, help="Max LULD symbols when --from-events (default: 3).")
    return parser.parse_args(argv)


def run_cli(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    if not os.getenv("SUPEREZIO_HEART_USER_AGENT", "").strip():
        print("SUPEREZIO_HEART_USER_AGENT is required", file=sys.stderr)
        return 2

    ohlcv_dir = resolve_ohlcv_dir(args.ohlcv_dir)
    ohlcv_dir.mkdir(parents=True, exist_ok=True)
    symbols = [str(s).upper() for s in args.symbol]
    summary: dict[str, Any] = {"ohlcv_dir": str(ohlcv_dir), "stored": [], "failed": []}

    with httpx.Client(timeout=30.0) as client:
        if args.from_events:
            events_path = args.events_path or (DEFAULT_HEART_ROOT / "events.jsonl")
            events = EventBook(events_path).read_all() if events_path.exists() else []
            result = seed_from_events(events, ohlcv_dir, client=client, limit=args.limit)
            summary["from_events"] = result
            summary["stored"].extend(result["stored"])
            summary["failed"].extend(result["failed"])
            if not result["requested"] and not symbols:
                symbols = ["SPY"]
            elif not result["stored"] and not symbols:
                symbols = ["SPY"]

        for symbol in symbols:
            try:
                fetch_and_store(symbol, ohlcv_dir, client=client)
                if symbol not in summary["stored"]:
                    summary["stored"].append(symbol)
            except (HeartHttpError, httpx.HTTPError, OSError, ValueError) as exc:
                summary["failed"].append({"symbol": symbol, "error": str(exc)})

    if not summary["stored"] and not args.from_events and not symbols:
        print("Provide --symbol and/or --from-events", file=sys.stderr)
        return 2

    print(json.dumps(summary, indent=2))
    return 0 if summary["stored"] else 1


if __name__ == "__main__":
    sys.exit(run_cli())
