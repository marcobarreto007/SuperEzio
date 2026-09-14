"""Long-horizon OHLCV assembly for the causal neural expert.

``TechnicalNeuralExpert`` withdraws ``MIN_LABELLED_SAMPLES + 21`` daily bars
before it labels a single example, and the collector used to hand it a plain
six-month window: measured 2026-09-14, ``timeframe="6M"`` returns 127 yfinance
bars, which the expert rejects with ``need 140, got 106``.  Every production
run therefore ended in ``insufficient_data`` with ``model_id: null``.

This module assembles the longest trustworthy series available for a ticker
from two free sources, in this order:

* the pinned CC0 reference cache under ``data/reference/technical_neural/``
  (deep history, one CSV per ticker, no network, no key), and
* the live provider mesh, which is fresher and is the only source for tickers
  the cache does not cover.

The provider defines the price level and the recent window; older cache bars
are spliced underneath it and rescaled so the two segments meet without a step.
The rescale is not cosmetic: measured 2026-09-14, the cache and yfinance agree
to the cent on the most recent bar but drift up to 4.2% apart on bars five
years back, because each series is back-adjusted from a different dividend
record.  Concatenating them raw would inject a 4% one-day return that never
happened into the training set of a model whose whole gate is out-of-sample
skill.
"""

from __future__ import annotations

import csv
import logging
import math
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Repo-root anchored so the loader works regardless of the process cwd.
DEFAULT_REFERENCE_ROOT = (
    Path(__file__).resolve().parents[3] / "data" / "reference" / "technical_neural"
)

# The reference cache is a static daily snapshot; the live mesh is asked for a
# window comfortably deeper than the expert's floor so a cache miss still
# leaves room to qualify.
DEFAULT_TIMEFRAME = "5Y"

_PRICE_FIELDS = ("open", "high", "low", "close")


class CandleHistoryError(RuntimeError):
    """Raised when no trustworthy bar could be assembled for a ticker."""


def reference_csv_path(ticker: str, root: Path | None = None) -> Path | None:
    """Path of the pinned reference CSV for ``ticker``, or ``None`` if absent."""
    symbol = str(ticker or "").strip().upper()
    if not symbol or not symbol[0].isalpha():
        return None
    base = Path(root) if root is not None else DEFAULT_REFERENCE_ROOT
    candidate = base / symbol[0] / f"{symbol}.csv"
    return candidate if candidate.is_file() else None


def _iso_day(epoch_seconds: float) -> str:
    return datetime.fromtimestamp(epoch_seconds, UTC).isoformat()


def read_reference_candles(ticker: str, root: Path | None = None) -> list[dict[str, Any]]:
    """Parse the pinned CSV cache into hub-shaped candles.

    Rows whose OHLCV is blank, non-finite, or economically impossible are
    dropped rather than repaired: this series trains a model, so a fabricated
    bar is worse than a missing one.
    """
    path = reference_csv_path(ticker, root)
    if path is None:
        return []
    candles: list[dict[str, Any]] = []
    seen: set[str] = set()
    try:
        with path.open(newline="", encoding="utf-8") as handle:
            for row in csv.DictReader(handle):
                try:
                    timestamp = float(row["timestamp"])
                    values = {name: float(row[name]) for name in _PRICE_FIELDS}
                    volume = float(row.get("volume") or 0.0)
                except (KeyError, TypeError, ValueError):
                    continue
                prices = list(values.values())
                if not all(math.isfinite(value) for value in prices):
                    continue
                if min(prices) <= 0 or not math.isfinite(volume) or volume < 0:
                    continue
                if values["high"] < max(values["open"], values["close"]):
                    continue
                if values["low"] > min(values["open"], values["close"]):
                    continue
                observed_at = _iso_day(timestamp)
                if observed_at in seen:
                    continue
                seen.add(observed_at)
                candles.append(
                    {
                        "datetime": observed_at,
                        "observed_at": observed_at,
                        "open": values["open"],
                        "high": values["high"],
                        "low": values["low"],
                        "close": values["close"],
                        "volume": volume,
                    }
                )
    except OSError as exc:
        logger.debug("reference cache unreadable for %s: %s", ticker, exc)
        return []
    candles.sort(key=lambda candle: str(candle["datetime"]))
    return candles


def _provider_candles(ticker: str, timeframe: str) -> list[dict[str, Any]]:
    """Ask the provider mesh for candles; never raise at this boundary."""
    try:
        from data.data_hub import hub

        result = hub.get_candles(ticker, timeframe=timeframe)
    except Exception as exc:  # noqa: BLE001 - provider mesh is best-effort
        logger.debug("provider candles unavailable for %s: %s", ticker, exc)
        return []
    if not isinstance(result, dict) or result.get("error"):
        return []
    raw = result.get("candles")
    if not isinstance(raw, list):
        return []
    cleaned: list[dict[str, Any]] = []
    for candle in raw:
        if not isinstance(candle, dict):
            continue
        close = candle.get("close")
        try:
            close_value = float(close)
        except (TypeError, ValueError):
            continue
        if not math.isfinite(close_value) or close_value <= 0:
            continue
        cleaned.append(candle)
    cleaned.sort(key=lambda candle: str(candle.get("datetime") or candle.get("date") or ""))
    return cleaned


def splice_history(
    older: list[dict[str, Any]], recent: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Append ``older`` behind ``recent``, rescaling it onto ``recent``'s level.

    Bars at or after ``recent``'s first timestamp are dropped from ``older`` —
    the fresher series owns every instant it covers, so no timestamp is ever
    duplicated and no two sources disagree inside the returned series.
    """
    if not older:
        return list(recent)
    if not recent:
        return list(older)

    boundary = str(recent[0].get("datetime") or recent[0].get("date") or "")
    if not boundary:
        return list(recent)

    tail = [candle for candle in older if str(candle["datetime"]) < boundary]
    if not tail:
        return list(recent)

    try:
        anchor_old = float(tail[-1]["close"])
        anchor_new = float(recent[0]["close"])
    except (KeyError, TypeError, ValueError):
        return list(recent)
    if not math.isfinite(anchor_old) or anchor_old <= 0 or not math.isfinite(anchor_new):
        return list(recent)

    scale = anchor_new / anchor_old
    rescaled: list[dict[str, Any]] = []
    for candle in tail:
        adjusted = dict(candle)
        for field in _PRICE_FIELDS:
            try:
                adjusted[field] = float(candle[field]) * scale
            except (KeyError, TypeError, ValueError):
                adjusted = {}
                break
        if adjusted:
            rescaled.append(adjusted)
    return [*rescaled, *recent]


def load_candle_history(
    ticker: str,
    *,
    timeframe: str = DEFAULT_TIMEFRAME,
    reference_root: str | Path | None = None,
    use_reference: bool = True,
) -> dict[str, Any]:
    """Assemble the longest trustworthy OHLCV series for ``ticker``.

    Returns a provider-shaped payload (``candles`` list, else ``error``) so it
    is a drop-in for ``DataHub.get_candles``.
    """
    symbol = str(ticker or "").strip().upper()
    if not symbol:
        return {"error": "invalid_symbol"}

    root = Path(reference_root) if reference_root is not None else None
    cached = read_reference_candles(symbol, root) if use_reference else []
    recent = _provider_candles(symbol, timeframe)

    sources: list[str] = []
    if cached:
        sources.append("reference_cache")
    if recent:
        sources.append("provider")

    candles = splice_history(cached, recent)
    if not candles:
        return {"error": "no_candle_history", "symbol": symbol}

    return {
        "symbol": symbol,
        "timeframe": timeframe,
        "candles": candles,
        "bars": len(candles),
        "sources": sources,
        "source": "+".join(sources) or "unknown",
    }


def load_candle_history_safe(ticker: str, **kwargs: Any) -> dict[str, Any]:
    """``load_candle_history`` behind a fail-closed boundary.

    The collector calls this from a worker thread; a data-source problem must
    degrade the expert, never abort the whole collection.
    """
    try:
        return load_candle_history(ticker, **kwargs)
    except Exception as exc:  # noqa: BLE001 - collection is best-effort
        logger.debug("candle history unavailable for %s: %s", ticker, exc)
        return {"error": f"candle_history: {exc}", "symbol": str(ticker).upper()}


__all__ = [
    "DEFAULT_REFERENCE_ROOT",
    "DEFAULT_TIMEFRAME",
    "CandleHistoryError",
    "load_candle_history",
    "load_candle_history_safe",
    "read_reference_candles",
    "reference_csv_path",
    "splice_history",
]
