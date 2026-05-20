"""Data collection node — delegates to ProfessionalCollector or SubprocessCollector."""

from __future__ import annotations

import asyncio
import os
import time
from typing import Any

from langgraph.config import get_stream_writer


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
            data, data_context = await _collect_legacy(ticker, writer, run_id)

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
        scan = await _run_scan(state.get("message", ""), state.get("filters", {}))
        scan_ctx = _format_scan_context(scan)
        writer(
            {
                "type": "DATA_COLLECTED",
                "ticker": "",
                "quality": scan.get("data_quality", "partial"),
                "source_errors": scan.get("source_errors", []),
                "candidates": len(scan.get("candidates", [])),
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
        return {"scan": scan, "data_context": scan_ctx}

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
# Legacy collector (subprocess)
# ---------------------------------------------------------------------------


async def _collect_legacy(ticker: str, writer, run_id: str) -> tuple[dict[str, Any], str]:
    """Fallback: use SubprocessDataCollector."""
    from ...data_collector import DataCollector
    from ...data_collector.subprocess_collector import SubprocessDataCollector
    from ...paths import PROJECT_ROOT

    timeout_s = int(os.getenv("SUPEREZIO_DATA_TIMEOUT", "60"))
    collector = SubprocessDataCollector(project_root=PROJECT_ROOT)
    data = await asyncio.to_thread(collector.collect_all, ticker, timeout_s)
    data_context = DataCollector.format_context(data)
    return data, data_context


# ---------------------------------------------------------------------------
# Market scan
# ---------------------------------------------------------------------------


async def _run_scan(message: str, filters: dict[str, Any]) -> dict[str, Any]:
    """Run a market scan and enrich candidates with price data."""
    from datetime import datetime, timezone

    candidates: list[dict[str, Any]] = []
    source_errors: list[str] = []

    try:
        from ...scanner import MarketScanner

        scanner = MarketScanner()
        raw = await asyncio.to_thread(
            scanner.scan_equities,
            country=filters.get("country"),
            sector=filters.get("sector"),
            limit=int(os.getenv("SUPEREZIO_SCAN_LIMIT", "30")),
        )
        candidates = [{"ticker": str(item), "source": "financedatabase"} for item in raw]
    except ImportError:
        source_errors.append("scanner: module_archived")
    except Exception as exc:
        source_errors.append(f"scanner: {exc}")

    # Enrich with prices
    if candidates:
        from data.data_hub import hub

        enriched: list[dict[str, Any]] = []
        for item in candidates[:12]:
            ticker = item.get("ticker", "")
            try:
                quote = await asyncio.wait_for(asyncio.to_thread(hub.get_price, ticker), timeout=6)
                if isinstance(quote, dict):
                    item.update(
                        {
                            "price": quote.get("price"),
                            "currency": quote.get("currency"),
                            "provider": quote.get("provider"),
                        }
                    )
            except Exception as exc:
                item["price_error"] = str(exc)
            enriched.append(item)
        candidates = enriched

    return {
        "query": message,
        "filters": filters,
        "candidates": candidates[:10],
        "data_quality": "partial" if source_errors else "provider_or_computed",
        "source_errors": source_errors,
        "collected_at": datetime.now(timezone.utc).isoformat(),
    }


def _format_scan_context(scan: dict[str, Any]) -> str:
    """Render scan results as CEO-readable text."""
    lines = [
        "=== MARKET SCAN ===",
        f"Query: {scan.get('query', '')}",
        f"Filters: {scan.get('filters', {})}",
        f"Data quality: {scan.get('data_quality', 'unknown')}",
    ]
    for item in scan.get("candidates", []):
        price = item.get("price")
        price_txt = f" price={price}" if price is not None else ""
        lines.append(
            f"- {item.get('ticker')}{price_txt} "
            f"provider={item.get('provider', item.get('source', 'unknown'))}"
        )
    if scan.get("source_errors"):
        lines.append("Source errors: " + ", ".join(scan["source_errors"]))
    return "\n".join(lines)
