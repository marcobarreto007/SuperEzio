"""Approval gate — requires human approval before orders are executed."""

from __future__ import annotations

import time
import uuid
from dataclasses import asdict, dataclass
from enum import Enum
from pathlib import Path
from typing import Any

from core.trading.workflow_store import (
    TradeWorkflowStore,
    resolve_workflow_db_path,
)


class ApprovalStatus(Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"
    CANCELLED = "cancelled"


@dataclass
class ApprovalRequest:
    id: str
    symbol: str
    side: str
    qty: float
    entry_price: float
    stop_loss_price: float
    risk_amount: float
    reason: str
    status: ApprovalStatus = ApprovalStatus.PENDING
    created_at: float = 0.0
    resolved_at: float = 0.0
    resolved_by: str = ""
    ticket_id: str = ""
    ticket_fingerprint: str = ""


@dataclass
class GateConfig:
    max_auto_approve_amount: float = 500.0  # Paper mode: auto-approve up to \$500 risk
    require_approval_above_risk: float = 200.0
    ttl_seconds: float = 3600.0
    enable_email: bool = True


class ApprovalGate:
    """Manages trade approval workflow.

    Every trade above a risk threshold requires explicit human approval.
    Trades below the threshold can be auto-approved if configured.
    """

    def __init__(
        self,
        config: GateConfig | None = None,
        *,
        store: TradeWorkflowStore | None = None,
    ):
        self.config = config or GateConfig()
        self._store = store
        self._pending: dict[str, ApprovalRequest] = {}
        self._history: list[ApprovalRequest] = []
        self._next_id = 1
        if self._store is not None:
            self._restore()

    @staticmethod
    def _request_from_dict(data: dict[str, Any]) -> ApprovalRequest:
        restored = dict(data)
        restored["status"] = ApprovalStatus(str(restored.get("status") or "pending"))
        return ApprovalRequest(**restored)

    def _restore(self) -> None:
        assert self._store is not None
        for data in self._store.load_approvals():
            req = self._request_from_dict(data)
            self._history.append(req)
            if req.status == ApprovalStatus.PENDING:
                self._pending[req.id] = req

    def _persist(self, req: ApprovalRequest) -> None:
        if self._store is not None:
            self._store.save_approval(approval_request_to_dict(req))

    def submit(
        self,
        symbol: str,
        side: str,
        qty: float,
        entry_price: float,
        stop_loss_price: float,
        risk_amount: float,
        reason: str = "",
        *,
        ticket_id: str = "",
        ticket_fingerprint: str = "",
    ) -> ApprovalRequest:
        if self._store is not None and ticket_id:
            existing = self._store.get_approval_for_ticket(ticket_id)
            if existing is not None:
                return self._request_from_dict(existing)
        request_id = (
            f"apr-{ticket_fingerprint[:24]}"
            if ticket_id and ticket_fingerprint
            else f"apr-{uuid.uuid4().hex}"
            if self._store is not None
            else f"apr-{self._next_id}"
        )
        req = ApprovalRequest(
            id=request_id,
            symbol=symbol,
            side=side,
            qty=qty,
            entry_price=entry_price,
            stop_loss_price=stop_loss_price,
            risk_amount=risk_amount,
            reason=reason,
            created_at=time.time(),
            ticket_id=ticket_id,
            ticket_fingerprint=ticket_fingerprint,
        )
        self._next_id += 1

        auto_threshold = (
            self.config.max_auto_approve_amount
            if self.config.max_auto_approve_amount > 0
            else self.config.require_approval_above_risk
        )
        if risk_amount <= auto_threshold:
            req.status = ApprovalStatus.APPROVED
            req.resolved_at = time.time()
            req.resolved_by = "auto"
            self._history.append(req)
            self._persist(req)
            return req

        self._pending[req.id] = req
        self._history.append(req)
        self._persist(req)
        return req

    def approve(self, request_id: str, approver: str = "operator") -> ApprovalRequest | None:
        req = self._pending.pop(request_id, None)
        if req is None:
            return None
        req.status = ApprovalStatus.APPROVED
        req.resolved_at = time.time()
        req.resolved_by = approver
        self._persist(req)
        return req

    def reject(self, request_id: str, approver: str = "operator") -> ApprovalRequest | None:
        req = self._pending.pop(request_id, None)
        if req is None:
            return None
        req.status = ApprovalStatus.REJECTED
        req.resolved_at = time.time()
        req.resolved_by = approver
        self._persist(req)
        return req

    def expire_old(self) -> list[str]:
        now = time.time()
        expired_ids = []
        for rid, req in list(self._pending.items()):
            if now - req.created_at > self.config.ttl_seconds:
                req.status = ApprovalStatus.EXPIRED
                req.resolved_at = now
                del self._pending[rid]
                expired_ids.append(rid)
                self._persist(req)
        return expired_ids

    def get_pending(self) -> list[ApprovalRequest]:
        return list(self._pending.values())

    def get_history(self) -> list[ApprovalRequest]:
        return list(self._history)

    @property
    def pending_count(self) -> int:
        return len(self._pending)


def approval_request_to_dict(req: ApprovalRequest) -> dict:
    data = asdict(req)
    data["status"] = req.status.value
    return data


_GLOBAL_APPROVAL_GATE: ApprovalGate | None = None
_GLOBAL_APPROVAL_GATE_PATH: Path | None = None


def get_approval_gate() -> ApprovalGate:
    """Return the process-wide paper trading approval gate."""

    global _GLOBAL_APPROVAL_GATE, _GLOBAL_APPROVAL_GATE_PATH
    configured_path = resolve_workflow_db_path()
    if _GLOBAL_APPROVAL_GATE is None or _GLOBAL_APPROVAL_GATE_PATH != configured_path:
        _GLOBAL_APPROVAL_GATE = ApprovalGate(store=TradeWorkflowStore(configured_path))
        _GLOBAL_APPROVAL_GATE_PATH = configured_path
    _GLOBAL_APPROVAL_GATE.expire_old()
    return _GLOBAL_APPROVAL_GATE


def reset_approval_gate_for_test() -> ApprovalGate:
    """Reset the singleton in tests."""

    global _GLOBAL_APPROVAL_GATE, _GLOBAL_APPROVAL_GATE_PATH
    _GLOBAL_APPROVAL_GATE = ApprovalGate()
    _GLOBAL_APPROVAL_GATE_PATH = resolve_workflow_db_path()
    return _GLOBAL_APPROVAL_GATE
