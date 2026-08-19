from __future__ import annotations

import json
from pathlib import Path

import pytest

from core.trading.workflow_store import (
    TradeWorkflowStore,
    WorkflowConflictError,
    WorkflowStoreError,
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
        new_status="AWAITING_HUMAN",
        new_phase="human_review",
        actor="operator",
        idempotency_key="review-1",
    )
    replay = TradeWorkflowStore(db).transition_ticket(
        "ticket-1",
        expected_status="DRAFT_UNVERIFIED_QUOTE",
        new_status="AWAITING_HUMAN",
        new_phase="human_review",
        actor="operator",
        idempotency_key="review-1",
    )

    assert updated["status"] == replay["status"] == "AWAITING_HUMAN"
    assert replay["workflow_version"] == 2
    with pytest.raises(WorkflowConflictError, match="expected"):
        store.transition_ticket(
            "ticket-1",
            expected_status="DRAFT_UNVERIFIED_QUOTE",
            new_status="APPROVED",
            new_phase="approved",
            actor="operator",
            idempotency_key="approval-1",
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
