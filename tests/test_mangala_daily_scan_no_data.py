"""Mangala daily scan must not stamp absent social data as a clean reading.

The scan used to coerce ``None`` social scores to ``0``, which the label
mapper then read as FRACO/CLEAN — dead data wearing an observed badge.
"""

from __future__ import annotations

import json

from scripts import mangala_daily_scan as scan
from scripts.mangala_daily_scan import (
    MangalaOpportunity,
    _get_pennylab_data,
    _inline_score_whale,
    _map_pump_risk,
    _map_whale_status,
)


class _OfflineSocialWhale:
    """Provider shape returned when every source is offline."""

    def get_whale_signals(self, ticker: str) -> dict:
        return {
            "ticker": ticker,
            "error": "no_data_all_sources_offline",
            "signal": "UNKNOWN",
            "data_status": "NO_DATA",
            "source": "no_data",
            "whale_score": None,
            "whale_mentions": 0,
        }

    def get_pump_detection(self, ticker: str) -> dict:
        return {
            "ticker": ticker,
            "error": "no_data_all_sources_offline",
            "signal": "UNKNOWN",
            "data_status": "NO_DATA",
            "source": "no_data",
            "pump_risk": None,
            "pump_mentions": 0,
            "dump_mentions": 0,
        }


def test_none_scores_map_to_sem_dados():
    assert _map_whale_status(None) == "SEM_DADOS"
    assert _map_pump_risk(None) == "SEM_DADOS"
    assert _map_whale_status(0) == "FRACO"
    assert _map_pump_risk(0) == "CLEAN"


def test_offline_provider_keeps_none_and_reports_no_data():
    pennylab = _get_pennylab_data(_OfflineSocialWhale(), "RIG")

    assert pennylab["whale_score"] is None
    assert pennylab["pump_score"] is None
    assert pennylab["data_status"] == "NO_DATA"
    assert pennylab["whale_data_status"] == "NO_DATA"
    assert pennylab["pump_data_status"] == "NO_DATA"


def test_observed_provider_is_scored_and_marked_observed():
    class _Observed(_OfflineSocialWhale):
        def get_whale_signals(self, ticker: str) -> dict:
            return {
                "ticker": ticker,
                "signal": "WHALE_DETECTED",
                "data_status": "OBSERVED",
                "whale_score": 72,
            }

        def get_pump_detection(self, ticker: str) -> dict:
            return {"ticker": ticker, "signal": "CLEAN", "data_status": "OBSERVED", "pump_risk": 0}

    pennylab = _get_pennylab_data(_Observed(), "ATER")

    assert pennylab["whale_score"] == 72
    assert pennylab["pump_score"] == 0
    assert pennylab["data_status"] == "OBSERVED"


def test_no_provider_means_no_data():
    pennylab = _get_pennylab_data(None, "KODK")

    assert pennylab["whale_score"] is None
    assert pennylab["pump_score"] is None
    assert pennylab["data_status"] == "NO_DATA"


def test_sem_dados_whale_label_scores_zero_without_volume_fallback():
    # Volume/preço existem, mas medem outra coisa — não viram score de whale.
    assert (
        _inline_score_whale(
            {
                "whale_print": {"label": "SEM_DADOS", "confidence": 0.0, "score": None},
                "volume": 5_000_000,
                "avg_volume_20d": 100_000,
                "price": 2.00,
            }
        )
        == 0
    )


def test_record_serialises_none_scores_and_data_status():
    record = MangalaOpportunity(
        ticker="RIG",
        price=4.5,
        volume=1_000_000,
        name="Transocean",
        score=40,
        signal="PASS",
        factors={"volume": 0, "whale": 0, "momentum": 0, "rsi": 0, "catalyst": 0},
        whale_status=_map_whale_status(None),
        whale_score=None,
        pump_risk=_map_pump_risk(None),
        pump_score=None,
        data_status="NO_DATA",
        flip_plan={},
    ).to_dict()

    assert record["whale_status"] == "SEM_DADOS"
    assert record["pump_risk"] == "SEM_DADOS"
    assert record["data_status"] == "NO_DATA"
    assert json.loads(json.dumps(record))["whale_score"] is None


def test_scan_record_reports_no_data_end_to_end(monkeypatch):
    """run_daily_scan must publish SEM_DADOS + None scores when the social
    source observed nothing (no artifact is written in this test)."""
    saved: list[MangalaOpportunity] = []
    monkeypatch.setattr(scan, "_get_data_hub", lambda: object())
    monkeypatch.setattr(scan, "_get_social_whale", lambda _hub: _OfflineSocialWhale())
    monkeypatch.setattr(
        scan,
        "_get_candidates",
        lambda _hub: [{"ticker": "RIG", "price": 4.5, "volume": 1_000_000, "name": "Transocean"}],
    )
    monkeypatch.setattr(
        scan,
        "_collect_stock_data",
        lambda _hub, ticker, _cand: {
            "ticker": ticker,
            "price": 4.5,
            "volume": 1_000_000,
            "avg_volume_20d": 500_000,
            "momentum_5d": 0.0,
            "rsi": 50.0,
            "news_count": 0,
        },
    )
    monkeypatch.setattr(scan, "_save_scan_results", lambda opps: saved.extend(opps))

    results = scan.run_daily_scan()

    assert len(results) == 1
    record = results[0]
    assert record["whale_score"] is None
    assert record["pump_score"] is None
    assert record["whale_status"] == "SEM_DADOS"
    assert record["pump_risk"] == "SEM_DADOS"
    assert record["data_status"] == "NO_DATA"
    assert [opp.data_status for opp in saved] == ["NO_DATA"]
