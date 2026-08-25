from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from core.trading.workflow_store import (
    TradeWorkflowStore,
    WorkflowConflictError,
    WorkflowStoreError,
    build_trade_intent_fingerprint,
    build_trade_intent_fingerprints,
)


def _ticket(**overrides: object) -> dict[str, object]:
    ticket: dict[str, object] = {
        "ticket_id": "ticket-1",
        "fingerprint": "a" * 64,
        "broker": "TD_DIRECT_INVESTING_CANADA",
        "status": "DRAFT_UNVERIFIED_QUOTE",
        "phase": "independent_quote_verification_required",
        "submitted_to_broker": False,
        "symbol": "TD",
    }
    ticket.update(overrides)
    return ticket


def test_ticket_is_idempotent_across_store_restart(tmp_path: Path) -> None:
    db = tmp_path / "workflow.sqlite3"
    first, created = TradeWorkflowStore(db).create_ticket(_ticket())
    second, created_again = TradeWorkflowStore(db).create_ticket(
        _ticket(ticket_id="retry-generated-id")
    )

    assert created is True
    assert created_again is False
    assert second["ticket_id"] == first["ticket_id"] == "ticket-1"
    assert TradeWorkflowStore(db).list_tickets() == [second]


def test_fingerprint_pair_closes_window_boundary() -> None:
    """Duas tentativas da mesma intencao a 2s de distancia devem se reconhecer.

    A janela e truncada contra o relogio de parede, entao 10:04:59 e 10:05:01
    caem em janelas diferentes — exatamente quando um retry e mais provavel.
    """
    intent = {"symbol": "TD", "side": "BUY", "quantity": 10, "limit_price": 110.0}
    before = datetime(2026, 8, 24, 10, 4, 59, tzinfo=timezone.utc)
    after = datetime(2026, 8, 24, 10, 5, 1, tzinfo=timezone.utc)

    first_current, _ = build_trade_intent_fingerprints(intent, now=before)
    second_current, second_previous = build_trade_intent_fingerprints(intent, now=after)

    # A borda continua existindo na chave crua da janela atual...
    assert first_current != second_current
    # ...mas o retry reconhece a tentativa anterior pelo alias.
    assert second_previous == first_current


def test_create_ticket_replays_across_window_boundary(tmp_path: Path) -> None:
    """Retry cruzando a borda da janela nao pode criar um segundo ticket."""
    db = tmp_path / "workflow.sqlite3"
    store = TradeWorkflowStore(db)
    intent = {"symbol": "TD", "side": "BUY", "quantity": 10, "limit_price": 110.0}
    before = datetime(2026, 8, 24, 10, 4, 59, tzinfo=timezone.utc)
    after = datetime(2026, 8, 24, 10, 5, 1, tzinfo=timezone.utc)

    first_fingerprint, _ = build_trade_intent_fingerprints(intent, now=before)
    retry_fingerprint, retry_previous = build_trade_intent_fingerprints(intent, now=after)

    first, created = store.create_ticket(
        _ticket(ticket_id="ticket-boundary", fingerprint=first_fingerprint)
    )
    second, created_again = store.create_ticket(
        _ticket(ticket_id="ticket-boundary-retry", fingerprint=retry_fingerprint),
        fingerprint_aliases=[retry_previous],
    )

    assert created is True
    assert created_again is False, "retry cruzando a borda deve ser replay, nao ticket novo"
    assert second["ticket_id"] == first["ticket_id"] == "ticket-boundary"
    assert len(store.list_tickets()) == 1


def test_create_ticket_rejects_malformed_fingerprint_alias(tmp_path: Path) -> None:
    """Alias fora do formato SHA-256 e recusado, nunca ignorado em silencio."""
    store = TradeWorkflowStore(tmp_path / "workflow.sqlite3")
    with pytest.raises(WorkflowStoreError, match="fingerprint aliases"):
        store.create_ticket(_ticket(), fingerprint_aliases=["not-a-sha256"])


def test_ticket_id_collision_fails_closed(tmp_path: Path) -> None:
    store = TradeWorkflowStore(tmp_path / "workflow.sqlite3")
    store.create_ticket(_ticket())

    with pytest.raises(WorkflowConflictError, match="ticket_id"):
        store.create_ticket(_ticket(fingerprint="b" * 64))


def test_transition_is_idempotent_and_checks_expected_status(tmp_path: Path) -> None:
    db = tmp_path / "workflow.sqlite3"
    store = TradeWorkflowStore(db)
    store.create_ticket(_ticket())
    updated = store.transition_ticket(
        "ticket-1",
        expected_status="DRAFT_UNVERIFIED_QUOTE",
        new_status="GATED",
        new_phase="gated",
        actor="system",
        idempotency_key="gate-1",
    )
    updated = store.transition_ticket(
        "ticket-1",
        expected_status="GATED",
        new_status="AWAITING_HUMAN",
        new_phase="human_review",
        actor="operator",
        idempotency_key="review-1",
    )
    replay = TradeWorkflowStore(db).transition_ticket(
        "ticket-1",
        expected_status="GATED",
        new_status="AWAITING_HUMAN",
        new_phase="human_review",
        actor="operator",
        idempotency_key="review-1",
    )

    assert updated["status"] == replay["status"] == "AWAITING_HUMAN"
    assert replay["workflow_version"] == 3
    with pytest.raises(WorkflowConflictError, match="expected"):
        store.transition_ticket(
            "ticket-1",
            expected_status="GATED",
            new_status="APPROVED",
            new_phase="approved",
            actor="operator",
            idempotency_key="approval-1",
        )


def test_illegal_transition_and_identity_patch_are_blocked(tmp_path: Path) -> None:
    store = TradeWorkflowStore(tmp_path / "workflow.sqlite3")
    store.create_ticket(_ticket())

    with pytest.raises(WorkflowConflictError, match="illegal"):
        store.transition_ticket(
            "ticket-1",
            expected_status="DRAFT_UNVERIFIED_QUOTE",
            new_status="BROKER_CONFIRMED",
            new_phase="confirmed",
            actor="operator",
            idempotency_key="skip-all-gates",
        )
    with pytest.raises(WorkflowConflictError, match="unsupported"):
        store.transition_ticket(
            "ticket-1",
            expected_status="DRAFT_UNVERIFIED_QUOTE",
            new_status="GATED",
            new_phase="gated",
            actor="system",
            idempotency_key="mutate-symbol",
            evidence_patch={"symbol": "AAPL"},
        )


def test_system_state_survives_restart(tmp_path: Path) -> None:
    db = tmp_path / "workflow.sqlite3"
    TradeWorkflowStore(db).save_system_state("kill_switch", {"is_active": True})

    assert TradeWorkflowStore(db).load_system_state("kill_switch") == {"is_active": True}


def test_dead_letter_is_deduplicated_and_replayable(tmp_path: Path) -> None:
    store = TradeWorkflowStore(tmp_path / "workflow.sqlite3")
    dead_letters = tmp_path / "dead-letter"
    first = store.record_dead_letter(
        category="td_ticket_audit",
        idempotency_key="a" * 64,
        payload=_ticket(),
        error="disk unavailable",
        output_dir=dead_letters,
    )
    second = TradeWorkflowStore(store.path).record_dead_letter(
        category="td_ticket_audit",
        idempotency_key="a" * 64,
        payload=_ticket(),
        error="another retry error",
        output_dir=dead_letters,
    )

    assert first == second
    assert len(list(dead_letters.glob("*.json"))) == 1
    body = json.loads(first.read_text(encoding="utf-8"))
    assert body["status"] == "pending_manual_replay"
    assert body["payload"]["submitted_to_broker"] is False


def test_new_ticket_requires_explicit_not_submitted(tmp_path: Path) -> None:
    store = TradeWorkflowStore(tmp_path / "workflow.sqlite3")
    with pytest.raises(WorkflowStoreError, match="submitted_to_broker=false"):
        store.create_ticket(_ticket(submitted_to_broker=True))


def test_intent_fingerprint_is_stable_inside_five_minute_window() -> None:
    from datetime import datetime, timezone

    intent = {"ticker": "TD", "action": "buy", "qty": 2, "limit_price": 110, "session_id": "s"}
    first = build_trade_intent_fingerprint(
        intent, now=datetime(2026, 8, 19, 2, 1, tzinfo=timezone.utc)
    )
    retry = build_trade_intent_fingerprint(
        intent, now=datetime(2026, 8, 19, 2, 4, tzinfo=timezone.utc)
    )
    later = build_trade_intent_fingerprint(
        intent, now=datetime(2026, 8, 19, 2, 5, tzinfo=timezone.utc)
    )

    assert first == retry
    assert later != first
