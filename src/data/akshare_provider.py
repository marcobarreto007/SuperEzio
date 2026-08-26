"""
AKShare provider — free US stock OHLCV data (intraday and daily).

AKShare is a Chinese open-source data library that provides free access to
East Money / Sina Finance US stock endpoints. No API key is required.

Documentation:
  - https://akshare.akfamily.xyz/
  - https://github.com/akfamily/akshare

Ticker format: AKShare uses "105.{TICKER}" for US stocks (e.g. "105.AAPL").
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

_AKSHARE_IMPORT_ERROR: str | None = None

try:
    import akshare as ak
except ImportError as _exc:
    _AKSHARE_IMPORT_ERROR = str(_exc)
    ak = None  # type: ignore[assignment]


def _akshare_us_symbol(symbol: str) -> str | None:
    """Convert a plain ticker like "AAPL" to AKShare format "105.AAPL"."""
    raw = (symbol or "").strip().upper()
    if not raw:
        return None
    # Already in AKShare format?
    if raw.startswith("105."):
        return raw
    # Strip exchange suffixes
    for suffix in (".US", ".NYS", ".NASDAQ", ".NYSE"):
        if raw.endswith(suffix):
            raw = raw[: -len(suffix)]
            break
    return f"105.{raw}"


# ── Isolamento anti-crash (INV-R29) ────────────────────────────────────────
# `ak.get_us_stock_name()` passa por `stock_us_sina`, que usa py_mini_racer
# (V8). Nesta maquina o V8 aborta o processo Python INTEIRO com
# 0x80000003 (fatal, sem excecao capturavel por try/except). Reproduzido
# 3x: suite de testes (2x) e servidor live (2026-08-18, chat real).
# Solucao: rodar a chamada em subprocesso — quem morre e o filho; o
# servidor sobrevive e o DataHub cai para o proximo provider.

_AKSHARE_NAMES_CHILD = (
    "import sys\n"
    "sys.stdout.reconfigure(encoding='utf-8')\n"
    "import akshare as ak\n"
    "try:\n"
    "    df = ak.get_us_stock_name()\n"
    "    df.to_csv(sys.stdout, index=False)\n"
    "except Exception as e:\n"
    "    sys.stderr.write('AKCHILD_ERR:' + repr(e))\n"
    "    sys.exit(2)\n"
)


def _us_stock_names_via_subprocess(timeout_s: float = 25.0) -> dict[str, Any]:
    """Obtem a tabela de nomes de US stocks sem arriscar o processo pai.

    Retorna ``{"names_csv": ...}`` em sucesso ou ``{"error": ...}``.
    """
    import subprocess
    import sys

    try:
        proc = subprocess.run(
            [sys.executable, "-c", _AKSHARE_NAMES_CHILD],
            capture_output=True,
            timeout=timeout_s,
        )
    except subprocess.TimeoutExpired:
        return {"error": "akshare_js_timeout"}

    if proc.returncode != 0:
        stderr = proc.stderr.decode("utf-8", errors="replace").strip()[:200]
        return {"error": f"akshare_js_subprocess_rc={proc.returncode} {stderr}"}

    csv_text = proc.stdout.decode("utf-8", errors="replace")
    if not csv_text.strip():
        return {"error": "akshare_js_empty_output"}
    return {"names_csv": csv_text}


def _parse_names_csv(csv_text: str):
    """Converte o CSV do subprocesso em DataFrame."""
    import io

    import pandas as pd

    try:
        return pd.read_csv(io.StringIO(csv_text))
    except Exception:
        return None


class AKShareProvider:
    """Free US stock price, candles and profile data via AKShare.

    Methods follow the DataHub convention: they return a dict with ``error``
    on failure or standardised fields on success.
    """

    def __init__(self) -> None:
        self._import_error = _AKSHARE_IMPORT_ERROR

    # ------------------------------------------------------------------
    # Price (latest quote)
    # ------------------------------------------------------------------

    def get_price(
        self,
        symbol: str,
        *,
        market: str | None = None,
        **_: Any,
    ) -> dict[str, Any]:
        """Fetch the latest price and volume for a US stock.

        Uses the realtime spot endpoint (``stock_us_spot``) which returns a
        DataFrame of all US stocks, then filters for the requested symbol.
        """
        asymbol = _akshare_us_symbol(symbol)
        if not asymbol:
            return {"error": "invalid_symbol"}

        if ak is None:
            return {"error": f"akshare_not_installed: {self._import_error}"}

        try:
            # stock_us_spot() returns all US stocks with Chinese column names
            spot_df = ak.stock_us_spot()  # type: ignore[union-attr]
            if spot_df is None or spot_df.empty:
                return {"error": "akshare_spot_empty"}

            match = spot_df[spot_df.iloc[:, 0].astype(str).str.contains(asymbol, na=False)]
            if match.empty:
                return {"error": "akshare_ticker_not_found"}

            row = match.iloc[0]
            # Columns: 0=代码(symbol), 1=最新价(price), 5=成交量(volume)
            price_raw = row.iloc[1] if len(row) > 1 else None
            volume_raw = row.iloc[5] if len(row) > 5 else None

            price: float | None = None
            try:
                price = float(price_raw)
            except (TypeError, ValueError):
                pass

            volume: int | None = None
            try:
                volume = int(float(str(volume_raw).replace(",", "")))
            except (TypeError, ValueError):
                pass

            if price is None or price <= 0:
                return {"error": "akshare_no_price"}

            return {
                "symbol": symbol,
                "akshare_symbol": asymbol,
                "price": price,
                "volume": volume,
                "source": "akshare",
                "provider": "akshare",
            }
        except Exception as exc:
            return {"error": f"akshare_get_price: {exc}"}

    # ------------------------------------------------------------------
    # Candles (OHLCV history)
    # ------------------------------------------------------------------

    _PERIOD_MAP: dict[str, str] = {
        "1D": "daily",
        "1W": "weekly",
        "1M": "monthly",
        "3M": "monthly",
        "6M": "daily",
        "1Y": "daily",
        "5Y": "daily",
    }

    def get_candles(
        self,
        symbol: str,
        timeframe: str = "6M",
        *,
        market: str | None = None,
        **_: Any,
    ) -> dict[str, Any]:
        """Fetch historical OHLCV candles.

        Supports daily, weekly, monthly periods. For intraday (1/5/15/30/60 min)
        uses the minute endpoint (``stock_us_hist_min_em``) when the timeframe
        starts with a number followed by "m" or "min".
        """
        asymbol = _akshare_us_symbol(symbol)
        if not asymbol:
            return {"error": "invalid_symbol"}

        if ak is None:
            return {"error": f"akshare_not_installed: {self._import_error}"}

        # -- Intraday (>1min, <1D) -------------------------------------------
        intraday_match = self._parse_intraday_timeframe(timeframe)
        if intraday_match is not None:
            return self._get_intraday_candles(asymbol, symbol, timeframe)

        # -- Daily / weekly / monthly -----------------------------------------
        period = self._PERIOD_MAP.get(timeframe, "daily")
        days_lookback: dict[str, int] = {
            "1D": 5,
            "1W": 30,
            "1M": 90,
            "3M": 180,
            "6M": 365,
            "1Y": 365,
            "5Y": 1825,
        }
        lookback = days_lookback.get(timeframe, 365)

        try:
            df = ak.stock_us_hist(  # type: ignore[union-attr]
                symbol=asymbol,
                period=period,
                start_date="19700101",
                end_date="22220101",
                adjust="",
            )
        except Exception as exc:
            return {"error": f"akshare_hist: {exc}"}

        if df is None or df.empty:
            return {"error": "akshare_no_candles"}

        # Chinese column names: 日期, 开盘, 收盘, 最高, 最低, 成交量
        # Sort by date ascending, then take the last N rows
        df = df.sort_values(by=df.columns[0])
        df = df.tail(lookback)

        candles: list[dict[str, Any]] = []
        for _, row in df.iterrows():
            try:
                date_val = row.iloc[0]
                dt = self._parse_date(date_val)
                candles.append(
                    {
                        "datetime": dt.isoformat() if dt else str(date_val),
                        "open": float(row.iloc[1]),
                        "high": float(row.iloc[2]),
                        "low": float(row.iloc[3]),
                        "close": float(row.iloc[4]),
                        "volume": float(row.iloc[5]) if len(row) > 5 else 0,
                    }
                )
            except (ValueError, TypeError):
                continue

        if not candles:
            return {"error": "akshare_no_candles_parsed"}

        return {
            "symbol": symbol,
            "akshare_symbol": asymbol,
            "timeframe": timeframe,
            "candles": candles,
            "source": "akshare",
            "provider": "akshare",
        }

    def _get_intraday_candles(self, asymbol: str, symbol: str, timeframe: str) -> dict[str, Any]:
        """Fetch intraday minute candles via stock_us_hist_min_em."""
        try:
            df = ak.stock_us_hist_min_em(  # type: ignore[union-attr]
                symbol=asymbol,
                start_date="1979-09-01 09:32:00",
                end_date="2222-01-01 09:32:00",
            )
        except Exception as exc:
            return {"error": f"akshare_intraday: {exc}"}

        if df is None or df.empty:
            return {"error": "akshare_no_intraday"}

        # Determine how many rows to keep based on timeframe
        limit = self._intraday_limit(timeframe)
        df = df.tail(limit)

        candles: list[dict[str, Any]] = []
        for _, row in df.iterrows():
            try:
                # Columns: 0=date, 1=open, 2=close, 3=high, 4=low, 5=volume
                date_val = row.iloc[0]
                dt = self._parse_date(str(date_val))
                candles.append(
                    {
                        "datetime": dt.isoformat() if dt else str(date_val),
                        "open": float(row.iloc[1]),
                        "high": float(row.iloc[3]),
                        "low": float(row.iloc[4]),
                        "close": float(row.iloc[2]),
                        "volume": float(row.iloc[5]) if len(row) > 5 else 0,
                    }
                )
            except (ValueError, TypeError):
                continue

        if not candles:
            return {"error": "akshare_no_intraday_parsed"}

        return {
            "symbol": symbol,
            "akshare_symbol": asymbol,
            "timeframe": timeframe,
            "candles": candles,
            "source": "akshare",
            "provider": "akshare",
        }

    @staticmethod
    def _parse_intraday_timeframe(timeframe: str) -> bool | None:
        """Return True if timeframe looks like intraday (e.g. '5m', '15min', '60min').

        SuperEzio standard timeframes use uppercase 'M' for months (1M, 3M, 6M)
        and lowercase 'm' for minutes (1m, 5m, 15m). We preserve the original
        casing to disambiguate: if the raw string is uppercase and ends with 'M',
        it is monthly, not intraday.
        """
        t_raw = (timeframe or "").strip()
        # SuperEzio monthly standard: "1M", "3M", "6M" — all-uppercase with 'M' suffix
        if t_raw.isupper() and t_raw.endswith("M"):
            return None
        t = t_raw.lower()
        if t.endswith("m") or t.endswith("min"):
            return True
        return None

    @staticmethod
    def _intraday_limit(timeframe: str) -> int:
        """Estimate how many minute-rows to keep for the given timeframe."""
        t = (timeframe or "").strip().lower().replace("min", "").replace("m", "")
        try:
            minutes = int(t)
        except ValueError:
            return 390  # default: one trading day
        # Typical: ~390 minute-bars per trading day
        # For a 5-min chart, 78 bars per day
        if minutes >= 60:
            return 65  # ~1 week of hourly
        if minutes >= 30:
            return 130  # ~1 week of 30min
        if minutes >= 15:
            return 260  # ~2 weeks of 15min
        if minutes >= 5:
            return 780  # ~2 weeks of 5min
        return 390  # 1min bars — 1 day

    @staticmethod
    def _parse_date(value: Any) -> datetime | None:
        """Try to parse a date value into a UTC datetime."""
        if value is None:
            return None
        if isinstance(value, datetime):
            return value.replace(tzinfo=UTC) if value.tzinfo is None else value
        if isinstance(value, str):
            for fmt in (
                "%Y-%m-%d",
                "%Y-%m-%d %H:%M:%S",
                "%Y/%m/%d",
                "%Y%m%d",
            ):
                try:
                    return datetime.strptime(value, fmt).replace(tzinfo=UTC)
                except ValueError:
                    continue
        return None

    # ------------------------------------------------------------------
    # Profile (company info)
    # ------------------------------------------------------------------

    def get_profile(
        self,
        symbol: str,
        *,
        market: str | None = None,
        **_: Any,
    ) -> dict[str, Any]:
        """Fetch company name and basic profile info.

        Uses the ``get_us_stock_name`` mapping to find the English name.
        """
        asymbol = _akshare_us_symbol(symbol)
        if not asymbol:
            return {"error": "invalid_symbol"}

        if ak is None:
            return {"error": f"akshare_not_installed: {self._import_error}"}

        # get_us_stock_name usa py_mini_racer (V8) que aborta o processo
        # inteiro nesta maquina — rodar isolado em subprocesso (INV-R29).
        try:
            payload = _us_stock_names_via_subprocess()
        except Exception as exc:
            return {"error": f"akshare_profile: {exc}"}

        if "error" in payload:
            return {"error": f"akshare_profile: {payload['error']}"}

        names_df = _parse_names_csv(payload["names_csv"])

        if names_df is None or names_df.empty:
            return {"error": "akshare_no_names"}

        # Find row by symbol (first column is typically the code/symbol)
        match = names_df[names_df.iloc[:, 0].astype(str).str.contains(asymbol, na=False)]
        if match.empty:
            # Try the original symbol
            match = names_df[names_df.iloc[:, 0].astype(str).str.contains(symbol, na=False)]
        if match.empty:
            return {"error": "akshare_ticker_not_found"}

        row = match.iloc[0]
        name = str(row.iloc[1]) if len(row) > 1 else symbol
        cname = str(row.iloc[2]) if len(row) > 2 else ""

        return {
            "symbol": symbol,
            "akshare_symbol": asymbol,
            "name": name.strip(),
            "chinese_name": cname.strip(),
            "source": "akshare",
            "provider": "akshare",
        }
