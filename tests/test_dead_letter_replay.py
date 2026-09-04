"""Consumidor da dead letter queue: replay de ordem paper que falhou o journal.

Semantica do replay: a EXECUCAO paper ja aconteceu; o que falhou foi o
registro de auditoria. Replay re-persiste no journal e NUNCA re-envia a
ordem ao broker (ou ao pipeline).
"""

from __future__ import annotations

import json
from pathlib import Path

from core.idempotency import enqueue_dead_letter, list_dead_letters
from core.pipeline.nodes.auto_execute_paper import replay_dead_letter_entry
from core.trading.paper_journal import PaperJournal, PaperTrade

TRADE_ID = "bob-replaytest-1"


def _make_trade(ticker: str = "TD") -> PaperTrade:
    return PaperTrade(
        trade_id=TRADE_ID,
        ticker=ticker,
        thesis="teste replay",
        direction="long",
        entry_date="2026-09-03T12:00:00+00:00",
        entry_price=88.5,
        shares=10,
        entry_reasoning="teste",
        verdict_at_entry="auto",
        risk_assessment="moderada",
        expected_holding_period="swing",
    )


def _setup(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("SUPEREZIO_PAPER_JOURNAL_PATH", str(tmp_path / "journal.jsonl"))
    monkeypatch.setenv("SUPEREZIO_DEDUP_DIR", str(tmp_path / "dedup"))
    monkeypatch.setenv("SUPEREZIO_DEAD_LETTER_DIR", str(tmp_path / "dead_letter"))


def test_replay_persists_journal_entry_and_leaves_the_queue(tmp_path, monkeypatch) -> None:
    _setup(monkeypatch, tmp_path)
    journal = PaperJournal()
    payload = _make_trade().to_dict()

    dl_path = enqueue_dead_letter(
        ticker="TD",
        qty=10,
        limit_price=88.5,
        action="buy",
        reason="journal_write_error:test",
        state_snapshot={"run_id": "run-1", "route": "auto", "journal_entry": payload},
    )

    pending = list_dead_letters()
    assert len(pending) == 1
    result = replay_dead_letter_entry(pending[0])

    assert result["status"] == "done"
    assert result["trade_id"] == TRADE_ID
    opened = [t for t in journal.list_open() if t.get("ticker") == "TD"]
    assert len(opened) == 1
    assert opened[0]["trade_id"] == TRADE_ID
    assert list_dead_letters() == [], "entrada replayada sai da fila de pending"
    record = json.loads(Path(dl_path).read_text(encoding="utf-8"))
    assert record["replay_status"] == "done"


def test_replay_is_idempotent_against_already_persisted_trade(tmp_path, monkeypatch) -> None:
    """Replay que ja persistiu o trade (mesmo trade_id) nao re-escreve o journal."""
    _setup(monkeypatch, tmp_path)
    journal = PaperJournal()
    payload = _make_trade().to_dict()

    enqueue_dead_letter(
        ticker="TD",
        qty=10,
        limit_price=88.5,
        action="buy",
        reason="journal_write_error:test",
        state_snapshot={"journal_entry": payload},
    )
    entry = list_dead_letters()[0]

    assert replay_dead_letter_entry(entry)["status"] == "done"
    assert list_dead_letters() == [], "entrada replayada sai da fila"
    # O trade ja esta persistido; a entrada em memoria ainda diz pending, mas o
    # replay reconhece o trade_id gravado e recusa a segunda escrita.
    assert replay_dead_letter_entry(entry)["status"] == "skipped"
    assert len(journal.list_open()) == 1

    # Entrada marcada done/failed tambem nao roda de novo.
    entry["replay_status"] = "done"
    assert replay_dead_letter_entry(entry)["status"] == "skipped"


def test_replay_legacy_entry_without_journal_entry_builds_minimal_trade(
    tmp_path, monkeypatch
) -> None:
    """Entrada enfileirada antes do journal_entry existir ainda e replayavel."""
    _setup(monkeypatch, tmp_path)
    journal = PaperJournal()

    enqueue_dead_letter(
        ticker="AC",
        qty=5,
        limit_price=12.34,
        action="buy",
        reason="journal_write_error:legacy",
        state_snapshot={"run_id": "run-legacy"},
    )
    result = replay_dead_letter_entry(list_dead_letters()[0])

    assert result["status"] == "done"
    opened = [t for t in journal.list_open() if t.get("ticker") == "AC"]
    assert len(opened) == 1
    assert opened[0]["shares"] == 5
    assert opened[0]["entry_price"] == 12.34


def test_replay_sell_closes_open_trade(tmp_path, monkeypatch) -> None:
    _setup(monkeypatch, tmp_path)
    journal = PaperJournal()
    journal.open_trade(_make_trade())

    enqueue_dead_letter(
        ticker="TD",
        qty=10,
        limit_price=90.0,
        action="sell",
        reason="journal_write_error:test",
        state_snapshot={"run_id": "run-1", "route": "auto"},
    )
    result = replay_dead_letter_entry(list_dead_letters()[0])

    assert result["status"] == "done"
    assert result["trade_id"] == TRADE_ID
    assert [t for t in journal.list_open() if t.get("ticker") == "TD"] == []
