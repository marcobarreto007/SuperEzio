"""Approval gate — requires human approval before orders are executed."""

from __future__ import annotations

import time
from dataclasses import dataclass
from enum import Enum


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


@dataclass
class GateConfig:
    max_auto_approve_amount: float = 0.0
    require_approval_above_risk: float = 200.0
    ttl_seconds: float = 3600.0
    enable_email: bool = True


class ApprovalGate:
    """Manages trade approval workflow.

    Every trade above a risk threshold requires explicit human approval.
    Trades below the threshold can be auto-approved if configured.
    """

    def __init__(self, config: GateConfig | None = None):
        self.config = config or GateConfig()
        self._pending: dict[str, ApprovalRequest] = {}
        self._history: list[ApprovalRequest] = []
        self._next_id = 1

    def submit(
        self,
        symbol: str,
        side: str,
        qty: float,
        entry_price: float,
        stop_loss_price: float,
        risk_amount: float,
        reason: str = "",
    ) -> ApprovalRequest:
        req = ApprovalRequest(
            id=f"apr-{self._next_id}",
            symbol=symbol,
            side=side,
            qty=qty,
            entry_price=entry_price,
            stop_loss_price=stop_loss_price,
            risk_amount=risk_amount,
            reason=reason,
            created_at=time.time(),
        )
        self._next_id += 1

        if self.config.max_auto_approve_amount > 0 and risk_amount <= self.config.max_auto_approve_amount:
            req.status = ApprovalStatus.APPROVED
            req.resolved_at = time.time()
            req.resolved_by = "auto"
            self._history.append(req)
            return req

        self._pending[req.id] = req
        self._history.append(req)
        return req

    def approve(self, request_id: str, approver: str = "operator") -> ApprovalRequest | None:
        req = self._pending.pop(request_id, None)
        if req is None:
            return None
        req.status = ApprovalStatus.APPROVED
        req.resolved_at = time.time()
        req.resolved_by = approver
        return req

    def reject(self, request_id: str, approver: str = "operator") -> ApprovalRequest | None:
        req = self._pending.pop(request_id, None)
        if req is None:
            return None
        req.status = ApprovalStatus.REJECTED
        req.resolved_at = time.time()
        req.resolved_by = approver
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
        return expired_ids

    def get_pending(self) -> list[ApprovalRequest]:
        return list(self._pending.values())

    def get_history(self) -> list[ApprovalRequest]:
        return list(self._history)

    @property
    def pending_count(self) -> int:
        return len(self._pending)
