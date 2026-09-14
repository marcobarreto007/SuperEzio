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
    assert data["status"] == "ok"
    assert data["currency"] == "CAD"
    assert len(data["opportunities"]) >= 5
    first = data["opportunities"][0]
    assert first["ticker"].endswith(".TO")
    assert "cluster" in first
    assert "meta_labeling_p" in first
    assert first["meta_labeling_p"] >= 0.55


def test_cockpit_trade_history_integrates_recommendations():
    """Garante que _cockpit_trade_history carrega a caderneta de recomendacoes."""
    history = _cockpit_trade_history(limit=10)
    assert history["source"] == "recommendation_ledger"
    assert "trades" in history
    if history["trades"]:
        assert "ticker" in history["trades"][0]
