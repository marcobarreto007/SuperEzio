import json
from datetime import UTC, datetime, timedelta

import pytest

from core.trading.td_research_candidates import load_research_candidates


@pytest.fixture
def research_root(tmp_path):
    today = datetime.now(UTC)
    config = tmp_path / "config"
    config.mkdir()
    (config / "td_direct_commission_free_etfs.json").write_text(
        json.dumps(
            {
                "verified_at": today.isoformat(),
                "source_url": "https://www.td.com/ca/en/investing/direct-investing/commission-free-etfs",
                "symbols": {"CAN": ["VFV"], "US": []},
            }
        )
    )
    (config / "td_universe_effective.json").write_text(
        json.dumps(
            {
                "generated_at": today.isoformat(),
                "symbols": {
                    "VFV": {
                        "listing_currency": "CAD",
                        "eligible_strict": True,
                        "friction": {"spread_pct_corwin_schultz_mean": 0.1234},
                    }
                },
            }
        )
    )
    history = tmp_path / "data/reference/effective_universe/ohlcv"
    history.mkdir(parents=True)
    (history / "VFV.TO.csv").write_text(f"Date,Close\n{today.date()},188.58\n")
    return tmp_path


def test_candidates_quote_history_with_provenance_not_live_approval(research_root):
    result = load_research_candidates(research_root)
    row = result["opportunities"][0]
    assert result["status"] == "research_only"
    assert result["scanned_at"] is None
    assert row["historical_close"] == 188.58
    assert row["price"] is None
    assert row["meta_labeling_p"] is None
    assert row["commission"] is None
    assert row["execution_ready"] is False
    assert "flip_plan" not in row
    assert row["provenance"]["historical_close"]["adjusted"] is True
    assert row["provenance"]["estimated_spread_pct"]["is_estimate"] is True


@pytest.mark.parametrize("close", ["nan", "inf", "-1", "0"])
def test_invalid_history_is_not_a_candidate(research_root, close):
    path = research_root / "data/reference/effective_universe/ohlcv/VFV.TO.csv"
    path.write_text(f"Date,Close\n{datetime.now(UTC).date()},{close}\n")
    assert load_research_candidates(research_root)["opportunities"] == []


def test_stale_history_is_not_a_candidate(research_root):
    path = research_root / "data/reference/effective_universe/ohlcv/VFV.TO.csv"
    old = (datetime.now(UTC) - timedelta(days=8)).date()
    path.write_text(f"Date,Close\n{old},188.58\n")
    assert load_research_candidates(research_root)["status"] == "unavailable"


def test_missing_history_never_falls_back_to_synthetic_price(research_root):
    (research_root / "data/reference/effective_universe/ohlcv/VFV.TO.csv").unlink()
    assert load_research_candidates(research_root)["opportunities"] == []


def test_manifest_membership_is_rechecked(research_root):
    path = research_root / "config/td_direct_commission_free_etfs.json"
    data = json.loads(path.read_text())
    data["symbols"]["CAN"] = ["XIU"]
    path.write_text(json.dumps(data))
    assert load_research_candidates(research_root)["opportunities"] == []


def test_stale_artifact_fails_closed(research_root):
    path = research_root / "config/td_universe_effective.json"
    data = json.loads(path.read_text())
    data["generated_at"] = (datetime.now(UTC) - timedelta(days=8)).isoformat()
    path.write_text(json.dumps(data))
    with pytest.raises(ValueError, match="stale"):
        load_research_candidates(research_root)


@pytest.mark.asyncio
async def test_endpoint_returns_source_evidence(research_root, monkeypatch):
    from agent_server.endpoints import get_cockpit_mangala_opportunities
    from core.trading import td_research_candidates

    monkeypatch.setattr(
        td_research_candidates,
        "load_research_candidates",
        lambda: load_research_candidates(research_root),
    )
    result = await get_cockpit_mangala_opportunities()
    assert result["opportunities"][0]["historical_close"] == 188.58


@pytest.mark.asyncio
async def test_endpoint_missing_reference_is_unavailable(monkeypatch):
    from agent_server.endpoints import get_cockpit_mangala_opportunities
    from core.trading import td_research_candidates

    def missing():
        raise FileNotFoundError("reference missing")

    monkeypatch.setattr(td_research_candidates, "load_research_candidates", missing)
    result = await get_cockpit_mangala_opportunities()
    assert result["status"] == "unavailable"
    assert result["opportunities"] == []
