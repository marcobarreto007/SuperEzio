"""Contagem do comitê de arbitragem (red team/judge) — env e capping.

Importar o app injeta SUPEREZIO_RED_TEAM_AGENTS/JUDGE_AGENTS no processo;
o graph usa no máximo 1 agente por papel e env inválido não pode derrubar
o pipeline (ValueError).
"""

from core.pipeline.graph import _arbitration_agent_count


def test_unset_is_zero(monkeypatch):
    monkeypatch.delenv("SUPEREZIO_RED_TEAM_AGENTS", raising=False)
    assert _arbitration_agent_count("SUPEREZIO_RED_TEAM_AGENTS") == 0


def test_value_is_capped_to_one(monkeypatch):
    monkeypatch.setenv("SUPEREZIO_RED_TEAM_AGENTS", "3")
    assert _arbitration_agent_count("SUPEREZIO_RED_TEAM_AGENTS") == 1


def test_negative_is_zero(monkeypatch):
    monkeypatch.setenv("SUPEREZIO_JUDGE_AGENTS", "-2")
    assert _arbitration_agent_count("SUPEREZIO_JUDGE_AGENTS") == 0


def test_garbage_is_zero_not_crash(monkeypatch):
    monkeypatch.setenv("SUPEREZIO_JUDGE_AGENTS", "abc")
    assert _arbitration_agent_count("SUPEREZIO_JUDGE_AGENTS") == 0


def test_one_stays_one(monkeypatch):
    monkeypatch.setenv("SUPEREZIO_JUDGE_AGENTS", "1")
    assert _arbitration_agent_count("SUPEREZIO_JUDGE_AGENTS") == 1
