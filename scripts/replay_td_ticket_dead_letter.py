"""Manually replay one TD ticket audit dead letter from durable workflow state."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from core.trading.td_direct_ticket import replay_td_direct_ticket_audit
from core.trading.workflow_store import TradeWorkflowStore


def replay(
    *,
    workflow_db: Path,
    ticket_log: Path,
    ticket_id: str,
    actor: str,
) -> dict[str, object]:
    store = TradeWorkflowStore(workflow_db)
    ticket = store.get_ticket(ticket_id)
    if ticket is None:
        raise RuntimeError(f"unknown ticket: {ticket_id}")
    allowed_statuses = {
        "AUDIT_WRITE_FAILED",
        "DRAFT_UNVERIFIED_QUOTE",
        "DRAFT_QUOTE_VERIFIED",
    }
    if ticket["status"] not in allowed_statuses:
        raise RuntimeError(f"ticket is not awaiting audit replay: {ticket['status']}")
    replay_td_direct_ticket_audit(ticket, ticket_log)
    restored = ticket
    if ticket["status"] == "AUDIT_WRITE_FAILED":
        restored_status = (
            "DRAFT_QUOTE_VERIFIED"
            if ticket.get("quote", {}).get("evidence_hash")
            else "DRAFT_UNVERIFIED_QUOTE"
        )
        restored = store.transition_ticket(
            ticket_id,
            expected_status="AUDIT_WRITE_FAILED",
            new_status=restored_status,
            new_phase=(
                "money_gate_required"
                if restored_status == "DRAFT_QUOTE_VERIFIED"
                else "independent_quote_verification_required"
            ),
            actor=actor,
            idempotency_key=f"audit-replayed:{ticket['fingerprint']}",
            details={"ticket_log": str(ticket_log.resolve())},
        )
    store.resolve_dead_letter(
        category="td_ticket_audit",
        idempotency_key=str(ticket["fingerprint"]),
        actor=actor,
    )
    return {
        "ok": True,
        "ticket_id": ticket_id,
        "status": restored["status"],
        "ticket_log": str(ticket_log.resolve()),
        "system_transmitted": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workflow-db", required=True, type=Path)
    parser.add_argument("--ticket-log", required=True, type=Path)
    parser.add_argument("--ticket-id", required=True)
    parser.add_argument("--actor", required=True)
    args = parser.parse_args()
    print(
        json.dumps(
            replay(
                workflow_db=args.workflow_db,
                ticket_log=args.ticket_log,
                ticket_id=args.ticket_id,
                actor=args.actor,
            ),
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
