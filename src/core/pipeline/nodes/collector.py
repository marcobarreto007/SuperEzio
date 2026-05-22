"""Data collection node — delegates to ProfessionalCollector or SubprocessCollector."""

from __future__ import annotations

import asyncio
import os
import re
import time
from typing import Any

from langgraph.config import get_stream_writer

from ..trade_order import normalize_liquidity_fields, pick_candidate, rank_candidates


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

        if intent == "another_trade_recommendation" and trade_ctx.get("ranked_candidates"):
            scan = _scan_from_cached_ranked(trade_ctx, state.get("message", ""), excluded)
        else:
            scan = await _run_scan(
                state.get("message", ""),
                state.get("filters", {}),
                excluded_tickers=excluded,
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
        # and CEO have per-ticker technicals/risk/sentiment to work with.
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

    timeout_s = int(os.getenv("SUPEREZIO_DATA_TIMEOUT", "60"))
    t0 = time.time()

    collector = ProfessionalCollector()
    try:
        data = await collector.collect(ticker, overall_timeout=timeout_s)
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

    timeout_s = int(os.getenv("SUPEREZIO_DATA_TIMEOUT", "60"))
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
)

_MICROCAP_HINTS = (
    "microcap",
    "micro cap",
    "micro-cap",
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


def _resolve_universe(
    explicit_country: str | None, msg_lower: str
) -> tuple[str, list[str]]:
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


def _apply_candidate_gate(
    item: dict[str, Any],
    *,
    allow_penny_otc: bool,
    allow_microcap: bool,
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

    market = (
        item.get("market")
        or item.get("exchange")
        or item.get("country")
    )
    if not market:
        return False, "missing_exchange"

    price = item.get("price")
    if price is None:
        return False, "missing_price"
    if isinstance(price, (int, float)) and price <= 0:
        return False, "missing_price"

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

    volume = (
        item.get("volume")
        or item.get("avg_volume")
        or item.get("liquidity")
    )
    if volume is None:
        return False, "missing_liquidity"
    if isinstance(volume, (int, float)) and volume <= 0:
        return False, "missing_liquidity"

    catalyst = (
        item.get("catalyst")
        or item.get("thesis")
        or item.get("short_term_thesis")
        or item.get("reason")
    )
    if not catalyst:
        return False, "missing_short_term_thesis"

    return True, None


def _safe_get_price(
    hub_obj: Any, ticker: str, *, market: str | None = None
) -> dict[str, Any]:
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
    from datetime import datetime, timezone

    msg_lower = (message or "").lower()
    explicit_country = (filters or {}).get("country")
    explicit_sector = (filters or {}).get("sector")

    allow_penny_otc = _wants_penny_or_otc(msg_lower)
    allow_microcap = _wants_microcap(msg_lower) or allow_penny_otc

    universe_label, countries = _resolve_universe(explicit_country, msg_lower)

    raw_candidates: list[dict[str, Any]] = []
    source_errors: list[str] = []
    # 12 per country → ~24 tickers for US+CA (Finnhub free tier ~60 req/min).
    per_country_limit = int(os.getenv("SUPEREZIO_SCAN_LIMIT", "12"))
    scan_max_total = int(os.getenv("SUPEREZIO_SCAN_MAX_TOTAL", "24"))

    try:
        from ...scanner import MarketScanner

        scanner = MarketScanner()
        for country in countries:
            try:
                tickers = await asyncio.to_thread(
                    scanner.scan_equities,
                    country=country,
                    sector=explicit_sector,
                    limit=per_country_limit,
                )
            except Exception as exc:  # noqa: BLE001
                source_errors.append(f"scanner_{country}: {exc}")
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
    except ImportError:
        source_errors.append("scanner: module_archived")
    except Exception as exc:  # noqa: BLE001
        source_errors.append(f"scanner: {exc}")

    if len(raw_candidates) > scan_max_total:
        raw_candidates = raw_candidates[:scan_max_total]

    # Profile + catalyst are heavier on Finnhub; keep a smaller default budget.
    enrich_budget = int(os.getenv("SUPEREZIO_SCAN_ENRICH", "12"))
    price_enrich_limit = int(os.getenv("SUPEREZIO_SCAN_PRICE_ENRICH", "24"))
    price_enrich_limit = min(price_enrich_limit, len(raw_candidates))
    price_targets = raw_candidates[: max(0, price_enrich_limit)]
    profile_catalyst_targets = price_targets[:enrich_budget]

    if price_targets:
        try:
            from core.config.secrets import load_local_env

            load_local_env()
            from data.data_hub import hub  # type: ignore[import-not-found]
        except ImportError:
            hub = None
        if hub is not None:
            if not os.getenv("FINNHUB_API_KEY"):
                source_errors.append("finnhub: FINNHUB_API_KEY not configured")

            enrich_concurrency = max(
                1, int(os.getenv("SUPEREZIO_SCAN_ENRICH_CONCURRENCY", "2"))
            )
            sem = asyncio.Semaphore(enrich_concurrency)

            async def _enrich_price(item: dict[str, Any]) -> tuple[dict[str, Any], Any]:
                async with sem:
                    ticker = str(item.get("ticker") or "")
                    market = item.get("market")
                    return item, await asyncio.wait_for(
                        asyncio.to_thread(
                            _safe_get_price, hub, ticker, market=market
                        ),
                        timeout=12,
                    )

            async def _enrich_profile(item: dict[str, Any]) -> tuple[dict[str, Any], Any]:
                async with sem:
                    return item, await asyncio.wait_for(
                        asyncio.to_thread(
                            _safe_get_profile, hub, item.get("ticker", "")
                        ),
                        timeout=12,
                    )

            async def _enrich_catalyst(item: dict[str, Any]) -> tuple[dict[str, Any], Any]:
                async with sem:
                    return item, await asyncio.wait_for(
                        asyncio.to_thread(
                            _safe_get_short_term_catalyst, hub, item.get("ticker", "")
                        ),
                        timeout=12,
                    )

            price_pairs = await asyncio.gather(
                *[_enrich_price(item) for item in price_targets]
            )
            profile_pairs = await asyncio.gather(
                *[_enrich_profile(item) for item in profile_catalyst_targets]
            )
            catalyst_pairs = await asyncio.gather(
                *[_enrich_catalyst(item) for item in profile_catalyst_targets]
            )

            price_results = [res for _, res in price_pairs]
            profile_results = [res for _, res in profile_pairs]
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
                    price_error_counts["exception"] = (
                        price_error_counts.get("exception", 0) + 1
                    )
                elif isinstance(price_res, dict) and "error" in price_res:
                    err = str(price_res.get("error"))
                    item["price_error"] = err
                    price_error_counts[err] = price_error_counts.get(err, 0) + 1
                    attempts = price_res.get("attempts")
                    if isinstance(attempts, list):
                        item["price_attempts"] = attempts
                _merge(item, price_res)

            for item, profile_res, catalyst_res in zip(
                profile_catalyst_targets, profile_results, catalyst_results
            ):
                _merge(item, profile_res)
                _merge(item, catalyst_res)

            if price_error_counts:
                top = sorted(
                    price_error_counts.items(), key=lambda kv: kv[1], reverse=True
                )[:5]
                source_errors.append(
                    "price_provider: " + ", ".join(f"{k}={v}" for k, v in top)
                )
                active = [
                    r["name"]
                    for r in hub.list_routes("price")
                    if r.get("configured")
                ]
                source_errors.append(
                    "price_routes_active: "
                    + (",".join(active) if active else "none")
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
                                source_errors.append(
                                    "price_attempts_sample: " + "; ".join(parts)
                                )
                            break

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

    ranked = rank_candidates(
        passing,
        source_errors=source_errors,
        weak_universe=len(passing) <= 1,
    )

    resolved_filters: dict[str, Any] = {
        "country": explicit_country,
        "sector": explicit_sector,
        "resolved_countries": countries,
        "allow_penny_otc": allow_penny_otc,
        "allow_microcap": allow_microcap,
    }

    return {
        "query": message,
        "filters": resolved_filters,
        "universe": universe_label,
        "candidates": passing[:10],
        "ranked_candidates": ranked,
        "rejected": rejected[:25],
        "rejected_count": len(rejected),
        "rejection_summary": rejection_summary,
        "data_quality": "partial" if source_errors else "provider_or_computed",
        "source_errors": source_errors,
        "collected_at": datetime.now(timezone.utc).isoformat(),
    }


def _scan_from_cached_ranked(
    trade_ctx: dict[str, Any],
    message: str,
    excluded_tickers: list[str],
) -> dict[str, Any]:
    """Reuse ranked candidates from a prior DECISIVE_TRADE_ORDER session."""
    from datetime import datetime, timezone

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
        "rejected_count": 0,
        "rejection_summary": {},
        "data_quality": "cached_ranked",
        "source_errors": [],
        "collected_at": datetime.now(timezone.utc).isoformat(),
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
        f"Rejected: {scan.get('rejected_count', 0)} (reasons: "
        f"{scan.get('rejection_summary', {})})",
    ]
    for item in scan.get("candidates", []):
        price = item.get("price")
        price_txt = f" price={price}" if price is not None else ""
        volume = item.get("volume")
        vol_txt = f" volume={volume}" if volume is not None else ""
        lines.append(
            f"- {item.get('ticker')}{price_txt}{vol_txt} "
            f"provider={item.get('provider', item.get('source', 'unknown'))}"
        )
    if scan.get("source_errors"):
        lines.append("Source errors: " + ", ".join(scan["source_errors"]))
    return "\n".join(lines)
