"""Contract tests for Dashboard Survival Protocol & TD Canada Universe.

Valida as garantias do dashboard moderno de 2026:
1. get_cockpit_mangala() reflete o Protocolo de Sobrevivencia ($1.000 CAD base).
2. get_cockpit_mangala_opportunities() reflete os ETFs TD Canada com clusters e Meta-Labeling.
3. _cockpit_trade_history() inclui recomendacoes da caderneta.
"""

from __future__ import annotations

import pytest

from agent_server.endpoints import (
    _cockpit_trade_history,
    get_cockpit_mangala,
    get_cockpit_mangala_opportunities,
)


@pytest.mark.asyncio
async def test_cockpit_survival_protocol_contract():
    """Garante que o painel de capital responde o Protocolo de Sobrevivencia 1000 CAD."""
    data = await get_cockpit_mangala()
    assert data["status"] == "ok"
    assert data["protocol"] == "SOBREVIVENCIA_1000_CAD"
    assert data["currency"] == "CAD"
    assert data["starting"] == 1000.0
    assert data["current"] >= 1000.0
    assert "risk_budget_cad" in data
    assert data["meta_labeling_threshold"] == 0.55


@pytest.mark.asyncio
async def test_cockpit_td_opportunities_contract():
    """Garante que as oportunidades do painel sao ETFs do Canada com clusters."""
    data = await get_cockpit_mangala_opportunities()
    assert data["status"] in {"research_only", "unavailable"}
    assert data["scanned_at"] is None
    for item in data["opportunities"]:
        assert item["ticker"].endswith(".TO")
        assert item["price"] is None
        assert item["meta_labeling_p"] is None
        assert item["provenance"]["historical_close"]["as_of"]
        assert item["execution_ready"] is False


def test_cockpit_trade_history_integrates_recommendations():
    """Garante que _cockpit_trade_history carrega a caderneta de recomendacoes."""
    history = _cockpit_trade_history(limit=10)
    assert history["source"] == "recommendation_ledger"
    assert "trades" in history
    if history["trades"]:
        assert "ticker" in history["trades"][0]


def test_cockpit_trade_history_excludes_mangala_fixtures(monkeypatch):
    class FakeJournal:
        path = "paper_journal.jsonl"

        def list_all(self):
            return [
                {
                    "trade_id": "mangala-AAPL-1",
                    "ticker": "AAPL",
                    "entry_price": 100.0,
                    "shares": 10.0,
                },
                {
                    "trade_id": "rec-real",
                    "ticker": "VFV",
                    "entry_price": 50.0,
                    "shares": 3.0,
                    "thesis": "tese paper",
                },
            ]

        def get_stats(self):
            return {"total_trades": 2, "open_trades": 2}

    class FakeLedger:
        def _read_all(self):
            return []

    monkeypatch.setattr("core.trading.paper_journal.PaperJournal", FakeJournal)
    monkeypatch.setattr(
        "core.trading.recommendation_ledger.get_recommendation_ledger",
        lambda: FakeLedger(),
    )
    history = _cockpit_trade_history(limit=10)
    ids = [row["trade_id"] for row in history["trades"]]
    assert "mangala-AAPL-1" not in ids
    assert "rec-real" in ids
    assert history["stats"]["not_broker_fills"] is True
    assert history["stats"]["broker_open_positions"] == 0
    assert all(row.get("is_broker_fill") is False for row in history["trades"])
