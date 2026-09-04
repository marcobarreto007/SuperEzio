"""Comportamento de borda das chaves de idempotencia de trade.

A janela de dedup e truncada contra o relogio de parede, entao duas
tentativas da mesma intencao a segundos de distancia podem cair em janelas
diferentes — exatamente quando um retry e mais provavel.
"""

from __future__ import annotations

from datetime import UTC, datetime

from core.idempotency import (
    claim_idempotency_keys,
    is_duplicate,
    make_idempotency_key,
    make_idempotency_keys,
)

BEFORE = datetime(2026, 8, 24, 10, 4, 59, tzinfo=UTC)
AFTER = datetime(2026, 8, 24, 10, 5, 1, tzinfo=UTC)
INTENT = {"ticker": "TD", "qty": 10, "limit_price": 110.0}


def test_single_key_has_the_window_boundary_hole() -> None:
    """Documenta o defeito que motivou o par de chaves.

    make_idempotency_key sozinha continua com o buraco; quem guarda submissao
    real precisa usar o par.
    """
    first = make_idempotency_key(**INTENT, now=BEFORE)
    second = make_idempotency_key(**INTENT, now=AFTER)
    assert first != second, "2s cruzando a borda ainda produzem chaves distintas"


def test_key_pair_recognises_the_previous_window() -> None:
    first_current, _ = make_idempotency_keys(**INTENT, now=BEFORE)
    second_current, second_previous = make_idempotency_keys(**INTENT, now=AFTER)

    assert first_current != second_current
    assert second_previous == first_current, "o retry precisa reconhecer a janela anterior"


def test_claim_blocks_retry_across_the_boundary(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("SUPEREZIO_DEDUP_DIR", str(tmp_path / "dedup"))

    first_keys = make_idempotency_keys(**INTENT, now=BEFORE)
    retry_keys = make_idempotency_keys(**INTENT, now=AFTER)

    assert claim_idempotency_keys(first_keys, {"status": "allowed"}) is True
    assert any(is_duplicate(key) for key in retry_keys), (
        "retry cruzando a borda deve ser detectado como duplicata"
    )
    assert claim_idempotency_keys(retry_keys, {"status": "allowed"}) is False


def test_two_windows_later_is_genuinely_a_new_intent(tmp_path, monkeypatch) -> None:
    """Passadas duas janelas continua sendo intencao nova — o contrato nao muda."""
    monkeypatch.setenv("SUPEREZIO_DEDUP_DIR", str(tmp_path / "dedup"))
    much_later = datetime(2026, 8, 24, 10, 20, 0, tzinfo=UTC)

    assert claim_idempotency_keys(make_idempotency_keys(**INTENT, now=BEFORE)) is True

    later_keys = make_idempotency_keys(**INTENT, now=much_later)
    assert not any(is_duplicate(key) for key in later_keys)
    assert claim_idempotency_keys(later_keys) is True


def test_dirs_anchor_to_project_root_when_env_is_absent(monkeypatch, tmp_path) -> None:
    """Sem env, dedup/dead-letter resolvem contra a raiz do projeto, nunca o cwd.

    Bootar de outro diretorio com o default relativo antigo criaria um
    journal/dedup novo e reabriria a janela de duplicata cross-restart.
    """
    import core.idempotency as idem

    monkeypatch.delenv("SUPEREZIO_DEDUP_DIR", raising=False)
    monkeypatch.delenv("SUPEREZIO_DEAD_LETTER_DIR", raising=False)

    resolved: list[str] = []

    def fake_resolve(name: str):
        resolved.append(name)
        return tmp_path / name

    monkeypatch.setattr("core.idempotency.resolve_project_path", fake_resolve)

    assert idem._ensure_dedup_dir() == tmp_path / "journal" / "dedup"
    assert idem._ensure_dead_letter_dir() == tmp_path / "journal" / "dead_letter"
    assert resolved == ["journal/dedup", "journal/dead_letter"]
