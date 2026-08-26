from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from core.trading.manual_trade_workflow import ManualTradeWorkflow, ManualTradeWorkflowError
from core.trading.workflow_store import TradeWorkflowStore

NOW = datetime(2026, 8, 19, 4, 0, tzinfo=UTC)


def _ticket(**overrides: object) -> dict[str, object]:
    ticket: dict[str, object] = {
        "ticket_id": "manual-ticket-1",
        "fingerprint": "d" * 64,
        "broker": "TD_DIRECT_INVESTING_CANADA",
        "status": "DRAFT_UNVERIFIED_QUOTE",
        "phase": "independent_quote_verification_required",
        "submitted_to_broker": False,
        "transmission_capability": False,
        "symbol": "QQQ",
        "currency": "USD",
        "side": "BUY",
        "quantity": 1,
        "limit_price": 100.0,
        "stop_price": 98.0,
        "planned_stop_risk": 2.0,
        "commission": {"eligible": False, "verified_at": "2026-08-18"},
        "require_commission_free": False,
        "expires_at": (NOW + timedelta(minutes=5)).isoformat(),
        "required_gates": {
            "server_side_quote": False,
            "money_gate": False,
            "portfolio_risk": False,
            "buying_power": False,
            "td_order_preview": False,
        },
    }
    ticket.update(overrides)
    return ticket


def _workflow(tmp_path: Path) -> ManualTradeWorkflow:
    store = TradeWorkflowStore(tmp_path / "workflow.sqlite3")
    store.create_ticket(_ticket())
    return ManualTradeWorkflow(store)


def _all_gates() -> dict[str, bool]:
    return {
        "server_side_quote": True,
        "money_gate": True,
        "portfolio_risk": True,
        "buying_power": True,
    }


def _preview(**overrides: object) -> dict[str, object]:
    preview: dict[str, object] = {
        "operator": "marco",
        "commission_confirmed": True,
        "commission_free_eligibility_confirmed": False,
        "digital_trade": True,
        "strategy_order": False,
        "td_easy_trade": False,
        "estimated_commission": 0,
        "estimated_spread": 0.02,
        "estimated_fx": 0,
        "estimated_ecn_fees": 0,
        "estimated_regulatory_fees": 0,
        "estimated_other_fees": 0,
        "total_estimated_cost": 0.02,
        "fx_conversion_required": False,
        "fx_rate": None,
        "cost_currency": "USD",
        "td_preview_as_of": NOW.isoformat(),
        "platform": "WEBBROKER",
    }
    preview.update(overrides)
    return preview


def _gate_and_preview(workflow: ManualTradeWorkflow, ticket_id: str = "manual-ticket-1") -> None:
    workflow.mark_gated(
        ticket_id,
        evidence=_all_gates(),
        evidence_records={"money_gate": {"passed": True, "evidence_hash": "f" * 64}},
    )
    workflow.record_td_preview(ticket_id, _preview(), actor="marco", now=NOW)


def test_manual_workflow_survives_restart_and_never_transports(tmp_path: Path) -> None:
    workflow = _workflow(tmp_path)
    _gate_and_preview(workflow)
    approval = workflow.request_approval("manual-ticket-1", actor="marco", now=NOW)

    restarted = ManualTradeWorkflow(TradeWorkflowStore(workflow.store.path))
    restarted.approve("manual-ticket-1", approval.id, actor="marco", now=NOW)
    entered = restarted.record_manual_entry(
        "manual-ticket-1",
        _preview(),
        actor="marco",
        now=NOW,
    )
    confirmed = ManualTradeWorkflow(
        TradeWorkflowStore(workflow.store.path)
    ).record_broker_confirmation(
        "manual-ticket-1",
        {
            "confirmation_ref": "TD-ORDER-1234",
            "confirmed_at": (NOW + timedelta(seconds=10)).isoformat(),
            "broker_status": "OPEN",
        },
        actor="marco",
    )

    assert entered["manual_entry"]["system_transmitted"] is False
    assert confirmed["status"] == "BROKER_CONFIRMED"
    assert confirmed["transmission_capability"] is False
    assert confirmed["submitted_to_broker"] is True
    assert confirmed["broker_confirmation"]["confirmation_ref"] == "TD-ORDER-1234"
    assert len(restarted.status("manual-ticket-1")["events"]) == 7


def test_cannot_request_approval_before_all_gates(tmp_path: Path) -> None:
    workflow = _workflow(tmp_path)
    with pytest.raises(ManualTradeWorkflowError, match="required gates"):
        workflow.mark_gated(
            "manual-ticket-1",
            evidence={**_all_gates(), "money_gate": False},
        )
    with pytest.raises(ManualTradeWorkflowError, match="not gated"):
        workflow.request_approval("manual-ticket-1")


def test_approval_cannot_be_used_for_another_ticket(tmp_path: Path) -> None:
    workflow = _workflow(tmp_path)
    _gate_and_preview(workflow)
    approval = workflow.request_approval("manual-ticket-1", now=NOW)
    other = _ticket(ticket_id="manual-ticket-2", fingerprint="e" * 64)
    workflow.store.create_ticket(other)
    _gate_and_preview(workflow, "manual-ticket-2")
    workflow.request_approval("manual-ticket-2", now=NOW)

    with pytest.raises(ManualTradeWorkflowError, match="does not belong"):
        workflow.approve("manual-ticket-2", approval.id, actor="marco", now=NOW)


def test_manual_entry_requires_fresh_balanced_td_preview(tmp_path: Path) -> None:
    workflow = _workflow(tmp_path)
    _gate_and_preview(workflow)
    approval = workflow.request_approval("manual-ticket-1", now=NOW)
    workflow.approve("manual-ticket-1", approval.id, actor="marco", now=NOW)

    with pytest.raises(ManualTradeWorkflowError, match="does not match"):
        workflow.record_manual_entry(
            "manual-ticket-1",
            _preview(total_estimated_cost=99),
            actor="marco",
            now=NOW,
        )

    with pytest.raises(ManualTradeWorkflowError, match="changed after approval"):
        workflow.record_manual_entry(
            "manual-ticket-1",
            _preview(estimated_spread=0.04, total_estimated_cost=0.04),
            actor="marco",
            now=NOW,
        )


def test_broker_confirmation_requires_reference(tmp_path: Path) -> None:
    workflow = _workflow(tmp_path)
    with pytest.raises(ManualTradeWorkflowError, match="confirmation_ref"):
        workflow.record_broker_confirmation(
            "manual-ticket-1",
            {"confirmation_ref": "", "confirmed_at": NOW.isoformat(), "broker_status": "OPEN"},
            actor="marco",
        )
