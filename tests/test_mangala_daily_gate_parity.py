"""Gate-parity regression: Mangala daily top-5 vs the live DECISIVE gates.

Ticket T2 — the 2026-08-22 live scan rejected 24 tickers while the daily
Mangala scan (data/mangala_daily.json, 2026-08-23T01:10 UTC) approved 5.
These tests pin the verdict with the REAL (price, volume) pairs from that
daily scan:

  1. The liquidity gate passes all 5 real candidates in their band
     (penny <$5: 50K shares / $100K daily dollar; KODK non-penny: 500K / $10M).
  2. Raw daily entries (discovery only, no thesis/provenance) FAIL CLOSED —
     the daily scan is a ranking layer, not a trade gate.
  3. The same 5 candidates PASS the full gate when healthily enriched
     (catalyst + risk + invalidation + provenance) — healthy data approves
     exactly these candidates.
  4. The live scan's own computed-thesis fallback is actionable for them.
  5. Generic provider catalyst text still fails closed (missing_catalyst).

Offline and deterministic — values are embedded from the real artifact.
"""

from __future__ import annotations

from src.core.pipeline.nodes.collector import (
    _apply_candidate_gate,
    _generate_fallback_catalyst,
)
from src.core.pipeline.trade_order import (
    _is_actionable_evidence,
    evaluate_quality_gates,
    normalize_liquidity_fields,
)

# Real values from data/mangala_daily.json (scan of 2026-08-22, saved 01:10 UTC).
DAILY_TOP5 = [
    ("NIO", 4.63, 21_891_270),
    ("TLRY", 4.84, 4_248_618),
    ("SNDL", 1.37, 1_582_406),
    ("KODK", 9.84, 1_380_306),
    ("PLUG", 2.27, 56_420_354),
]


def _raw_discovery_entry(ticker: str, price: float, volume: int) -> dict:
    """Candidate as the live scan builds it after discovery (no thesis yet)."""
    return {
        "ticker": ticker,
        "name": ticker,
        "market": "United States",
        "source": "financedatabase",
        "price": price,
        "volume": volume,
        "provenance": {
            "ticker": {"source": "financedatabase"},
            "market": {"source": "financedatabase"},
            "price": {"source": "finnhub"},
            "volume": {"source": "finnhub"},
        },
    }


def _healthily_enriched(ticker: str, price: float, volume: int) -> dict:
    """Same candidate with the full thesis a healthy provider run would attach."""
    item = _raw_discovery_entry(ticker, price, volume)
    item.update(
        {
            "exchange": "NASDAQ",
            "currency": "USD",
            "provider": "finnhub",
            "catalyst": f"{ticker} reports Q2 earnings on 2026-09-02 inside the requested horizon.",
            "risk": f"{ticker} Q2 revenue may miss the published consensus estimate.",
            "invalidation": "Invalidate on a close below the 20-day moving average after the Q2 report.",
        }
    )
    for field in ("catalyst", "risk", "invalidation"):
        item["provenance"][field] = {"source": "finnhub"}
    return item


def test_daily_top5_pass_liquidity_gate_with_real_data():
    """The 2026-08-22 daily top-5 all clear the liquidity floors for their band."""
    for ticker, price, volume in DAILY_TOP5:
        item = {"ticker": ticker, "price": price, "volume": volume, "market": "United States"}
        normalize_liquidity_fields(item)
        shares = item["avg_daily_volume_shares"]
        dollar = item["avg_daily_dollar_volume"]
        penny = price < 5.0
        assert shares >= (50_000 if penny else 500_000), f"{ticker} below shares floor"
        assert dollar >= (100_000 if penny else 10_000_000), f"{ticker} below dollar floor"


def test_daily_top5_raw_entries_fail_closed_without_thesis():
    """Discovery-only daily output must never pass the trade gate.

    The daily Mangala scan carries no catalyst/risk/invalidation/provenance,
    so the gate correctly rejects every entry — the divergence between the
    daily and live paths is missing enrichment, not a gate bug.
    """
    for ticker, price, volume in DAILY_TOP5:
        item = _raw_discovery_entry(ticker, price, volume)
        ok, reason = _apply_candidate_gate(item, allow_penny_otc=False, allow_microcap=False)
        assert not ok, f"{ticker} must fail closed without a thesis"
        assert reason == "missing_catalyst", f"{ticker} rejected with {reason}"
        _, failures = evaluate_quality_gates(item)
        assert "missing_risk" in failures and "missing_invalidation" in failures


def test_daily_top5_pass_full_gate_when_healthily_enriched():
    """With healthy data the gate approves exactly the 5 real candidates."""
    for ticker, price, volume in DAILY_TOP5:
        item = _healthily_enriched(ticker, price, volume)
        ok, reason = _apply_candidate_gate(item, allow_penny_otc=False, allow_microcap=False)
        assert ok, f"{ticker} failed healthy gate: {reason}"
        ok2, failures = evaluate_quality_gates(item)
        assert ok2, f"{ticker} failed quality gates: {failures}"


def test_computed_fallback_thesis_passes_for_real_candidates():
    """The live scan's own price/volume fallback thesis is actionable for all 5.

    This is the no-provider-catalyst path: even with a silent catalyst route,
    priced+volumed candidates get a computed, attributable thesis and pass.
    """
    for ticker, price, volume in DAILY_TOP5:
        item = _raw_discovery_entry(ticker, price, volume)
        fb = _generate_fallback_catalyst(item)
        assert fb.get("catalyst"), f"{ticker}: fallback produced no catalyst"
        assert _is_actionable_evidence(fb["catalyst"], "catalyst"), f"{ticker}: not actionable"
        item["catalyst"] = fb["catalyst"]
        item["invalidation"] = fb["invalidation"]
        item["risk"] = fb["risk"]
        item["provenance"].update(fb["provenance"])
        ok, reason = _apply_candidate_gate(item, allow_penny_otc=False, allow_microcap=False)
        assert ok, f"{ticker} failed with computed thesis: {reason}"


def test_generic_provider_catalyst_still_fails_closed():
    """Boilerplate catalyst text (not a number, not a concrete term) is rejected.

    This pins the 2026-08-22 missing_catalyst path: providers returning
    generic text suppress the computed fallback and the gate fails closed.
    """
    item = _healthily_enriched("NIO", 4.63, 21_891_270)
    item["catalyst"] = "Liquid equity on major exchange"
    item["risk"] = "Market risk"
    ok, reason = _apply_candidate_gate(item, allow_penny_otc=False, allow_microcap=False)
    assert not ok
    assert reason == "missing_catalyst"
