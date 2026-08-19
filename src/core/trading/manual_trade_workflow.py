"""Broker-neutral workflow for human-entered, externally confirmed trades."""

from __future__ import annotations

import math
import re
from datetime import datetime, timezone
from typing import Any, Mapping

from core.trading.approval_gate import (
    ApprovalGate,
    ApprovalRequest,
    ApprovalStatus,
    GateConfig,
)
from core.trading.workflow_store import (
    TradeWorkflowStore,
    WorkflowConflictError,
    WorkflowStoreError,
)


_REQUIRED_AUTOMATED_GATES = {
    "server_side_quote",
    "money_gate",
    "portfolio_risk",
    "buying_power",
}
_CONFIRMATION_REF = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{3,99}$")


class ManualTradeWorkflowError(RuntimeError):
    """Raised when a live-manual transition is incomplete or unsafe."""


def _aware_utc(value: Any, field: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(str(value or "").replace("Z", "+00:00"))
    except ValueError as exc:
        raise ManualTradeWorkflowError(f"{field} must be an ISO-8601 datetime") from exc
    if parsed.tzinfo is None:
        raise ManualTradeWorkflowError(f"{field} must include a timezone")
    return parsed.astimezone(timezone.utc)


def _nonnegative(value: Any, field: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ManualTradeWorkflowError(f"{field} must be a non-negative number") from exc
    if not math.isfinite(number) or number < 0:
        raise ManualTradeWorkflowError(f"{field} must be a non-negative number")
    return round(number, 4)


class ManualTradeWorkflow:
    """State machine with no broker adapter, credentials, or transport capability."""

    def __init__(self, store: TradeWorkflowStore) -> None:
        self.store = store
        self.approvals = ApprovalGate(
            config=GateConfig(max_auto_approve_amount=0.0, require_approval_above_risk=0.0),
            store=store,
        )

    def _ticket(self, ticket_id: str) -> dict[str, Any]:
        ticket = self.store.get_ticket(ticket_id)
        if ticket is None:
            raise ManualTradeWorkflowError(f"unknown ticket: {ticket_id}")
        if ticket.get("transmission_capability") is not False:
            raise ManualTradeWorkflowError("manual workflow requires transmission_capability=false")
        return ticket

    def mark_gated(
        self,
        ticket_id: str,
        *,
        evidence: Mapping[str, Any],
        actor: str = "system",
    ) -> dict[str, Any]:
        """Internal transition used only after all automated gates have evidence."""

        ticket = self._ticket(ticket_id)
        missing = sorted(
            name for name in _REQUIRED_AUTOMATED_GATES if evidence.get(name) is not True
        )
        if missing:
            raise ManualTradeWorkflowError("required gates not passed: " + ", ".join(missing))
        required_gates = dict(ticket.get("required_gates") or {})
        required_gates.update({name: True for name in _REQUIRED_AUTOMATED_GATES})
        required_gates["td_order_preview"] = False
        if ticket["status"] not in {"DRAFT_UNVERIFIED_QUOTE", "DRAFT_QUOTE_VERIFIED"}:
            raise ManualTradeWorkflowError(f"ticket is not a draft: {ticket['status']}")
        return self.store.transition_ticket(
            ticket_id,
            expected_status=str(ticket["status"]),
            new_status="GATED",
            new_phase="automated_gates_passed",
            actor=actor,
            idempotency_key=f"gated:{ticket['fingerprint']}",
            details={"gate_names": sorted(_REQUIRED_AUTOMATED_GATES)},
            evidence_patch={"required_gates": required_gates},
        )

    def request_approval(self, ticket_id: str, *, actor: str = "operator") -> ApprovalRequest:
        ticket = self._ticket(ticket_id)
        if ticket["status"] not in {"GATED", "AWAITING_HUMAN"}:
            raise ManualTradeWorkflowError(f"ticket is not gated: {ticket['status']}")
        request = self.approvals.submit(
            str(ticket.get("symbol") or ticket.get("ticker") or ""),
            str(ticket.get("side") or ticket.get("action") or ""),
            float(ticket.get("quantity") or ticket.get("qty") or 0.0),
            float(ticket.get("limit_price") or 0.0),
            float(ticket.get("stop_price") or 0.0),
            float(ticket.get("planned_stop_risk") or ticket.get("risk_budget") or 0.01),
            reason="live-manual ticket requires explicit human approval",
            ticket_id=ticket_id,
            ticket_fingerprint=str(ticket["fingerprint"]),
        )
        if ticket["status"] == "GATED":
            self.store.transition_ticket(
                ticket_id,
                expected_status="GATED",
                new_status="AWAITING_HUMAN",
                new_phase="awaiting_human_approval",
                actor=actor,
                idempotency_key=f"approval-request:{request.id}",
                details={"approval_id": request.id},
            )
        return request

    def approve(self, ticket_id: str, approval_id: str, *, actor: str) -> dict[str, Any]:
        request = self.approvals.get_request(approval_id)
        if request is None or request.ticket_id != ticket_id:
            raise ManualTradeWorkflowError("approval does not belong to this ticket")
        if request.status == ApprovalStatus.PENDING:
            request = self.approvals.approve(approval_id, approver=actor)
        if request is None or request.status != ApprovalStatus.APPROVED:
            raise ManualTradeWorkflowError("approval is not approved")
        return self.store.transition_ticket(
            ticket_id,
            expected_status="AWAITING_HUMAN",
            new_status="APPROVED",
            new_phase="human_approved",
            actor=actor,
            idempotency_key=f"approval-resolved:{approval_id}:approved",
            details={"approval_id": approval_id, "resolved_by": request.resolved_by},
        )

    def reject(self, ticket_id: str, approval_id: str, *, actor: str) -> dict[str, Any]:
        request = self.approvals.get_request(approval_id)
        if request is None or request.ticket_id != ticket_id:
            raise ManualTradeWorkflowError("approval does not belong to this ticket")
        if request.status == ApprovalStatus.PENDING:
            request = self.approvals.reject(approval_id, approver=actor)
        if request is None or request.status != ApprovalStatus.REJECTED:
            raise ManualTradeWorkflowError("approval is not rejected")
        return self.store.transition_ticket(
            ticket_id,
            expected_status="AWAITING_HUMAN",
            new_status="REJECTED",
            new_phase="human_rejected",
            actor=actor,
            idempotency_key=f"approval-resolved:{approval_id}:rejected",
            details={"approval_id": approval_id, "resolved_by": request.resolved_by},
        )

    def record_manual_entry(
        self,
        ticket_id: str,
        preview: Mapping[str, Any],
        *,
        actor: str,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        ticket = self._ticket(ticket_id)
        current = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
        if ticket.get("expires_at") and current > _aware_utc(ticket["expires_at"], "expires_at"):
            raise ManualTradeWorkflowError("ticket expired before manual entry")
        if preview.get("commission_confirmed") is not True:
            raise ManualTradeWorkflowError("TD preview commission must be explicitly confirmed")
        preview_as_of = _aware_utc(preview.get("td_preview_as_of"), "td_preview_as_of")
        if abs((current - preview_as_of).total_seconds()) > 120:
            raise ManualTradeWorkflowError("TD preview is stale or future-dated")
        commission = _nonnegative(preview.get("estimated_commission"), "estimated_commission")
        spread = _nonnegative(preview.get("estimated_spread"), "estimated_spread")
        fx = _nonnegative(preview.get("estimated_fx"), "estimated_fx")
        other = _nonnegative(preview.get("estimated_other_fees", 0), "estimated_other_fees")
        total = _nonnegative(preview.get("total_estimated_cost"), "total_estimated_cost")
        if abs(total - (commission + spread + fx + other)) > 0.01:
            raise ManualTradeWorkflowError("total_estimated_cost does not match cost components")
        entry = {
            "actor": actor,
            "entered_at": current.isoformat(),
            "platform": str(preview.get("platform") or "").strip(),
            "system_transmitted": False,
            "operator_reported_submitted": True,
        }
        if entry["platform"] not in {
            "WEBBROKER",
            "TD_APP",
            "ADVANCED_DASHBOARD",
            "TD_ACTIVE_TRADER",
        }:
            raise ManualTradeWorkflowError("unsupported official TD platform")
        required_gates = dict(ticket.get("required_gates") or {})
        required_gates["td_order_preview"] = True
        normalized_preview = {
            "commission_confirmed": True,
            "estimated_commission": commission,
            "estimated_spread": spread,
            "estimated_fx": fx,
            "estimated_other_fees": other,
            "total_estimated_cost": total,
            "td_preview_as_of": preview_as_of.isoformat(),
        }
        return self.store.transition_ticket(
            ticket_id,
            expected_status="APPROVED",
            new_status="MANUALLY_ENTERED",
            new_phase="operator_reported_submission",
            actor=actor,
            idempotency_key=f"manual-entry:{ticket['fingerprint']}:{preview_as_of.isoformat()}",
            details={"platform": entry["platform"], "system_transmitted": False},
            submitted_to_broker=True,
            evidence_patch={
                "manual_entry": entry,
                "td_preview": normalized_preview,
                "costs": normalized_preview,
                "required_gates": required_gates,
            },
        )

    def record_broker_confirmation(
        self,
        ticket_id: str,
        confirmation: Mapping[str, Any],
        *,
        actor: str,
    ) -> dict[str, Any]:
        self._ticket(ticket_id)
        reference = str(confirmation.get("confirmation_ref") or "").strip()
        if not _CONFIRMATION_REF.fullmatch(reference):
            raise ManualTradeWorkflowError("broker confirmation_ref format is invalid")
        confirmed_at = _aware_utc(confirmation.get("confirmed_at"), "confirmed_at")
        evidence = {
            "actor": actor,
            "confirmation_ref": reference,
            "confirmed_at": confirmed_at.isoformat(),
            "status": str(confirmation.get("broker_status") or "").strip().upper(),
        }
        if evidence["status"] not in {"ACCEPTED", "OPEN", "FILLED", "PARTIALLY_FILLED"}:
            raise ManualTradeWorkflowError(
                "broker_status is not a recognized positive confirmation"
            )
        return self.store.transition_ticket(
            ticket_id,
            expected_status="MANUALLY_ENTERED",
            new_status="BROKER_CONFIRMED",
            new_phase="broker_confirmed",
            actor=actor,
            idempotency_key=f"broker-confirmation:{reference}",
            details=evidence,
            submitted_to_broker=True,
            evidence_patch={"broker_confirmation": evidence},
        )

    def status(self, ticket_id: str) -> dict[str, Any]:
        ticket = self._ticket(ticket_id)
        return {**ticket, "events": self.store.get_events(ticket_id)}


__all__ = [
    "ManualTradeWorkflow",
    "ManualTradeWorkflowError",
    "WorkflowConflictError",
    "WorkflowStoreError",
]
