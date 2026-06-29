"""Broker reconciliation for Bob's live paper organism.

This module is the accounting boundary between local memory and IBKR paper.
Bob can submit orders, but he can only learn from broker-confirmed state.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from .paper_journal import PaperJournal

logger = logging.getLogger(__name__)

ACTIVE_ORDER_STATUSES = {
    "",
    "api pending",
    "pending",
    "pending submit",
    "presubmitted",
    "submitted",
}


@dataclass
class ReconciliationIssue:
    severity: str
    code: str
    message: str
    ticker: str = ""
    broker_ref: str = ""
    journal_ref: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "severity": self.severity,
            "code": self.code,
            "message": self.message,
            "ticker": self.ticker,
            "broker_ref": self.broker_ref,
            "journal_ref": self.journal_ref,
        }


@dataclass
class BrokerReconciliationReport:
    timestamp: str
    positions_count: int
    open_orders_count: int
    journal_rows_count: int
    blocking: bool = False
    issues: list[ReconciliationIssue] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "positions_count": self.positions_count,
            "open_orders_count": self.open_orders_count,
            "journal_rows_count": self.journal_rows_count,
            "blocking": self.blocking,
            "issues": [issue.to_dict() for issue in self.issues],
        }


def _clean_ticker(row: dict[str, Any]) -> str:
    return str(row.get("ticker") or row.get("symbol") or "").strip().upper()


def _clean_status(value: Any) -> str:
    return str(value or "").strip().lower().replace("_", " ")


def _broker_order_ref(row: dict[str, Any]) -> str:
    return str(
        row.get("perm_id")
        or row.get("broker_perm_id")
        or row.get("order_id")
        or row.get("broker_order_id")
        or ""
    ).strip()


def _journal_order_ref(row: dict[str, Any]) -> str:
    return str(
        row.get("broker_perm_id")
        or row.get("perm_id")
        or row.get("broker_order_id")
        or row.get("order_id")
        or ""
    ).strip()


def _journal_is_broker_submitted(row: dict[str, Any]) -> bool:
    tags = {str(tag).lower() for tag in row.get("tags") or []}
    return bool(
        "broker_submitted" in tags
        or row.get("broker_order_id")
        or row.get("broker_perm_id")
        or str(row.get("source") or "").lower().startswith("ibkr")
    )


def _journal_claims_confirmed_position(row: dict[str, Any]) -> bool:
    tags = {str(tag).lower() for tag in row.get("tags") or []}
    status = _clean_status(row.get("status") or row.get("broker_order_status"))
    return bool(
        "broker_filled" in tags
        or "position_confirmed" in tags
        or row.get("broker_fill_confirmed") is True
        or status in {"filled", "open position", "position confirmed"}
    )


class BrokerReconciler:
    """Compare IBKR broker state with the local paper journal."""

    def __init__(self, journal: PaperJournal | None = None):
        self._journal = journal or PaperJournal()

    def _load_broker_state(self) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        from adapters.broker import get_ibkr_service

        service = get_ibkr_service()
        positions = service.get_positions()
        orders = service.get_open_orders()
        return positions, orders

    def reconcile(
        self,
        *,
        positions: list[dict[str, Any]] | None = None,
        open_orders: list[dict[str, Any]] | None = None,
        journal_entries: list[dict[str, Any]] | None = None,
    ) -> BrokerReconciliationReport:
        """Return a broker-vs-journal report.

        Passing explicit lists keeps this deterministic in tests. Omitting them
        reads current IBKR cached/live state.
        """
        if positions is None or open_orders is None:
            loaded_positions, loaded_orders = self._load_broker_state()
            if positions is None:
                positions = loaded_positions
            if open_orders is None:
                open_orders = loaded_orders
        if journal_entries is None:
            journal_entries = self._journal.list_all()

        positions = list(positions or [])
        open_orders = [
            order
            for order in list(open_orders or [])
            if _clean_status(order.get("status")) in ACTIVE_ORDER_STATUSES
        ]
        journal_entries = list(journal_entries or [])

        broker_order_refs = {
            ref for ref in (_broker_order_ref(order) for order in open_orders) if ref
        }
        broker_position_tickers = {
            _clean_ticker(pos)
            for pos in positions
            if _clean_ticker(pos) and float(pos.get("quantity") or pos.get("qty") or 0) != 0
        }

        issues: list[ReconciliationIssue] = []

        journal_refs = {
            ref for ref in (_journal_order_ref(entry) for entry in journal_entries) if ref
        }
        journal_open_position_tickers = {
            _clean_ticker(entry)
            for entry in journal_entries
            if _clean_ticker(entry)
            and entry.get("exit_date") is None
            and _journal_claims_confirmed_position(entry)
        }

        for order in open_orders:
            ref = _broker_order_ref(order)
            if ref and ref not in journal_refs:
                issues.append(
                    ReconciliationIssue(
                        severity="WARN",
                        code="broker_order_missing_journal",
                        message="IBKR has an open order that is not represented in PaperJournal.",
                        ticker=_clean_ticker(order),
                        broker_ref=ref,
                    )
                )

        for pos in positions:
            ticker = _clean_ticker(pos)
            if ticker and ticker not in journal_open_position_tickers:
                issues.append(
                    ReconciliationIssue(
                        severity="INFO",
                        code="broker_position_unlinked",
                        message="IBKR has a position without a confirmed local journal link.",
                        ticker=ticker,
                        broker_ref=ticker,
                    )
                )

        for entry in journal_entries:
            if entry.get("exit_date") is not None:
                continue
            ticker = _clean_ticker(entry)
            ref = _journal_order_ref(entry)

            if _journal_is_broker_submitted(entry):
                has_order = bool(ref and ref in broker_order_refs)
                has_position = ticker in broker_position_tickers
                if not has_order and not has_position:
                    issues.append(
                        ReconciliationIssue(
                            severity="BLOCK",
                            code="journal_broker_ticket_unverified",
                            message=(
                                "PaperJournal contains a broker-submitted open ticket, "
                                "but IBKR has neither matching open order nor position."
                            ),
                            ticker=ticker,
                            broker_ref=ref,
                            journal_ref=str(entry.get("trade_id") or ""),
                        )
                    )

            if _journal_claims_confirmed_position(entry) and ticker not in broker_position_tickers:
                issues.append(
                    ReconciliationIssue(
                        severity="BLOCK",
                        code="journal_position_not_in_broker",
                        message="Local journal claims a confirmed broker position that IBKR does not show.",
                        ticker=ticker,
                        broker_ref=ticker,
                        journal_ref=str(entry.get("trade_id") or ""),
                    )
                )

        blocking = any(issue.severity == "BLOCK" for issue in issues)
        report = BrokerReconciliationReport(
            timestamp=datetime.now(timezone.utc).isoformat(),
            positions_count=len(positions),
            open_orders_count=len(open_orders),
            journal_rows_count=len(journal_entries),
            blocking=blocking,
            issues=issues,
        )
        if blocking:
            logger.error("Broker reconciliation blocking issues: %s", report.to_dict())
        else:
            logger.debug("Broker reconciliation ok: %s", report.to_dict())
        return report
