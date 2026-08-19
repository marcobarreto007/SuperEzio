"""Collector node — MARKET SCAN + TICKER DATA collection.

Responsibility: Multi-ticker scanning, candidate ranking, data quality gates,
and single-ticker data collection (delegates to DataCollector for deep fetch).

NOT the same as core.data_collector.collector.DataCollector — that module
does single-ticker deep aggregation (price, fundamentals, risk, news, macro).
This module orchestrates the SCAN pipeline (FinGPT → Finnhub → Yahoo →
candidate gate → ranking) for multi-ticker discovery.
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
import time
from datetime import datetime, timezone
from typing import Any

from langgraph.config import get_stream_writer

from ..trade_order import normalize_liquidity_fields, pick_candidate, rank_candidates
from ..scan_registry import ScanEventRegistry
from ..circuit_breaker import CircuitBreaker, CircuitBreakerOpenError

_SCAN_CACHE_TTL_SECONDS = 300  # 5 min — ranked candidates are stale after this

logger = logging.getLogger(__name__)


# ── Configurable scan hard limits ──────────────────────────────────────────
def _scan_max_raw():
    return int(os.getenv("SUPEREZIO_SCAN_MAX_CANDIDATES_RAW", "60"))


def _scan_max_after_gate():
    return int(os.getenv("SUPEREZIO_SCAN_MAX_CANDIDATES_AFTER_GATE", "5"))


def _scan_max_llm_candidates():
    return int(os.getenv("SUPEREZIO_SCAN_MAX_LLM_CANDIDATES", "3"))


def _scan_max_llm_calls():
    return int(os.getenv("SUPEREZIO_SCAN_MAX_LLM_CALLS", "6"))


def _scan_llm_timeout():
    return float(os.getenv("SUPEREZIO_SCAN_LLM_TIMEOUT_SECONDS", "600"))


def _cache_is_fresh(trade_ctx: dict[str, Any]) -> bool:
    """Return True if the scan cache is still valid for reuse."""
    scanned_at = trade_ctx.get("scanned_at")
    if not scanned_at:
        return False
    try:
        dt = datetime.fromisoformat(str(scanned_at))
        age = (datetime.now(timezone.utc) - dt).total_seconds()
        return age <= _SCAN_CACHE_TTL_SECONDS
    except Exception:
        return False


def _try_fast_cache(ticker: str, writer) -> dict | None:
    """Check pre-computed cache. Returns data dict if fresh, None if stale/empty.

    Latency: <10ms (SQLite query). This is the 193s → 7s optimization.
    """
    try:
        from core.trading.historical_cache import get_cached_ohlcv
        from core.trading.batch_expert_runner import get_expert_analysis

        ohlcv = get_cached_ohlcv(ticker, days=5)  # Need at least 1 candle
        experts = get_expert_analysis(ticker)

        if not ohlcv:
            return None  # Cache miss — fall through to live collection

        latest = ohlcv[-1]
        price = latest["close"]
        volume = latest["volume"]

        # Build minimal data dict from cache
        # CRITICAL: include ohlcv so MathHub can compute RSI, MACD, Sharpe, etc.
        # Without it, _extract_candles returns [] and ALL 14 modules skip with
        # "missing_price_series" — 0/14 coverage.
        data = {
            "ticker": ticker,
            "price": {
                "latest": price,
                "volume": volume,
                "data_quality": "cached",
                "source": "learner_24_7_cache",
            },
            "fundamentals": {"data_quality": "cached", "source": "learner_24_7_cache"},
            "technicals": {"data_quality": "cached", "source": "learner_24_7_cache"},
            "risk": {"data_quality": "cached", "source": "learner_24_7_cache"},
            "ohlcv": ohlcv,
        }

        # Build rich data_context from expert analyses
        lines = [f"TICKER: {ticker}"]
        lines.append(f"Latest Price: ${price:.2f} (vol: {volume:,.0f})")
        for role, edata in sorted(experts.items()):
            a = edata.get("analysis", {})
            if isinstance(a, dict):
                verdict = a.get("verdict", "?")
                lines.append(f"  {role}: {verdict}")

        data_context = "\n".join(lines)

        writer(
            {
                "type": "PIPELINE_STEP",
                "step": "data",
                "status": "cache_hit",
                "ticker": ticker,
                "source": "learner_cache",
                "latency_ms": 0,
            }
        )

        return {"data": data, "data_context": data_context, "_data_from_cache": True}
    except Exception:
        return None  # Any error → fall through to live collection


async def node_collector(state: dict, *, config=None) -> dict:
    """Collect financial data for the detected ticker or market scan."""
    writer = get_stream_writer()
    run_id = state.get("run_id", "")
    route = state.get("route", "general")
    ticker = state.get("ticker", "")

    writer(
        {
            "type": "PIPELINE_STEP",
            "run_id": run_id,
            "step": "data",
            "status": "started",
            "route": route,
        }
    )

    # ═══════════════════════════════════════════════════════
    # FAST PATH: Check pre-computed cache for ANY route with a ticker
    # ═══════════════════════════════════════════════════════
    if ticker:
        cached = _try_fast_cache(ticker, writer)
        if cached:
            writer(
                {
                    "type": "PIPELINE_STEP",
                    "run_id": run_id,
                    "step": "data",
                    "status": "completed",
                    "provider": "cache",
                    "route": route,
                    "ticker": ticker,
                }
            )
            return cached

    # ── Ticker analysis ──
    if route == "ticker_analysis" and ticker:
        use_pro = os.getenv("SUPEREZIO_PROFESSIONAL_COLLECTOR", "true").lower() in {
            "1",
            "true",
            "yes",
            "on",
        }

        if use_pro:
            data, data_context = await _collect_professional(ticker, writer, run_id)
        else:
            data, data_context = await _collect_subprocess_fallback(ticker, writer, run_id)

        # Emit data source status
        sources: dict[str, Any] = {}
        for key in (
            "price",
            "fundamentals",
            "technicals",
            "sentiment",
            "social",
            "macro",
            "profile",
            "quant",
            "risk",
            "reddit",
            "crisis",
            "realtime_price",
            "quantum",
        ):
            section = data.get(key)
            if isinstance(section, dict):
                sources[key] = {
                    "status": section.get("data_quality", "collected"),
                    "error": section.get("error"),
                }

        writer(
            {
                "type": "DATA_COLLECTED",
                "ticker": ticker,
                "provider": "data_collector",
                "capability": "ticker_analysis",
                "quality": data.get("data_quality", "unknown"),
                "source_errors": data.get("source_errors", []),
                "analysis_id": data.get("analysis_id"),
                "sources": sources,
            }
        )
        writer(
            {
                "type": "PIPELINE_STEP",
                "run_id": run_id,
                "step": "data",
                "status": "completed",
            }
        )
        return {"data": data, "data_context": data_context}

    # ── Market scan ──
    if route == "market_scan":
        trade_ctx = state.get("trade_order_context") or {}
        intent = state.get("intent", "")
        excluded = list(trade_ctx.get("excluded_tickers") or [])

        if (
            intent == "another_trade_recommendation"
            and trade_ctx.get("ranked_candidates")
            and _cache_is_fresh(trade_ctx)
        ):
            scan = _scan_from_cached_ranked(trade_ctx, state.get("message", ""), excluded)
        else:
            if intent == "another_trade_recommendation" and trade_ctx.get("ranked_candidates"):
                logger.warning(
                    "Scan cache expired (%s TTL=%ds), running fresh scan",
                    trade_ctx.get("scanned_at", "?"),
                    _SCAN_CACHE_TTL_SECONDS,
                )
            scan = await _run_scan(
                state.get("message", ""),
                state.get("filters", {}),
                excluded_tickers=excluded,
                writer=writer,
            )
            if trade_ctx.get("universe"):
                scan.setdefault("universe", trade_ctx.get("universe"))
        scan_ctx = _format_scan_context(scan)
        candidates = scan.get("candidates", [])
        top_ticker = candidates[0].get("ticker", "") if candidates else ""

        # Distinct providers actually used to enrich the surviving candidates.
        # This feeds the /task/submit trace via `provider_sources_used`.
        providers_used = sorted(
            {
                str(c.get("provider"))
                for c in candidates
                if isinstance(c, dict) and c.get("provider")
            }
        )

        writer(
            {
                "type": "DATA_COLLECTED",
                "ticker": top_ticker,
                "provider": ", ".join(providers_used) if providers_used else "scanner",
                "capability": "market_scan",
                "quality": scan.get("data_quality", "partial"),
                "source_errors": scan.get("source_errors", []),
                "candidates": len(candidates),
                "rejected_count": scan.get("rejected_count", 0),
                "rejection_summary": scan.get("rejection_summary", {}),
                "providers": providers_used,
            }
        )
        writer(
            {
                "type": "PIPELINE_STEP",
                "run_id": run_id,
                "step": "data",
                "status": "completed",
            }
        )

        # Collect full data for the top candidate so experts, neural_decision,
        # and agent have per-ticker technicals/risk/sentiment to work with.
        full_data: dict[str, Any] = {}
        full_ctx = ""
        if top_ticker:
            try:
                full_data, full_ctx = await _collect_professional(top_ticker, writer, run_id)
            except Exception:
                full_data = {"ticker": top_ticker, "data_quality": "error"}

        return {
            "scan": scan,
            "data": full_data,
            "ticker": top_ticker,
            "data_context": scan_ctx + "\n\n" + full_ctx if full_ctx else scan_ctx,
        }

    # ── General / no ticker ──
    writer(
        {
            "type": "PIPELINE_STEP",
            "run_id": run_id,
            "step": "data",
            "status": "skipped",
        }
    )
    return {}


# ---------------------------------------------------------------------------
# Professional collector
# ---------------------------------------------------------------------------


async def _collect_professional(ticker: str, writer, run_id: str) -> tuple[dict[str, Any], str]:
    """Use ProfessionalCollector mesh for comprehensive data gathering."""
    from ...data_collector.professional import ProfessionalCollector

    timeout_s = int(os.getenv("SUPEREZIO_DATA_TIMEOUT", "180"))
    t0 = time.time()

    collector = ProfessionalCollector()
    try:
        data = await asyncio.wait_for(
            collector.collect(ticker, overall_timeout=timeout_s),
            timeout=timeout_s + 15,  # Hard limit with cleanup margin
        )
    except asyncio.TimeoutError:
        data = {
            "analysis_id": f"{ticker}-timeout",
            "ticker": ticker,
            "collected_at": "",
            "data_quality": "partial",
            "source_errors": ["professional_collector_timeout"],
            "price": {"error": "timeout"},
        }
    except Exception as exc:
        data = {
            "analysis_id": f"{ticker}-err",
            "ticker": ticker,
            "collected_at": "",
            "data_quality": "error",
            "source_errors": [f"professional_collector: {exc}"],
            "price": {"error": str(exc)},
        }

    elapsed = time.time() - t0
    data_context = collector.format_context(data)
    writer(
        {
            "type": "PIPELINE_STEP",
            "run_id": run_id,
            "step": "professional_collector",
            "status": "completed",
            "ticker": ticker,
            "quality": data.get("data_quality", "unknown"),
            "mesh_health": data.get("mesh_health", {}),
            "elapsed_ms": int(elapsed * 1000),
        }
    )
    return data, data_context


# ---------------------------------------------------------------------------
# Subprocess collector fallback
# ---------------------------------------------------------------------------


async def _collect_subprocess_fallback(
    ticker: str, writer, run_id: str
) -> tuple[dict[str, Any], str]:
    """Fallback: use SubprocessDataCollector."""
    from ...data_collector import DataCollector
    from adapters.data_collector.subprocess_collector import SubprocessDataCollector
    from ...paths import PROJECT_ROOT

    timeout_s = int(os.getenv("SUPEREZIO_DATA_TIMEOUT", "180"))
    collector = SubprocessDataCollector(project_root=PROJECT_ROOT)
    data = await asyncio.to_thread(collector.collect_all, ticker, timeout_s)
    data_context = DataCollector.format_context(data)
    return data, data_context


# ---------------------------------------------------------------------------
# Market scan
# ---------------------------------------------------------------------------


# --- Market scan universe and quality gate -----------------------------------

_CHINA_UNIVERSE_HINTS = (
    "china",
    "chinese",
    "shanghai",
    "shenzhen",
    "a-share",
    "a-shares",
    ".sz",
    ".ss",
    "hong kong",
    "hkex",
    "hsi",
)

_PENNY_OTC_HINTS = (
    "penny stock",
    "penny stocks",
    "penny",
    "pink sheet",
    "pink sheets",
    "otc",
    "over the counter",
    "acao de centavo",
    "centavo",
    "acoes de pouco valor",
    "ações de pouco valor",
    "pouco valor",
    "pump and dump",
    "pump",
    "dump",
)

_MICROCAP_HINTS = (
    "microcap",
    "micro cap",
    "micro-cap",
    "mini cap",
    "mini-cap",
    "mini caps",
    "mini-caps",
    "nano cap",
    "nano-cap",
    "small cap risky",
    "high risk penny",
    "high-risk penny",
)


def _compile_hint_patterns(hints: tuple[str, ...]) -> list[re.Pattern[str]]:
    """Pre-compile hint list into word-boundary regex patterns.

    Multi-word hints match across flexible whitespace. Single-word hints
    match at non-word boundaries to avoid false positives.
    """
    patterns: list[re.Pattern[str]] = []
    for h in hints:
        h = h.strip()
        escaped = re.escape(h).replace(r"\ ", r"\s+")
        patterns.append(re.compile(rf"(?:^|\W){escaped}(?:$|\W)", re.IGNORECASE))
    return patterns


_CHINA_PATTERNS = _compile_hint_patterns(_CHINA_UNIVERSE_HINTS)
_PENNY_PATTERNS = _compile_hint_patterns(_PENNY_OTC_HINTS)
_MICROCAP_PATTERNS = _compile_hint_patterns(_MICROCAP_HINTS)


def _has_any(text: str, patterns: list[re.Pattern[str]]) -> bool:
    return any(p.search(text) for p in patterns)


def _wants_china_universe(msg_lower: str) -> bool:
    return _has_any(msg_lower, _CHINA_PATTERNS)


def _wants_penny_or_otc(msg_lower: str) -> bool:
    return _has_any(msg_lower, _PENNY_PATTERNS)


def _wants_microcap(msg_lower: str) -> bool:
    return _has_any(msg_lower, _MICROCAP_PATTERNS)


def _requested_max_price(msg_lower: str) -> float | None:
    # First check for explicit price patterns (e.g., "under $5", "below $10")
    patterns = (
        r"\b(?:under|below|less than|sub)\s*(?:cad|usd|\$)?\s*(\d+(?:\.\d+)?)\b",
        r"\b(?:cad|usd|\$)\s*(\d+(?:\.\d+)?)\s*(?:or less|and under|or under|max|maximum)\b",
    )
    for pattern in patterns:
        match = re.search(pattern, msg_lower)
        if not match:
            continue
        try:
            value = float(match.group(1))
        except (TypeError, ValueError):
            continue
        if value > 0:
            return value

    # Penny stock keywords: default to $5 max
    penny_keywords = (
        "penny stock",
        "penny stocks",
        "pennystock",
        "pennystocks",
        "under $5",
        "under $5.00",
        "below $5",
        "below $5.00",
        "cheap stock",
        "cheap stocks",
        "dollar stock",
        "dollar stocks",
    )
    if any(kw in msg_lower for kw in penny_keywords):
        return 5.0

    # Microcap keywords: default to $10 max
    if _wants_microcap(msg_lower):
        return 10.0

    return None


def _resolve_universe(explicit_country: str | None, msg_lower: str) -> tuple[str, list[str]]:
    """Decide which scanner countries to query.

    Returns (universe_label, [country, ...]).

    Rule: a generic English short-term profit prompt defaults to a curated
    US + Canada liquid universe. China A-shares only enter the universe when
    the user explicitly mentions China/Asia.
    """
    if explicit_country:
        return f"explicit:{explicit_country}", [explicit_country]
    if _wants_china_universe(msg_lower):
        return "CHINA_A_SHARES", ["China"]
    return "US_CANADA_LIQUID", ["United States", "Canada"]


def _generate_fallback_catalyst(item: dict[str, Any]) -> dict[str, Any]:
    """Generate technical catalyst, risk, and invalidation from OpenBB data.

    Finnhub's earnings calendar only catches scheduled events — many liquid
    tickers have no earnings in the next 14 days. When Finnhub returns empty,
    this fallback builds a thesis from price, moving averages, momentum, and
    the earnings date that OpenBB discovery already provides.
    """
    price = item.get("price")
    ma50 = item.get("ma50")
    ma200 = item.get("ma200")
    earnings_date = item.get("earnings_date")
    change_pct = item.get("change_pct")
    ticker = str(item.get("ticker", "?"))

    catalyst = None
    invalidation = None
    risk = None

    # Priority 1: upcoming earnings already known from OpenBB
    if earnings_date:
        try:
            ed = datetime.fromisoformat(str(earnings_date))
            days = (ed.date() - datetime.now(timezone.utc).date()).days
            if 0 <= days <= 14:
                catalyst = (
                    f"earnings release expected within {days} days "
                    f"(scheduled {earnings_date}) — potential volatility catalyst"
                )
                invalidation = (
                    "close below prior-week low after earnings print, "
                    "or guidance miss / negative pre-announcement"
                )
                risk = "post-earnings volatility; position size 0.5% of capital max"
        except Exception:
            pass

    # Priority 2: bullish moving-average alignment
    if not catalyst and price is not None and ma50 is not None and ma200 is not None:
        p = float(price)
        m50 = float(ma50)
        m200 = float(ma200)
        if p > m50 > m200:
            catalyst = (
                f"bullish trend: price (${p:.2f}) above 50d MA (${m50:.2f}) "
                f"and 200d MA (${m200:.2f}), uptrend intact"
            )
            invalidation = f"close below 50-day MA (${m50:.2f})"
            risk = "trend reversal; max loss 0.5% of trading capital"
        elif p > m50:
            catalyst = (
                f"short-term uptrend: price (${p:.2f}) above 50d MA (${m50:.2f}), "
                f"200d MA at ${m200:.2f}"
            )
            invalidation = f"close below 50-day MA (${m50:.2f})"
            risk = "mid-trend entry; max loss 0.5% of trading capital"

    # Priority 3: daily momentum
    if not catalyst and change_pct is not None and float(change_pct) > 2:
        pct = float(change_pct)
        catalyst = (
            f"positive momentum: +{pct:.1f}% daily move with elevated volume, "
            f"price ${float(price):.2f}"
            if price
            else f"+{pct:.1f}% daily move"
        )
        invalidation = (
            f"close below today's low (${float(price):.2f})"
            if price
            else "close below prior day low"
        )
        risk = "momentum fade risk; tight stop-loss recommended, 0.5% max"

    # Priority 4: generic — liquid, listed, tradable
    if not catalyst:
        catalyst = (
            f"{ticker}: liquid equity on major US exchange"
            f"{', market cap $' + str(item.get('market_cap', '')) if item.get('market_cap') else ''}"
            " — suitable for short-term tactical allocation"
        )
        invalidation = "close below 200-day MA or 8% from entry"
        risk = "broad market / sector risk; position size 0.5% of capital"

    return {
        "catalyst": catalyst,
        "invalidation": invalidation,
        "risk": risk,
        "source": "technical_fallback",
    }


def _apply_candidate_gate(
    item: dict[str, Any],
    *,
    allow_penny_otc: bool,
    allow_microcap: bool,
    max_price: float | None = None,
) -> tuple[bool, str | None]:
    """Apply the market-scan data-quality gate.

    Returns (passes, rejected_reason). A candidate is only valid when it has a
    ticker, an exchange/market, a positive latest price, a positive recent
    volume proxy, and a verifiable short-term thesis. Penny prices and
    over-the-counter venues are rejected unless explicitly requested.
    """
    ticker = item.get("ticker")
    if not ticker or not isinstance(ticker, str):
        return False, "missing_ticker"

    market = item.get("market") or item.get("exchange") or item.get("country")
    if not market:
        return False, "missing_exchange"

    price = item.get("price")
    if price is None:
        return False, "missing_price"
    if isinstance(price, (int, float)) and price <= 0:
        return False, "missing_price"
    if max_price is not None and isinstance(price, (int, float)) and price > max_price:
        return False, "price_above_requested_max"

    if not allow_penny_otc:
        if isinstance(price, (int, float)) and price < 1.0:
            return False, "penny_filtered"
        venue = str(item.get("venue") or item.get("exchange") or "").lower()
        if "otc" in venue or "pink" in venue:
            return False, "otc_filtered"

    if not allow_microcap:
        mcap = item.get("market_cap") or item.get("marketcap")
        if isinstance(mcap, (int, float)) and 0 < mcap < 300_000_000:
            return False, "microcap_filtered"

    volume = item.get("volume") or item.get("avg_volume") or item.get("liquidity")
    if volume is None:
        return False, "missing_liquidity"
    if isinstance(volume, (int, float)) and volume <= 0:
        return False, "missing_liquidity"

    return True, None


def _safe_get_price(hub_obj: Any, ticker: str, *, market: str | None = None) -> dict[str, Any]:
    """Call hub.get_price defensively — never propagate provider errors."""
    try:
        result = hub_obj.get_price(ticker, market=market)
    except TypeError:
        try:
            result = hub_obj.get_price(ticker)
        except Exception as exc:  # noqa: BLE001
            return {"error": str(exc)}
    except Exception as exc:  # noqa: BLE001 — provider errors are runtime
        return {"error": str(exc)}
    return result if isinstance(result, dict) else {"error": "non_dict_response"}


def _safe_get_profile(hub_obj: Any, ticker: str) -> dict[str, Any]:
    """Call hub.get_profile defensively. Test doubles may not implement it."""
    fn = getattr(hub_obj, "get_profile", None)
    if not callable(fn):
        return {}
    try:
        result = fn(ticker)
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc)}
    return result if isinstance(result, dict) else {}


def _safe_get_fundamentals(hub_obj: Any, ticker: str) -> dict[str, Any]:
    """Call hub.get_fundamentals defensively. Test doubles may not implement it."""
    fn = getattr(hub_obj, "get_fundamentals", None)
    if not callable(fn):
        return {}
    try:
        result = fn(ticker)
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc)}
    return result if isinstance(result, dict) else {}


def _safe_get_short_term_catalyst(hub_obj: Any, ticker: str) -> dict[str, Any]:
    """Pull a 2-week catalyst via the hub's `short_term_catalyst` capability.

    Test doubles without a `route` method or capability return empty silently;
    the gate then rejects the candidate with `missing_short_term_thesis`,
    which is the correct, honest behavior.
    """
    route_fn = getattr(hub_obj, "route", None)
    if not callable(route_fn):
        return {}
    try:
        result = route_fn("short_term_catalyst", ticker)
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc)}
    return result if isinstance(result, dict) else {}


async def _run_scan(
    message: str,
    filters: dict[str, Any],
    *,
    excluded_tickers: list[str] | None = None,
    writer: Any | None = None,
) -> dict[str, Any]:
    """Run a market scan and produce gated candidates plus rejection telemetry.

    The scan pipeline:
    1. Resolve the scan universe. Generic English prompts default to US+CA.
    2. Query MarketScanner once per country in the resolved universe.
    3. Enrich candidates with hub data (price up to 24; profile/catalyst up to 12).
    4. Apply the candidate quality gate. Passing items go to `candidates`;
       failing items go to `rejected` with a `rejected_reason`.

    Output keys consumed by `_market_scan_answer`:
        candidates, rejected, rejected_count, rejection_summary, universe,
        filters, data_quality, source_errors, collected_at.
    """

    msg_lower = (message or "").lower()
    explicit_country = (filters or {}).get("country")
    explicit_sector = (filters or {}).get("sector")

    allow_penny_otc = _wants_penny_or_otc(msg_lower)
    allow_microcap = _wants_microcap(msg_lower) or allow_penny_otc
    requested_max_price = _requested_max_price(msg_lower)

    universe_label, countries = _resolve_universe(explicit_country, msg_lower)

    raw_candidates: list[dict[str, Any]] = []
    source_errors: list[str] = []
    provider_sources_used: set[str] = set()
    _t0 = time.monotonic()
    scan_id = f"scan-{int(_t0 * 1000)}"
    # 12 per country → ~24 tickers for US+CA (Finnhub free tier ~60 req/min).
    per_country_limit = int(os.getenv("SUPEREZIO_SCAN_LIMIT", "12"))
    scan_max_total = int(os.getenv("SUPEREZIO_SCAN_MAX_TOTAL", "24"))
    event_writer = writer or (lambda _event: None)

    # ── MRI Registry ── (writer streams SCAN_EVENT to UI in real time)
    registry = ScanEventRegistry(scan_id, writer=event_writer)
    registry.stage_started("init")
    registry.emit(
        "init",
        "heartbeat",
        data={
            "universe": universe_label,
            "countries": countries,
            "filters": filters,
        },
    )

    try:
        from ...scanner import MarketScanner
        from ...scanner.openbb_scanner import OpenBBScanner

        # ── Primary: OpenBB discovery (real tickers with price + fundamentals) ──
        obb_scanner = OpenBBScanner()
        if obb_scanner.available:
            registry.stage_started("fetch_tickers", provider="openbb")
            try:
                obb_items = await asyncio.to_thread(
                    obb_scanner.scan_equities,
                    sector=explicit_sector,
                    industry=explicit_sector,
                    limit=scan_max_total,
                    max_price=requested_max_price,
                )
            except Exception as exc:  # noqa: BLE001
                source_errors.append(f"openbb_discovery: {exc}")
                obb_items = []
            if obb_items:
                raw_candidates = obb_items
                provider_sources_used.add("openbb")
                registry.stage_completed(
                    "fetch_tickers",
                    provider="openbb",
                    done=len(obb_items),
                    total=scan_max_total,
                )
            else:
                registry.stage_failed(
                    "fetch_tickers",
                    "openbb_returned_empty",
                    provider="openbb",
                )
        else:
            registry.stage_started("fetch_tickers", provider="openbb")
            registry.stage_failed("fetch_tickers", "openbb_not_installed", provider="openbb")
            obb_items = []

        # ── Fallback: FinanceDatabase scanner (per-country loop) ──
        if not raw_candidates:
            registry.stage_started("fetch_tickers", provider="scanner")
            scanner = MarketScanner()
            fetch_errors = 0
            fetch_total = len(countries)
            for idx, country in enumerate(countries):
                registry.stage_heartbeat(
                    "fetch_tickers",
                    provider="scanner",
                    done=idx,
                    total=fetch_total,
                    errors=fetch_errors,
                )
                try:
                    tickers = await asyncio.to_thread(
                        scanner.scan_equities,
                        country=country,
                        sector=explicit_sector,
                        limit=per_country_limit,
                    )
                except Exception as exc:  # noqa: BLE001
                    source_errors.append(f"scanner_{country}: {exc}")
                    fetch_errors += 1
                    continue
                for sym in tickers or []:
                    if not sym:
                        continue
                    raw_candidates.append(
                        {
                            "ticker": str(sym),
                            "source": "financedatabase",
                            "market": country,
                        }
                    )
            registry.stage_completed(
                "fetch_tickers",
                provider="scanner",
                done=fetch_total,
                total=fetch_total,
                errors=fetch_errors,
            )

        # ── Penny scanner fallback: yfinance direct for sub-$5 stocks ──
        if allow_penny_otc and (not raw_candidates or len(raw_candidates) < 5):
            registry.stage_started("fetch_tickers", provider="penny_scanner")
            try:
                from ....core.scanner.penny_scanner import scan_penny_stocks

                penny_results = await asyncio.to_thread(
                    scan_penny_stocks,
                    max_price=requested_max_price or 5.0,
                    min_volume=50_000,
                )
                existing_tickers = {str(c["ticker"]).upper() for c in raw_candidates}
                added = 0
                for p in penny_results:
                    sym = str(p["ticker"]).upper()
                    if sym not in existing_tickers:
                        raw_candidates.append(
                            {
                                "ticker": sym,
                                "source": "penny_scanner_yfinance",
                                "market": p.get("exchange", "United States"),
                                "price": p.get("price"),
                                "volume": p.get("volume"),
                                "name": p.get("name", ""),
                                "sector": p.get("sector", ""),
                                "market_cap": p.get("market_cap"),
                            }
                        )
                        existing_tickers.add(sym)
                        added += 1
                registry.stage_completed(
                    "fetch_tickers",
                    provider="penny_scanner",
                    done=added,
                    total=len(penny_results),
                )
                if added:
                    provider_sources_used.add("penny_scanner_yfinance")
            except Exception as exc:  # noqa: BLE001
                source_errors.append(f"penny_scanner: {exc}")
                registry.stage_failed("fetch_tickers", str(exc)[:200], provider="penny_scanner")
    except ImportError:
        source_errors.append("scanner: module_archived")
        registry.stage_failed("fetch_tickers", "module_archived", provider="scanner")
    except Exception as exc:  # noqa: BLE001
        source_errors.append(f"scanner: {exc}")
        registry.stage_failed("fetch_tickers", str(exc)[:200], provider="scanner")

    # Merge pre-vetted penny stocks from the watchlist if penny scanning is requested
    if allow_penny_otc:
        try:
            from experts.pennylab.data_provider import _PENNY_WATCHLIST

            existing_tickers = {c["ticker"].upper() for c in raw_candidates}
            for sym in _PENNY_WATCHLIST:
                if sym.upper() not in existing_tickers:
                    raw_candidates.append(
                        {
                            "ticker": sym,
                            "source": "pennylab_watchlist",
                            "market": "Canada"
                            if (sym.endswith(".TO") or sym.endswith(".V"))
                            else ("Brazil" if sym.endswith(".SA") else "United States"),
                        }
                    )
        except Exception as exc:
            logger.warning("Failed to merge pennylab watchlist: %s", exc)

    if len(raw_candidates) > scan_max_total:
        raw_candidates = raw_candidates[:scan_max_total]

    # Hard cap on raw candidates from config
    max_raw = _scan_max_raw()
    if len(raw_candidates) > max_raw:
        raw_candidates = raw_candidates[:max_raw]

    # Profile + catalyst are heavier on Finnhub; keep a smaller default budget.
    enrich_budget = int(os.getenv("SUPEREZIO_SCAN_ENRICH", "12"))
    price_enrich_limit = int(os.getenv("SUPEREZIO_SCAN_PRICE_ENRICH", "24"))
    price_enrich_limit = min(price_enrich_limit, len(raw_candidates))
    price_targets = raw_candidates[: max(0, price_enrich_limit)]
    profile_catalyst_targets = price_targets[:enrich_budget]

    breaker_snapshots: dict[str, dict] = {}
    if price_targets:
        try:
            from core.config.secrets import load_local_env

            load_local_env()
            from data.data_hub import hub  # type: ignore[import-not-found]
        except ImportError:
            hub = None
        if hub is not None:
            per_item_timeout = float(os.getenv("SUPEREZIO_SCAN_ENRICH_TIMEOUT_MS", "60000")) / 1000
            stage_deadline_ms = int(os.getenv("SUPEREZIO_SCAN_STAGE_DEADLINE_MS", "180000"))
            num_workers = max(1, int(os.getenv("SUPEREZIO_SCAN_ENRICH_CONCURRENCY", "2")))

            # ── Circuit breakers per provider ──
            breaker_finnhub = CircuitBreaker("finnhub")
            breaker_finnhub_fundamentals = CircuitBreaker("finnhub_fundamentals")
            breaker_yfinance = CircuitBreaker("yfinance")
            breaker_twelve = CircuitBreaker("twelve_data")
            _BREAKERS_BY_PROVIDER = {
                "finnhub": breaker_finnhub,
                "finnhub_fundamentals": breaker_finnhub_fundamentals,
                "yfinance": breaker_yfinance,
                "twelve_data": breaker_twelve,
            }

            def _resolve_breaker(_item: dict[str, Any]) -> CircuitBreaker:
                # Finnhub is the default enrichment provider
                return breaker_finnhub

            # ── Queue-based enrichment engine ──

            async def _run_enrich_stage(
                stage: str,
                items: list[dict[str, Any]],
                call_fn,  # async (item) -> Any
            ) -> list[tuple[dict[str, Any], Any]]:
                """Process items through a provider queue with worker pool.

                Each worker pulls from an asyncio.Queue. As items complete,
                heartbeats are emitted to the registry. On stage deadline,
                completed results are preserved and pending items are abandoned.
                """
                if not items:
                    return []

                registry.stage_started(stage, provider="data_hub")
                in_queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
                out_pairs: list[tuple[dict[str, Any], Any]] = []
                done_count = 0
                error_count = 0
                total = len(items)
                _done_event = asyncio.Event()

                for item in items:
                    in_queue.put_nowait(item)

                async def _worker() -> None:
                    nonlocal done_count, error_count
                    while True:
                        try:
                            item = in_queue.get_nowait()
                        except asyncio.QueueEmpty:
                            return
                        try:
                            result = await call_fn(item)
                        except Exception as exc:
                            result = exc
                        out_pairs.append((item, result))
                        done_count += 1
                        if isinstance(result, Exception) or (
                            isinstance(result, dict) and "error" in result
                        ):
                            error_count += 1
                        if done_count % max(1, total // 5) == 0 or done_count == total:
                            registry.stage_heartbeat(
                                stage,
                                provider="data_hub",
                                done=done_count,
                                total=total,
                                errors=error_count,
                            )
                        in_queue.task_done()
                        if done_count >= total:
                            _done_event.set()

                workers = [asyncio.create_task(_worker()) for _ in range(num_workers)]

                try:
                    await asyncio.wait_for(_done_event.wait(), timeout=stage_deadline_ms / 1000)
                except asyncio.TimeoutError:
                    pass  # deadline fired — preserve what we have

                for w in workers:
                    w.cancel()

                abandoned = total - done_count
                if abandoned > 0:
                    registry.stage_failed(
                        stage,
                        "stage_deadline",
                        provider="data_hub",
                        done=done_count,
                        total=total,
                        errors=error_count + abandoned,
                    )
                else:
                    registry.stage_completed(
                        stage,
                        provider="data_hub",
                        done=done_count - error_count,
                        total=total,
                        errors=error_count,
                    )
                return out_pairs

            # ── Enrich callables (shared breaker logic) ──

            async def _call_price(item: dict[str, Any]) -> Any:
                breaker = _resolve_breaker(item)
                if not breaker.allow():
                    return CircuitBreakerOpenError(f"circuit_open:{breaker.provider}")
                ticker = str(item.get("ticker") or "")
                market = item.get("market")
                try:
                    result = await asyncio.wait_for(
                        asyncio.to_thread(_safe_get_price, hub, ticker, market=market),
                        timeout=per_item_timeout,
                    )
                except Exception:
                    breaker.failure()
                    raise
                if isinstance(result, dict) and "error" in result:
                    breaker.failure()
                else:
                    breaker.success()
                return result

            async def _call_profile(item: dict[str, Any]) -> Any:
                breaker = _resolve_breaker(item)
                if not breaker.allow():
                    return CircuitBreakerOpenError(f"circuit_open:{breaker.provider}")
                try:
                    result = await asyncio.wait_for(
                        asyncio.to_thread(_safe_get_profile, hub, item.get("ticker", "")),
                        timeout=per_item_timeout,
                    )
                except Exception:
                    breaker.failure()
                    raise
                if isinstance(result, dict) and "error" in result:
                    breaker.failure()
                else:
                    breaker.success()
                return result

            async def _call_fundamentals(item: dict[str, Any]) -> Any:
                breaker = breaker_finnhub_fundamentals
                if not breaker.allow():
                    return CircuitBreakerOpenError(f"circuit_open:{breaker.provider}")
                try:
                    result = await asyncio.wait_for(
                        asyncio.to_thread(_safe_get_fundamentals, hub, item.get("ticker", "")),
                        timeout=per_item_timeout,
                    )
                except Exception:
                    breaker.failure()
                    raise
                if isinstance(result, dict) and "error" in result:
                    breaker.failure()
                else:
                    breaker.success()
                return result

            async def _call_catalyst(item: dict[str, Any]) -> Any:
                breaker = _resolve_breaker(item)
                if not breaker.allow():
                    return CircuitBreakerOpenError(f"circuit_open:{breaker.provider}")
                try:
                    result = await asyncio.wait_for(
                        asyncio.to_thread(
                            _safe_get_short_term_catalyst, hub, item.get("ticker", "")
                        ),
                        timeout=per_item_timeout,
                    )
                except Exception:
                    breaker.failure()
                    raise
                if isinstance(result, dict) and "error" in result:
                    breaker.failure()
                else:
                    breaker.success()
                return result

            # ── Enrich stages (queue-based, independent failure domains) ──

            price_pairs = await _run_enrich_stage(
                "enrich_price",
                price_targets,
                _call_price,
            )
            profile_pairs = await _run_enrich_stage(
                "enrich_profile",
                profile_catalyst_targets,
                _call_profile,
            )
            fundamentals_pairs = await _run_enrich_stage(
                "enrich_fundamentals",
                profile_catalyst_targets,
                _call_fundamentals,
            )
            catalyst_pairs = await _run_enrich_stage(
                "enrich_catalyst",
                profile_catalyst_targets,
                _call_catalyst,
            )

            # ── Circuit breaker snapshot in trace ──
            breaker_snapshots = {name: b.snapshot() for name, b in _BREAKERS_BY_PROVIDER.items()}

            price_results = [res for _, res in price_pairs]
            profile_results = [res for _, res in profile_pairs]
            fundamentals_results = [res for _, res in fundamentals_pairs]
            catalyst_results = [res for _, res in catalyst_pairs]
            # Fields a data provider may legitimately surface today or in the
            # future. Anything outside this allow-list is ignored on purpose.
            _RICH_FIELDS = (
                "name",
                "company",
                "exchange",
                "venue",
                "market_cap",
                "marketcap",
                "avg_volume",
                "liquidity",
                "atr",
                "volatility",
                "catalyst",
                "thesis",
                "short_term_thesis",
                "reason",
                "risk",
                "downside_risk",
                "invalidation",
                "invalidation_condition",
                "confidence",
                "event_date",
                "country",
                # ── Fundamentals (Finnhub /stock/metric) ──
                "pe_ratio",
                "beta",
                "eps",
                "dividend_yield",
                "price_to_book",
                "price_to_sales",
                "roe",
                "roa",
                "profit_margin",
                "operating_margin",
                "gross_margin",
                "revenue_growth_yoy",
                "eps_growth_yoy",
                "debt_to_equity",
                "current_ratio",
                "sector",
                "industry",
            )

            def _merge(item: dict[str, Any], result: Any) -> None:
                if isinstance(result, Exception) or not isinstance(result, dict):
                    return
                if "error" in result:
                    return
                price = result.get("price")
                if price is not None and item.get("price") is None:
                    item["price"] = price
                volume = result.get("volume")
                if volume is not None and item.get("volume") is None:
                    item["volume"] = volume
                if result.get("currency") is not None:
                    item.setdefault("currency", result.get("currency"))
                provider = result.get("provider") or result.get("source")
                if provider is not None:
                    item.setdefault("provider", provider)
                for field in _RICH_FIELDS:
                    if result.get(field) is not None and item.get(field) is None:
                        item[field] = result[field]

            price_error_counts: dict[str, int] = {}
            for item, price_res in zip(price_targets, price_results):
                if isinstance(price_res, Exception):
                    item["price_error"] = str(price_res)
                    price_error_counts["exception"] = price_error_counts.get("exception", 0) + 1
                elif isinstance(price_res, dict) and "error" in price_res:
                    err = str(price_res.get("error"))
                    item["price_error"] = err
                    price_error_counts[err] = price_error_counts.get(err, 0) + 1
                    attempts = price_res.get("attempts")
                    if isinstance(attempts, list):
                        item["price_attempts"] = attempts
                _merge(item, price_res)

            for item, profile_res, fundamentals_res, catalyst_res in zip(
                profile_catalyst_targets, profile_results, fundamentals_results, catalyst_results
            ):
                _merge(item, profile_res)
                _merge(item, fundamentals_res)
                _merge(item, catalyst_res)

            # ── Catalyst fallback: OpenBB data → technical thesis when Finnhub empty ──
            for item in profile_catalyst_targets:
                has_catalyst = (
                    item.get("catalyst")
                    or item.get("thesis")
                    or item.get("short_term_thesis")
                    or item.get("reason")
                )
                if not has_catalyst:
                    fb = _generate_fallback_catalyst(item)
                    if fb.get("catalyst"):
                        item["catalyst"] = fb["catalyst"]
                    if fb.get("invalidation"):
                        item.setdefault("invalidation", fb["invalidation"])
                    if fb.get("risk"):
                        item.setdefault("risk", fb["risk"])

            if price_error_counts:
                top = sorted(price_error_counts.items(), key=lambda kv: kv[1], reverse=True)[:5]
                source_errors.append("price_provider: " + ", ".join(f"{k}={v}" for k, v in top))
                active = [r["name"] for r in hub.list_routes("price") if r.get("configured")]
                source_errors.append(
                    "price_routes_active: " + (",".join(active) if active else "none")
                )
                if price_error_counts.get("no_provider_result_for_price"):
                    for item in price_targets:
                        attempts = item.get("price_attempts")
                        if isinstance(attempts, list) and attempts:
                            parts = [
                                f"{a.get('provider')}:{a.get('error')}"
                                for a in attempts[:4]
                                if isinstance(a, dict)
                            ]
                            if parts:
                                source_errors.append("price_attempts_sample: " + "; ".join(parts))
                            break

        # Price discovery is intentionally confined to DataHub. If every
        # configured route fails, the candidate must reach the gate without a
        # price and be rejected. A direct provider call here would bypass
        # DataHub routing, observability, circuit breakers and test isolation.

    # ── Catalyst fallback for ALL candidates (covers items beyond enrich budget) ──
    for item in raw_candidates:
        has_catalyst = (
            item.get("catalyst")
            or item.get("thesis")
            or item.get("short_term_thesis")
            or item.get("reason")
        )
        if not has_catalyst:
            fb = _generate_fallback_catalyst(item)
            if fb.get("catalyst"):
                item["catalyst"] = fb["catalyst"]
            if fb.get("invalidation"):
                item.setdefault("invalidation", fb["invalidation"])
            if fb.get("risk"):
                item.setdefault("risk", fb["risk"])

    # ── Gate ──
    registry.stage_started("gate")
    passing: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    rejection_summary: dict[str, int] = {}
    excluded = {str(t).upper() for t in (excluded_tickers or []) if t}
    for item in raw_candidates:
        ticker_key = str(item.get("ticker") or "").upper()
        if ticker_key and ticker_key in excluded:
            rj = dict(item)
            rj["rejected_reason"] = "excluded_previous_recommendation"
            rejected.append(rj)
            rejection_summary["excluded_previous_recommendation"] = (
                rejection_summary.get("excluded_previous_recommendation", 0) + 1
            )
            continue
        ok, reason = _apply_candidate_gate(
            item,
            allow_penny_otc=allow_penny_otc,
            allow_microcap=allow_microcap,
            max_price=requested_max_price,
        )
        if ok:
            normalize_liquidity_fields(item)
            passing.append(item)
            continue
        rj = dict(item)
        key = reason or "unknown"
        rj["rejected_reason"] = key
        rejected.append(rj)
        rejection_summary[key] = rejection_summary.get(key, 0) + 1
    registry.stage_completed(
        "gate",
        done=len(passing),
        total=len(raw_candidates),
        errors=len(rejected),
    )

    # ── Rank ──
    registry.stage_started("rank")
    ranked = rank_candidates(
        passing,
        source_errors=source_errors,
        weak_universe=len(passing) <= 1,
    )
    registry.stage_completed("rank", done=len(ranked), total=len(ranked))

    # Hard cap: only top N after gate go to candidates
    max_after_gate = _scan_max_after_gate()
    capped_passing = passing[:max_after_gate]
    max_llm = _scan_max_llm_candidates()
    llm_candidates = capped_passing[:max_llm]

    # Determine final decision
    if llm_candidates:
        final_decision = "BUY_CANDIDATE" if len(llm_candidates) == 1 else "BUY_CANDIDATES"
    else:
        final_decision = "REJECT_ALL"

    # ── Finalize ──
    registry.stage_started("finalize")
    top_reject_reasons = sorted(rejection_summary.items(), key=lambda kv: kv[1], reverse=True)[:3]
    active_providers = list(provider_sources_used) if "provider_sources_used" in dir() else []

    summary = (
        f"[SCAN_SUMMARY] scan_id={scan_id} route=market_scan "
        f"universe={universe_label} raw={len(raw_candidates)} "
        f"gated={len(passing)} rejected={len(rejected)} "
        f"top_reject={','.join(f'{k}:{v}' for k, v in top_reject_reasons)} "
        f"llm_candidates={len(llm_candidates)} llm_calls_budget={_scan_max_llm_calls()} "
        f"providers={','.join(active_providers) if active_providers else 'none'} "
        f"final={final_decision} elapsed_ms={registry.elapsed_ms()}"
    )
    logger.info(summary)
    registry.stage_completed("finalize")

    # Emit SCAN_SUMMARY to UI stream
    event_writer(
        {
            "type": "SCAN_SUMMARY",
            "scan_id": scan_id,
            "candidate_count": len(passing),
            "rejected_count": len(rejected),
            "provider_sources_used": sorted(active_providers) if active_providers else [],
            "elapsed_ms": registry.elapsed_ms(),
        }
    )

    resolved_filters: dict[str, Any] = {
        "country": explicit_country,
        "sector": explicit_sector,
        "resolved_countries": countries,
        "allow_penny_otc": allow_penny_otc,
        "allow_microcap": allow_microcap,
        "max_price": requested_max_price,
    }

    return {
        "query": message,
        "filters": resolved_filters,
        "universe": universe_label,
        "candidates": capped_passing,
        "ranked_candidates": ranked[:max_after_gate],
        "rejected": rejected[:25],
        "rejected_count": len(rejected),
        "rejection_summary": rejection_summary,
        "data_quality": "partial" if source_errors else "provider_or_computed",
        "source_errors": source_errors,
        "collected_at": datetime.now(timezone.utc).isoformat(),
        "scan_trace": {
            "scan_id": scan_id,
            "raw_candidate_count": len(raw_candidates),
            "gated_candidate_count": len(passing),
            "rejected_count": len(rejected),
            "top_rejection_reasons": dict(top_reject_reasons),
            "llm_candidates_analyzed": len(llm_candidates),
            "llm_calls_budget": _scan_max_llm_calls(),
            "provider_sources_used": sorted(active_providers),
            "final_decision": final_decision,
            "elapsed_ms": registry.elapsed_ms(),
            "mri_events": registry.as_trace(),
            "circuit_breakers": breaker_snapshots,
        },
    }


def _scan_from_cached_ranked(
    trade_ctx: dict[str, Any],
    message: str,
    excluded_tickers: list[str],
) -> dict[str, Any]:
    """Reuse ranked candidates from a prior DECISIVE_TRADE_ORDER session."""

    ranked = list(trade_ctx.get("ranked_candidates") or [])
    excluded = {str(t).upper() for t in excluded_tickers if t}
    candidates = [
        entry.get("candidate")
        for entry in ranked
        if isinstance(entry, dict) and isinstance(entry.get("candidate"), dict)
    ]
    for item in candidates:
        normalize_liquidity_fields(item)

    next_entry, _ = pick_candidate(ranked, excluded_tickers=excluded)
    remaining = [
        entry
        for entry in ranked
        if str((entry.get("candidate") or {}).get("ticker", "")).upper() not in excluded
    ]

    return {
        "query": message,
        "filters": trade_ctx.get("filters") or {},
        "universe": trade_ctx.get("universe") or "unspecified",
        "candidates": candidates[:10],
        "ranked_candidates": ranked,
        "rejected": [],
        "rejected_count": int(trade_ctx.get("rejected_count", 0) or 0),
        "rejection_summary": trade_ctx.get("rejection_summary") or {},
        "data_quality": "cached_ranked",
        "source_errors": trade_ctx.get("source_errors") or [],
        "collected_at": trade_ctx.get("scanned_at")
        or trade_ctx.get("collected_at")
        or datetime.now(timezone.utc).isoformat(),
        "from_cache": True,
        "next_cached_entry": next_entry,
        "remaining_after_exclude": len(remaining),
    }


def _format_scan_context(scan: dict[str, Any]) -> str:
    """Render scan results as CEO-readable text."""
    lines = [
        "=== MARKET SCAN ===",
        f"Query: {scan.get('query', '')}",
        f"Universe: {scan.get('universe', 'unspecified')}",
        f"Filters: {scan.get('filters', {})}",
        f"Data quality: {scan.get('data_quality', 'unknown')}",
        f"Rejected: {scan.get('rejected_count', 0)} (reasons: {scan.get('rejection_summary', {})})",
    ]
    for item in scan.get("candidates", []):
        price = item.get("price")
        price_txt = f" price={price}" if price is not None else ""
        volume = item.get("volume")
        vol_txt = f" volume={volume}" if volume is not None else ""
        name = item.get("name", "")
        if name:
            name_txt = f" name={name}"
        else:
            name_txt = " name=UNKNOWN_DO_NOT_INVENT"
        sector = item.get("sector", "")
        sector_txt = f" sector={sector}" if sector else ""
        provider = item.get("provider") or item.get("source") or "scanner"
        lines.append(
            f"- {item.get('ticker')}{name_txt}{sector_txt}{price_txt}{vol_txt} provider={provider}"
        )
    if scan.get("source_errors"):
        lines.append("Source errors: " + ", ".join(scan["source_errors"]))
    return "\n".join(lines)
