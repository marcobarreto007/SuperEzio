"""Testes do filtro fail-closed de sessão na ConversationMemory.

Regra: só sessões interativas reais (bob-<uuid>) ou ids na allowlist
SUPEREZIO_MEMORY_EXTRA_SESSIONS persistem no disco. Sessões de teste/probe
são descartadas antes de tocar o arquivo — a memória alimenta conselho
financeiro e não pode acumular resíduo de teste.
"""

import tempfile
from pathlib import Path

import pytest

from core.memory.conversation_memory import ConversationMemory, is_real_session_id

REAL_SESSION = "bob-7e65d4c1-70c1-40ac-a9f0-85e09d1e799a"


@pytest.mark.parametrize(
    "session_id,expected",
    [
        (REAL_SESSION, True),
        ("bob-933411f2-788d-40a7-ab51-d5c575ab2e01", True),
        ("default", False),
        ("", False),
        (None, False),
        ("test-runner", False),
        ("quality-probe-ticker_analysis-1787067346", False),
        ("overnight_001", False),
        ("stress-000", False),
        ("bob-test", False),  # prefixo bob- sem uuid não basta
        ("bob-final", False),
        ("operator", False),  # sem allowlist, falha fechado
    ],
)
def test_is_real_session_id(session_id, expected):
    assert is_real_session_id(session_id) is expected


def test_bob_uuid_session_persists():
    with tempfile.TemporaryDirectory() as tmpdir:
        mem_path = Path(tmpdir) / "memory.jsonl"
        mem = ConversationMemory(mem_path)
        turn = mem.add_turn(REAL_SESSION, "oi Bob", "olá!")
        assert mem_path.exists()
        assert len(mem.get_session_history(REAL_SESSION)) == 1
        assert turn.session_id == REAL_SESSION


def test_default_session_does_not_persist():
    with tempfile.TemporaryDirectory() as tmpdir:
        mem_path = Path(tmpdir) / "memory.jsonl"
        mem = ConversationMemory(mem_path)
        turn = mem.add_turn("default", "cara vc esta travado neste ticket ?", "resposta")
        # Retorna o turno para o caller, mas não toca disco nem cache
        assert turn.session_id == "default"
        assert not mem_path.exists()
        assert mem.get_session_history("default") == []


@pytest.mark.parametrize(
    "session_id",
    [
        "default",
        "test-runner",
        "quality-probe-status_pt-1787067241",
        "overnight_092",
        "small_caps_memory_injection",
        "bob_order_probe_20_20260617-161416",
    ],
)
def test_test_sessions_never_persist(session_id):
    with tempfile.TemporaryDirectory() as tmpdir:
        mem_path = Path(tmpdir) / "memory.jsonl"
        mem = ConversationMemory(mem_path)
        mem.add_turn(session_id, "prompt de teste", "resposta de teste")
        assert not mem_path.exists()
        assert mem.get_session_history(session_id) == []


def test_env_allowlist_extra_session_persists(monkeypatch):
    monkeypatch.setenv("SUPEREZIO_MEMORY_EXTRA_SESSIONS", "operator,trader")
    with tempfile.TemporaryDirectory() as tmpdir:
        mem_path = Path(tmpdir) / "memory.jsonl"
        mem = ConversationMemory(mem_path)
        mem.add_turn("operator", "pergunta real via API", "resposta")
        assert mem_path.exists()
        assert len(mem.get_session_history("operator")) == 1


def test_filter_disabled_persists_any_session():
    """reset_memory_for_test e uso explícito desligam o filtro (isolamento de teste)."""
    with tempfile.TemporaryDirectory() as tmpdir:
        mem_path = Path(tmpdir) / "memory.jsonl"
        mem = ConversationMemory(mem_path, enforce_session_filter=False)
        mem.add_turn("s1", "Buy AAPL?", "Apple strong", ticker_discussed="AAPL")
        assert mem_path.exists()
        assert len(mem.get_session_history("s1")) == 1
