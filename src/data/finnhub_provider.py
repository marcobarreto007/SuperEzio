"""
Finnhub data provider.

Used by the DataHub for real-time US/Canada equity quotes, company profiles,
and short-term (≤14 day) catalysts derived from the earnings calendar.

Free tier endpoints used:
    GET /quote               — real-time price snapshot (no volume on free tier)
    GET /stock/profile2      — company name, exchange, market cap, currency
    GET /stock/metric        — 10-day average volume (when available)
    GET /calendar/earnings   — upcoming earnings (drives 2-week catalyst)

Free tier limit is 60 calls/min, which is sufficient for the market scan
candidate gate (≤30 tickers × 3 capabilities per scan).
"""

from __future__ import annotations

import os
import threading
import time
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List

import requests

from .finnhub_symbols import finnhub_symbol_variants

_RATE_LOCK = threading.Lock()
_LAST_REQUEST_MONO = 0.0


def _set_if(d: dict, key: str, value: Any) -> None:
    """Set key in dict only if value is not None."""
    if value is not None:
        d[key] = value


def _log_event(phase: str, event: str, data: dict | None = None) -> None:
    try:
        from core.observability.neural_log import log_event

        log_event(phase, event, data or {})
    except Exception:
        pass


def _finnhub_min_interval_sec() -> float:
    raw = os.getenv("FINNHUB_MIN_INTERVAL_SEC", "1.05")
    try:
        return max(0.0, float(raw))
    except ValueError:
        return 1.05


def _finnhub_metric_cache_ttl_sec() -> float:
    raw = os.getenv("FINNHUB_METRIC_CACHE_TTL_SEC", "60")
    try:
        return max(0.0, float(raw))
    except ValueError:
        return 60.0


def _rate_limit_before_request() -> None:
    """Respect Finnhub free-tier throughput (60 calls/min)."""
    interval = _finnhub_min_interval_sec()
    if interval <= 0:
        return
    global _LAST_REQUEST_MONO
    with _RATE_LOCK:
        now = time.monotonic()
        wait = interval - (now - _LAST_REQUEST_MONO)
        if wait > 0:
            time.sleep(wait)
        _LAST_REQUEST_MONO = time.monotonic()


class FinnhubProvider:
    """
    Finnhub provider for equity price, profile, and short-term catalyst data.

    Requires FINNHUB_API_KEY in the environment.
    """

    def __init__(self, api_key: str | None = None) -> None:
        self.api_key = api_key or os.getenv("FINNHUB_API_KEY")
        if not self.api_key:
            raise RuntimeError("FINNHUB_API_KEY is required but not set")
        self.base_url = "https://finnhub.io/api/v1"
        self.timeout = 10

    # ─────────────────────────────────────────────────────────────────
    # Price / quote
    # ─────────────────────────────────────────────────────────────────
    def get_price(
        self,
        symbol: str,
        *,
        market: str | None = None,
        include_avg_volume: bool = True,
    ) -> Dict[str, Any]:
        """
        Real-time price snapshot, enriched with 10-day average volume when
        Finnhub /stock/metric exposes it on the current key tier.

        Returns:
            {symbol, price, change, change_pct, prev_close, volume?, source}
            or {"error": ...} on failure.
        """
        variants = finnhub_symbol_variants(symbol, market)
        if not variants:
            return {"error": "invalid_symbol"}

        last_error = "no_quote"
        for variant in variants:
            try:
                _rate_limit_before_request()
                response = requests.get(
                    f"{self.base_url}/quote",
                    params={"symbol": variant, "token": self.api_key},
                    timeout=self.timeout,
                )
            except Exception as exc:
                _log_event(
                    "FINNHUB",
                    "QUOTE_ERROR",
                    {"symbol": variant, "error": str(exc)},
                )
                last_error = str(exc)
                continue

            if response.status_code != 200:
                last_error = f"http_{response.status_code}"
                continue

            data = response.json() if response.content else {}
            price = data.get("c")
            if price is None or float(price) == 0.0:
                last_error = "no_quote"
                continue

            payload: Dict[str, Any] = {
                "symbol": variant,
                "requested_symbol": symbol,
                "price": float(price),
                "change": float(data.get("d") or 0.0),
                "change_pct": float(data.get("dp") or 0.0),
                "prev_close": float(data.get("pc") or 0.0),
                "source": "finnhub",
            }

            if include_avg_volume:
                volume = self._fetch_avg_volume(variant)
                if volume is not None:
                    payload["volume"] = volume
                    payload["avg_daily_volume_shares"] = volume
                    payload["volume_unit"] = "shares"

            return payload

        return {"error": last_error, "symbol": symbol, "tried": variants}

    def get_quote(self, symbol: str) -> Dict[str, Any]:
        """Alias for hub `quote` capability — same payload as get_price."""
        return self.get_price(symbol)

    def _fetch_metrics_raw(self, symbol: str) -> dict | None:
        """
        Fetch raw /stock/metric response for a symbol.
        Returns the full 'metric' dict or None on any failure.
        Successful responses are cached briefly per provider instance so
        get_price + get_fundamentals share the same API call within a scan
        cycle. Failures are not cached, because provider 429/5xx/no_payload
        states are transient in the local runtime.
        """
        if not hasattr(self, "_metrics_cache"):
            self._metrics_cache: dict[str, tuple[float, dict]] = {}
        key = symbol.upper()
        ttl = _finnhub_metric_cache_ttl_sec()
        cached = self._metrics_cache.get(key)
        if cached is not None:
            cached_at, metric = cached
            if ttl > 0 and time.monotonic() - cached_at <= ttl:
                return metric
            self._metrics_cache.pop(key, None)

        try:
            _rate_limit_before_request()
            response = requests.get(
                f"{self.base_url}/stock/metric",
                params={"symbol": symbol, "metric": "all", "token": self.api_key},
                timeout=self.timeout,
            )
            if response.status_code != 200:
                return None
            metric = (response.json() or {}).get("metric") or {}
            if not isinstance(metric, dict) or not metric:
                return None
            if ttl > 0:
                self._metrics_cache[key] = (time.monotonic(), metric)
            return metric
        except Exception:
            return None

    def _fetch_avg_volume(self, symbol: str) -> float | None:
        """
        Pull 10-day average volume from /stock/metric. Returns None when the
        endpoint is unavailable on the current tier or the field is missing.
        """
        metric = self._fetch_metrics_raw(symbol)
        if not metric:
            return None
        vol = metric.get("10DayAverageTradingVolume")
        if vol is None:
            vol = metric.get("3MonthAverageTradingVolume")
        if vol is None:
            return None
        # Finnhub /stock/metric reports 10DayAverageTradingVolume in
        # millions of shares (e.g. 2.20265 => ~2.20M shares/day).
        return float(vol) * 1_000_000.0

    # ─────────────────────────────────────────────────────────────────
    # Company profile
    # ─────────────────────────────────────────────────────────────────
    def get_profile(self, symbol: str) -> Dict[str, Any]:
        """
        Company profile: name, exchange, currency, market cap.

        Returns:
            {symbol, name, exchange, currency, market_cap, country, ipo, share_outstanding}
            or {"error": ...} on failure / empty result.
        """
        variants = finnhub_symbol_variants(symbol)
        last_error = "no_profile"
        for variant in variants:
            try:
                _rate_limit_before_request()
                response = requests.get(
                    f"{self.base_url}/stock/profile2",
                    params={"symbol": variant, "token": self.api_key},
                    timeout=self.timeout,
                )
            except Exception as exc:
                _log_event(
                    "FINNHUB",
                    "PROFILE_ERROR",
                    {"symbol": variant, "error": str(exc)},
                )
                last_error = str(exc)
                continue

            if response.status_code != 200:
                last_error = f"http_{response.status_code}"
                continue
            data = response.json() or {}
            if not data.get("name"):
                last_error = "no_profile"
                continue

            market_cap_raw = data.get("marketCapitalization")
            market_cap = (
                int(float(market_cap_raw) * 1_000_000) if market_cap_raw is not None else None
            )

            return {
                "symbol": variant,
                "requested_symbol": symbol,
                "name": data.get("name"),
                "exchange": data.get("exchange"),
                "currency": data.get("currency"),
                "market_cap": market_cap,
                "country": data.get("country"),
                "ipo": data.get("ipo"),
                "share_outstanding": data.get("shareOutstanding"),
                "source": "finnhub",
            }

        return {"error": last_error, "symbol": symbol, "tried": variants}

    # ─────────────────────────────────────────────────────────────────
    # Fundamentals (P/E, Beta, EPS, margins, ROE, sector)
    # ─────────────────────────────────────────────────────────────────
    def get_fundamentals(self, symbol: str) -> Dict[str, Any]:
        """
        Extract key fundamental metrics from Finnhub /stock/metric.

        Returns a dict with pe_ratio, beta, eps, dividend_yield, roe, roa,
        profit_margin, operating_margin, sector, industry, and more.
        Returns {"error": ...} on failure.
        """
        variants = finnhub_symbol_variants(symbol)
        last_error = "no_metrics"
        for variant in variants:
            metric = self._fetch_metrics_raw(variant)
            if not metric:
                last_error = "no_metrics"
                continue

            # ── Valuation ──
            pe = metric.get("peBasicExclExtraTTM") or metric.get("peTTM") or metric.get("peNormalizedAnnual")
            beta = metric.get("beta")
            eps = metric.get("epsBasicExclExtraItemsTTM") or metric.get("epsInclExtraItemsTTM")
            dividend_yield = metric.get("dividendYieldIndicatedAnnual")
            pb = metric.get("pbAnnual") or metric.get("pbQuarterly")
            ps = metric.get("psTTM")

            # ── Profitability ──
            roe = metric.get("roeTTM") or metric.get("roeAnnual")
            roa = metric.get("roaTTM") or metric.get("roaAnnual")
            profit_margin = metric.get("netProfitMarginTTM") or metric.get("netProfitMarginAnnual")
            operating_margin = metric.get("operatingMarginTTM") or metric.get("operatingMarginAnnual")
            gross_margin = metric.get("grossMarginTTM") or metric.get("grossMarginAnnual")

            # ── Growth ──
            revenue_growth = metric.get("revenueGrowthTTMYoy") or metric.get("revenueGrowth3Y")
            eps_growth = metric.get("epsGrowthTTMYoy") or metric.get("epsGrowth3Y")

            # ── Financial health ──
            debt_to_equity = metric.get("totalDebt/totalEquityAnnual") or metric.get("totalDebt/totalEquityQuarterly")
            current_ratio = metric.get("currentRatioAnnual") or metric.get("currentRatioQuarterly")

            # ── Classification ──
            sector = metric.get("sector")
            industry = metric.get("industry")

            # ── Volume (already in get_price, but include for completeness) ──
            avg_volume = metric.get("10DayAverageTradingVolume") or metric.get("3MonthAverageTradingVolume")
            if avg_volume is not None:
                avg_volume = float(avg_volume) * 1_000_000.0

            # Finnhub reports market capitalization in millions, matching
            # /stock/profile2. Keep DataHub's contract in absolute units.
            market_cap_raw = metric.get("marketCapitalization")
            market_cap = (
                int(float(market_cap_raw) * 1_000_000)
                if market_cap_raw is not None
                else None
            )

            payload: Dict[str, Any] = {
                "symbol": variant,
                "requested_symbol": symbol,
                "source": "finnhub",
            }

            # Only include non-None values
            _set_if(payload, "pe_ratio", pe)
            _set_if(payload, "beta", beta)
            _set_if(payload, "eps", eps)
            _set_if(payload, "dividend_yield", dividend_yield)
            _set_if(payload, "price_to_book", pb)
            _set_if(payload, "price_to_sales", ps)
            _set_if(payload, "roe", roe)
            _set_if(payload, "roa", roa)
            _set_if(payload, "profit_margin", profit_margin)
            _set_if(payload, "operating_margin", operating_margin)
            _set_if(payload, "gross_margin", gross_margin)
            _set_if(payload, "revenue_growth_yoy", revenue_growth)
            _set_if(payload, "eps_growth_yoy", eps_growth)
            _set_if(payload, "debt_to_equity", debt_to_equity)
            _set_if(payload, "current_ratio", current_ratio)
            _set_if(payload, "sector", sector)
            _set_if(payload, "industry", industry)
            _set_if(payload, "avg_daily_volume_shares", avg_volume)
            _set_if(payload, "market_cap", market_cap)

            return payload

        return {"error": last_error, "symbol": symbol, "tried": variants}

    def get_short_term_catalyst(self, symbol: str, *, window_days: int = 14) -> Dict[str, Any]:
        """
        Identify a concrete catalyst within the next `window_days` for the
        ticker by querying the earnings calendar. An earnings release inside
        the window IS a 2-week-horizon catalyst with a built-in invalidation
        condition (post-print drift).

        Returns:
            {symbol, catalyst, invalidation, event_date, confidence, source}
            or {"error": "no_catalyst_in_window"} when nothing schedulable.
        """
        today = date.today()
        end = today + timedelta(days=window_days)
        variants = finnhub_symbol_variants(symbol)
        last_error = "no_catalyst_in_window"
        for variant in variants:
            try:
                _rate_limit_before_request()
                response = requests.get(
                    f"{self.base_url}/calendar/earnings",
                    params={
                        "from": today.isoformat(),
                        "to": end.isoformat(),
                        "symbol": variant,
                        "token": self.api_key,
                    },
                    timeout=self.timeout,
                )
            except Exception as exc:
                _log_event(
                    "FINNHUB",
                    "CATALYST_ERROR",
                    {"symbol": variant, "error": str(exc)},
                )
                last_error = str(exc)
                continue

            if response.status_code != 200:
                last_error = f"http_{response.status_code}"
                continue
            data = response.json() or {}

            events = data.get("earningsCalendar") or []
            if not events:
                last_error = "no_catalyst_in_window"
                continue

            event = sorted(events, key=lambda e: e.get("date") or "")[0]
            event_date = event.get("date")
            eps_est = event.get("epsEstimate")
            rev_est = event.get("revenueEstimate")
            hour = (event.get("hour") or "").lower()
            when = {"bmo": "before market open", "amc": "after market close"}.get(hour, "")

            catalyst = f"earnings release on {event_date}"
            if when:
                catalyst += f" ({when})"
            if eps_est is not None:
                catalyst += f", EPS est {eps_est}"
            if rev_est is not None:
                catalyst += f", revenue est {rev_est:,}"

            invalidation = (
                f"close below prior-week low after {event_date} print, "
                "or guidance withdrawal / negative pre-announcement"
            )

            return {
                "symbol": variant,
                "requested_symbol": symbol,
                "catalyst": catalyst,
                "invalidation": invalidation,
                "event_date": event_date,
                "confidence": "scheduled_event",
                "source": "finnhub",
            }

        return {"error": last_error, "symbol": symbol, "tried": variants}

    # ─────────────────────────────────────────────────────────────────
    # Candles (OHLCV)
    # ─────────────────────────────────────────────────────────────────
    _CANDLE_RESOLUTION: dict[str, str] = {
        "1D": "5",
        "1W": "60",
        "1M": "D",
        "3M": "D",
        "6M": "D",
        "1Y": "D",
        "5Y": "W",
    }
    _CANDLE_LOOKBACK_DAYS: dict[str, int] = {
        "1D": 5,
        "1W": 12,
        "1M": 35,
        "3M": 100,
        "6M": 190,
        "1Y": 380,
        "5Y": 1900,
    }

    def get_candles(
        self,
        symbol: str,
        timeframe: str = "6M",
        *,
        market: str | None = None,
        **_: Any,
    ) -> Dict[str, Any]:
        """OHLCV via Finnhub /stock/candle (free tier: D/W/M resolutions)."""
        resolution = self._CANDLE_RESOLUTION.get(timeframe, "D")
        days = self._CANDLE_LOOKBACK_DAYS.get(timeframe, 190)
        end = datetime.now(timezone.utc)
        start = end - timedelta(days=days)
        params_base = {
            "resolution": resolution,
            "from": int(start.timestamp()),
            "to": int(end.timestamp()),
        }
        variants = finnhub_symbol_variants(symbol, market)
        last_error = "no_candles"
        for variant in variants:
            try:
                _rate_limit_before_request()
                response = requests.get(
                    f"{self.base_url}/stock/candle",
                    params={**params_base, "symbol": variant, "token": self.api_key},
                    timeout=self.timeout,
                )
            except Exception as exc:
                last_error = str(exc)
                continue
            if response.status_code != 200:
                last_error = f"http_{response.status_code}"
                continue
            data = response.json() or {}
            if data.get("s") != "ok":
                last_error = str(data.get("s") or "no_candles")
                continue
            times = data.get("t") or []
            if not times:
                last_error = "no_candles"
                continue
            candles: List[Dict[str, Any]] = []
            opens = data.get("o") or []
            highs = data.get("h") or []
            lows = data.get("l") or []
            closes = data.get("c") or []
            volumes = data.get("v") or []
            for i, ts in enumerate(times):
                candles.append(
                    {
                        "datetime": datetime.fromtimestamp(int(ts), tz=timezone.utc).isoformat(),
                        "open": float(opens[i]) if i < len(opens) else None,
                        "high": float(highs[i]) if i < len(highs) else None,
                        "low": float(lows[i]) if i < len(lows) else None,
                        "close": float(closes[i]) if i < len(closes) else None,
                        "volume": float(volumes[i]) if i < len(volumes) else 0,
                    }
                )
            return {
                "symbol": variant,
                "requested_symbol": symbol,
                "timeframe": timeframe,
                "candles": candles,
                "source": "finnhub",
                "provider": "finnhub",
            }
        return {"error": last_error, "symbol": symbol, "tried": variants}

    def get_news(
        self,
        query: str,
        *,
        limit: int = 5,
        **_: Any,
    ) -> List[Dict[str, Any]] | Dict[str, Any]:
        """Company headlines via /company-news (query treated as ticker)."""
        token = (query or "").strip().upper().split()[0]
        if not token:
            return {"error": "invalid_query"}
        end = date.today()
        start = end - timedelta(days=30)
        variants = finnhub_symbol_variants(token)
        last_error = "no_news"
        for variant in variants:
            try:
                _rate_limit_before_request()
                response = requests.get(
                    f"{self.base_url}/company-news",
                    params={
                        "symbol": variant,
                        "from": start.isoformat(),
                        "to": end.isoformat(),
                        "token": self.api_key,
                    },
                    timeout=self.timeout,
                )
            except Exception as exc:
                last_error = str(exc)
                continue
            if response.status_code != 200:
                last_error = f"http_{response.status_code}"
                continue
            rows = response.json()
            if not isinstance(rows, list) or not rows:
                last_error = "no_news"
                continue
            articles: List[Dict[str, Any]] = []
            for row in rows[: max(1, limit)]:
                if not isinstance(row, dict):
                    continue
                articles.append(
                    {
                        "title": row.get("headline") or row.get("title"),
                        "url": row.get("url"),
                        "source": row.get("source") or "finnhub",
                        "published_at": row.get("datetime"),
                        "summary": row.get("summary"),
                        "symbol": variant,
                        "provider": "finnhub",
                    }
                )
            if articles:
                return articles
        return {"error": last_error, "symbol": token, "tried": variants}
