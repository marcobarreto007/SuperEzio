from __future__ import annotations

import json
from pathlib import Path

from scripts.replay_td_ticket_dead_letter import replay
from core.trading.workflow_store import TradeWorkflowStore


def test_dead_letter_replay_repairs_claim_without_duplicate(tmp_path: Path) -> None:
    db = tmp_path / "workflow.sqlite3"
    ticket_log = tmp_path / "td" / "tickets.jsonl"
    ticket = {
        "ticket_id": "td-replay-1",
        "fingerprint": "f" * 64,
        "broker": "TD_DIRECT_INVESTING_CANADA",
        "status": "DRAFT_UNVERIFIED_QUOTE",
        "phase": "independent_quote_verification_required",
        "submitted_to_broker": False,
        "transmission_capability": False,
    }
    store = TradeWorkflowStore(db)
    store.create_ticket(ticket)
    claims = ticket_log.parent / "claims"
    claims.mkdir(parents=True)
    (claims / f"{'f' * 64}.json").write_text(
        json.dumps({"ticket_id": ticket["ticket_id"], "fingerprint": ticket["fingerprint"]}),
        encoding="utf-8",
    )
    store.record_dead_letter(
        category="td_ticket_audit",
        idempotency_key="f" * 64,
        payload=ticket,
        error="simulated crash after claim",
        output_dir=tmp_path / "dead-letter",
    )
    store.transition_ticket(
        ticket["ticket_id"],
        expected_status="DRAFT_UNVERIFIED_QUOTE",
        new_status="AUDIT_WRITE_FAILED",
        new_phase="dead_letter_replay_required",
        actor="system",
        idempotency_key="audit-failed",
    )

    result = replay(
        workflow_db=db,
        ticket_log=ticket_log,
        ticket_id=ticket["ticket_id"],
        actor="marco",
    )

    assert result["status"] == "DRAFT_UNVERIFIED_QUOTE"
    assert result["system_transmitted"] is False
    assert len(ticket_log.read_text(encoding="utf-8").splitlines()) == 1
