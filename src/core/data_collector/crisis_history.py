"""Long-horizon macro/market series for the CrisisMathExpert.

The twelve crisis sensors each declare their own minimum: 12 credit-to-GDP
observations, 61 market observations for the Markov regime HMM, 90 for the
multi-window LPPLS, 91 for the Hawkes MLE.  The production input path
(``core.rag.macro_dataset``) hands them a short monthly window and, measured
2026-09-14, currently returns **zero** observations for the United States and
raises ``ImportError`` (pyarrow absent) for Canada — so all twelve sensors
close with ``insufficient_data`` and the report comes back ``unavailable``.

The pinned reference cache under ``data/reference/crisis/`` already holds the
series those sensors were written for: BIS credit-to-GDP (quarterly, US and
Canada), Shiller's long equity/rate/CPI record (monthly, 1871-), FRED credit
spreads and stress indexes, and the OFR financial stress index.  This module
reads them, with no network and no key, and shapes them into the
``MacroObservation`` / ``MarketObservation`` contracts ``CrisisInput`` expects.

Parsing is fail-closed: a source that is missing, unreadable, or written in an
unexpected layout yields nothing rather than a guessed column, because these
series are what the gates count.
"""

from __future__ import annotations

import csv
import logging
import math
import zipfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from experts.crisis.contracts.schemas import CrisisInput, MacroObservation, MarketObservation

logger = logging.getLogger(__name__)

DEFAULT_REFERENCE_ROOT = Path(__file__).resolve().parents[3] / "data" / "reference" / "crisis"

# Crises need decades, not the 24-month window the collector used to pass.
DEFAULT_MAX_OBSERVATIONS = 600

# BIS numeric country code -> the collector's country label.
_BIS_COUNTRY = {
    "United States": "US",
    "Canada": "CA",
    "Brazil": "BR",
}

# FRED series used as market-series channels, and the close-like column each
# one fills.  Keys are the file stems under data/reference/crisis/.
_FRED_CHANNELS = {
    "FRED_BAMLH0A0HYM2": "credit_spread",
    "FRED_STLFSI4": "vix_like_index",
}


def _reference_root(root: str | Path | None) -> Path:
    return Path(root) if root is not None else DEFAULT_REFERENCE_ROOT


def _finite(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _quarter_to_months(period: str) -> list[str]:
    """``"1964-Q4"`` -> ``["1964-10", "1964-11", "1964-12"]``."""
    try:
        year_text, quarter_text = period.split("-Q")
        year = int(year_text)
        quarter = int(quarter_text)
    except (AttributeError, ValueError):
        return []
    if not 1 <= quarter <= 4:
        return []
    first = (quarter - 1) * 3 + 1
    return [f"{year:04d}-{month:02d}" for month in range(first, first + 3)]


def read_bis_credit_to_gdp(country: str, root: str | Path | None = None) -> dict[str, float]:
    """Credit-to-GDP ratios (BIS "actual data") keyed by ``YYYY-MM``."""
    code = _BIS_COUNTRY.get(country)
    if code is None:
        return {}
    base = _reference_root(root)
    path = base / "WS_CREDIT_GAP_csv_flat.csv"
    if not path.is_file():
        return {}

    country_column = None
    type_column = None
    period_column = None
    value_column = None
    ratios: dict[str, float] = {}
    try:
        with path.open(newline="", encoding="utf-8-sig") as handle:
            reader = csv.DictReader(handle)
            for name in reader.fieldnames or []:
                if name.startswith("BORROWERS_CTY"):
                    country_column = name
                elif name.startswith("CG_DTYPE"):
                    type_column = name
                elif name.startswith("TIME_PERIOD"):
                    period_column = name
                elif name.startswith("OBS_VALUE"):
                    value_column = name
            if not all((country_column, type_column, period_column, value_column)):
                return {}
            for row in reader:
                if not str(row.get(country_column)).startswith(f"{code}:"):
                    continue
                # "A" is the observed ratio; "B" is the HP trend and "C" the gap.
                if not str(row.get(type_column)).startswith("A:"):
                    continue
                value = _finite(row.get(value_column))
                if value is None:
                    continue
                for month in _quarter_to_months(str(row.get(period_column))):
                    ratios.setdefault(month, value)
    except OSError as exc:
        logger.debug("BIS credit-gap cache unreadable: %s", exc)
        return {}
    return ratios


def read_fred_series(series: str, root: str | Path | None = None) -> dict[str, float]:
    """A two-column FRED CSV keyed by ISO observation date."""
    base = _reference_root(root)
    path = base / f"{series}.csv"
    if not path.is_file():
        return {}
    values: dict[str, float] = {}
    try:
        with path.open(newline="", encoding="utf-8-sig") as handle:
            reader = csv.DictReader(handle)
            names = reader.fieldnames or []
            if len(names) < 2:
                return {}
            for row in reader:
                date = str(row.get(names[0]) or "").strip()
                value = _finite(row.get(names[1]))
                if date and value is not None:
                    values[date] = value
    except OSError as exc:
        logger.debug("FRED cache %s unreadable: %s", series, exc)
        return {}
    return values


def _normalize_month_cell(value: Any) -> str | None:
    """Shiller dates are ``YYYY.MM``; pandas may hand them back as text or float.

    A float ``1871.1`` is October, not January, so the two-decimal form is the
    only faithful rendering — ``f"{value:.2f}"`` keeps ``.01`` and ``.10``
    apart where ``str()`` would collapse them.
    """
    if value is None:
        return None
    if isinstance(value, float):
        if not math.isfinite(value):
            return None
        text = f"{value:.2f}"
    elif isinstance(value, int) and not isinstance(value, bool):
        text = f"{value:.2f}"
    elif isinstance(value, str):
        text = value.strip()
    else:
        return None
    if len(text) != 7 or text[4] != ".":
        return None
    try:
        year = int(text[:4])
        month = int(text[5:])
    except ValueError:
        return None
    if not 1 <= month <= 12:
        return None
    return f"{year:04d}-{month:02d}"


def read_shiller(root: str | Path | None = None) -> list[dict[str, float | str]]:
    """Shiller's monthly record: real total-return price, GS10, CPI.

    The workbook's header spans seven merged rows, so columns are taken
    positionally and the layout is asserted before any row is read.
    """
    base = _reference_root(root)
    path = base / "Shiller_ie_data.xls"
    if not path.is_file():
        return []
    try:
        import pandas as pd

        frame = pd.read_excel(path, sheet_name="Data", header=None)
    except Exception as exc:  # noqa: BLE001 - optional cache, any read failure is "no data"
        logger.debug("Shiller workbook unreadable: %s", exc)
        return []

    if frame.shape[1] < 10 or frame.shape[0] < 10:
        return []
    header = [str(value) for value in frame.iloc[7].tolist()[:10]]
    if header[:2] != ["Date", "P"] or not header[6].startswith("Rate GS10"):
        logger.warning("Shiller workbook layout changed; refusing to guess columns")
        return []

    rows: list[dict[str, float | str]] = []
    for index in range(8, frame.shape[0]):
        month = _normalize_month_cell(frame.iat[index, 0])
        if month is None:
            continue
        rows.append(
            {
                "date": month,
                "real_price": _finite(frame.iat[index, 9]) or 0.0,
                "gs10": _finite(frame.iat[index, 6]) or 0.0,
                "cpi": _finite(frame.iat[index, 4]) or 0.0,
            }
        )
    rows.sort(key=lambda row: str(row["date"]))
    return rows


def read_ofr_fsi(root: str | Path | None = None) -> dict[str, float]:
    """OFR Financial Stress Index keyed by ISO date."""
    base = _reference_root(root)
    path = base / "OFR_fsi.csv"
    if not path.is_file():
        return {}
    values: dict[str, float] = {}
    try:
        with path.open(newline="", encoding="utf-8-sig") as handle:
            reader = csv.DictReader(handle)
            names = reader.fieldnames or []
            if not names or names[0].strip().lower() != "date":
                return {}
            for row in reader:
                date = str(row.get(names[0]) or "").strip()
                value = _finite(row.get(names[1]))
                if date and value is not None:
                    values[date] = value
    except OSError as exc:
        logger.debug("OFR FSI cache unreadable: %s", exc)
        return {}
    return values


def _monthly_mean(series: dict[str, float]) -> dict[str, float]:
    """Collapse dated observations onto ``YYYY-MM`` by arithmetic mean."""
    buckets: dict[str, list[float]] = {}
    for date, value in series.items():
        month = date[:7]
        if len(month) == 7 and month[4] == "-":
            buckets.setdefault(month, []).append(value)
    return {month: sum(items) / len(items) for month, items in buckets.items()}


def _yoy(values: dict[str, float], month: str) -> float | None:
    """Year-over-year percent change from a monthly map."""
    try:
        year, index = int(month[:4]), int(month[5:])
    except (TypeError, ValueError):
        return None
    previous = f"{year - 1:04d}-{index:02d}"
    current_value = values.get(month)
    previous_value = values.get(previous)
    if current_value is None or previous_value in (None, 0.0):
        return None
    return (current_value / previous_value - 1.0) * 100.0


def build_crisis_history(
    country: str = "United States",
    *,
    reference_root: str | Path | None = None,
    max_observations: int = DEFAULT_MAX_OBSERVATIONS,
) -> dict[str, Any]:
    """Shape the reference cache into ``CrisisInput`` observations and series."""
    shiller = read_shiller(reference_root)
    credit_ratios = read_bis_credit_to_gdp(country, reference_root)
    ofr = _monthly_mean(read_ofr_fsi(reference_root))
    channels = {
        channel: _monthly_mean(read_fred_series(series, reference_root))
        for series, channel in _FRED_CHANNELS.items()
    }

    sources: list[str] = []
    if shiller:
        sources.append("shiller")
    if credit_ratios:
        sources.append("bis_credit_gap")
    if ofr:
        sources.append("ofr_fsi")
    if any(channels.values()):
        sources.append("fred")

    observations: list[MacroObservation] = []
    market_series: list[MarketObservation] = []
    cpi_by_month = {str(item["date"]): float(item["cpi"]) for item in shiller}
    window = shiller[-max_observations:] if max_observations > 0 else shiller
    for row in window:
        month = str(row["date"])
        macro: dict[str, Any] = {"date": month, "policy_rate": float(row["gs10"])}
        credit = credit_ratios.get(month)
        if credit is not None:
            macro["credit_to_gdp"] = credit
            growth = _yoy(credit_ratios, month)
            if growth is not None:
                macro["credit_growth_yoy"] = growth
        inflation = _yoy(cpi_by_month, month)
        if inflation is not None:
            macro["inflation_yoy"] = inflation
        macro["equity_index"] = float(row["real_price"])
        observations.append(MacroObservation(**macro))

        close = float(row["real_price"])
        if close <= 0:
            continue
        market: dict[str, Any] = {"date": month, "close": close}
        if ofr.get(month) is not None:
            market["vix_like_index"] = ofr[month]
        spread = channels["credit_spread"].get(month)
        if spread is not None:
            market["credit_spread"] = spread
        market_series.append(MarketObservation(**market))

    return {
        "country": country,
        "observations": observations,
        "market_series": market_series,
        "sources": sources,
        "bars": len(observations),
    }


def build_crisis_input(
    country: str = "United States",
    *,
    asset_symbol: str | None = None,
    reference_root: str | Path | None = None,
    max_observations: int = DEFAULT_MAX_OBSERVATIONS,
) -> CrisisInput | None:
    """A ready ``CrisisInput``, or ``None`` when the cache yields nothing."""
    try:
        history = build_crisis_history(
            country, reference_root=reference_root, max_observations=max_observations
        )
        observations = history["observations"]
        if not observations:
            return None
        return CrisisInput(
            country=country,
            asset_symbol=asset_symbol,
            frequency="monthly",
            observations=observations,
            market_series=history["market_series"] or None,
            metadata={
                "source": "reference_cache",
                "sources": history["sources"],
                # O cache não tem série de mercado longa fora dos EUA: o
                # market_series é o registro Shiller (EUA) mesmo para outros
                # países. Os canais por país (credit_to_gdp) são corretos.
                "market_series_country": "United States",
            },
        )
    except Exception as exc:  # noqa: BLE001 - cache is optional; never break the caller
        logger.debug("crisis reference history unavailable for %s: %s", country, exc)
        return None


def reference_available(root: str | Path | None = None) -> bool:
    """Whether the crisis reference cache is present in this tree."""
    base = _reference_root(root)
    return (base / "Shiller_ie_data.xls").is_file() and (
        base / "WS_CREDIT_GAP_csv_flat.csv"
    ).is_file()


def extract_bis_archive(root: str | Path | None = None) -> bool:
    """Materialise the flat BIS CSV from the pinned zip when only the zip exists."""
    base = _reference_root(root)
    target = base / "WS_CREDIT_GAP_csv_flat.csv"
    archive = base / "BIS_WS_CREDIT_GAP_csv_flat.zip"
    if target.is_file() or not archive.is_file():
        return target.is_file()
    try:
        with zipfile.ZipFile(archive) as bundle:
            for name in bundle.namelist():
                if name.lower().endswith(".csv"):
                    target.write_bytes(bundle.read(name))
                    return True
    except (OSError, zipfile.BadZipFile) as exc:
        logger.debug("BIS archive unusable: %s", exc)
    return False


def utcnow() -> datetime:
    """Indirection kept for callers that need a single clock source."""
    return datetime.now(UTC)


__all__ = [
    "DEFAULT_MAX_OBSERVATIONS",
    "DEFAULT_REFERENCE_ROOT",
    "build_crisis_history",
    "build_crisis_input",
    "extract_bis_archive",
    "read_bis_credit_to_gdp",
    "read_fred_series",
    "read_ofr_fsi",
    "read_shiller",
    "reference_available",
]
