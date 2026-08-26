from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest
from hypothesis import given
from hypothesis import settings as hypothesis_settings
from hypothesis import strategies as st

import core.trading.canada_money_gate as money_gate_module
from core.config.settings import Settings
from core.trading.canada_money_gate import CanadaMoneyGate, CanadaMoneyGateError
from core.trading.workflow_store import TradeWorkflowStore

NOW = datetime(2026, 8, 19, 5, 0, tzinfo=UTC)


def _settings(**overrides: object) -> Settings:
    values = {
        "superezio_money_gate_snapshot_max_age_sec": 120,
        "superezio_money_gate_min_equity_cad": 1000,
        "superezio_money_gate_max_risk_pct": 0.5,
        "superezio_money_gate_max_notional_pct": 10,
        "superezio_money_gate_max_symbol_pct": 10,
        "superezio_money_gate_max_sector_pct": 25,
        "superezio_money_gate_max_non_cad_pct": 30,
        "superezio_money_gate_max_gross_pct": 100,
        "superezio_money_gate_gap_multiplier": 2,
        "superezio_money_gate_slippage_bps": 25,
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


def _ticket(ticket_id: str = "ticket-money-1", **overrides: object) -> dict[str, object]:
    ticket: dict[str, object] = {
        "ticket_id": ticket_id,
        "fingerprint": ("a" if ticket_id.endswith("1") else "b") * 64,
        "broker": "TD_DIRECT_INVESTING_CANADA",
        "status": "DRAFT_QUOTE_VERIFIED",
        "phase": "money_gate_required",
        "submitted_to_broker": False,
        "transmission_capability": False,
        "symbol": "TD",
        "currency": "CAD",
        "side": "BUY",
        "quantity": 5,
        "limit_price": 100,
        "planned_stop_risk": 10,
        "account_type": "TFSA",
    }
    ticket.update(overrides)
    return ticket


def _snapshot(**overrides: object) -> dict[str, object]:
    snapshot: dict[str, object] = {
        "account_alias": "primary_tfsa",
        "account_type": "TFSA",
        "base_currency": "CAD",
        "equity_cad": 10_000,
        "buying_power_cad": 2_000,
        "cash_cad": 10_000,
        "margin_enabled": False,
        "captured_at": (NOW - timedelta(seconds=10)).isoformat(),
        "operator": "marco",
        "source_platform": "WEBBROKER",
        "attested_from_td": True,
        "positions": [],
    }
    snapshot.update(overrides)
    return snapshot


@pytest.fixture(autouse=True)
def inactive_kill_switch(monkeypatch):
    monkeypatch.setattr(
        money_gate_module,
        "get_kill_switch",
        lambda: SimpleNamespace(check=lambda: SimpleNamespace(is_active=False)),
    )


def _stored_gate(tmp_path: Path, *tickets: dict[str, object]) -> CanadaMoneyGate:
    store = TradeWorkflowStore(tmp_path / "money.sqlite3")
    for ticket in tickets or (_ticket(),):
        store.create_ticket(ticket)
    return CanadaMoneyGate(store, settings=_settings())


def test_cad_snapshot_passes_and_reserves_buying_power(tmp_path: Path) -> None:
    gate = _stored_gate(tmp_path)

    evidence = gate.evaluate(_ticket(), _snapshot(), operator="marco", now=NOW)

    assert evidence["passed"] is True
    assert evidence["trust"] == "OPERATOR_ATTESTED_TD_SNAPSHOT_SERVER_CALCULATED"
    assert evidence["metrics"]["notional_cad"] == 500.0
    assert evidence["metrics"]["required_buying_power_cad"] == 501.25
    assert len(evidence["evidence_hash"]) == 64


@pytest.mark.parametrize("account_type", ["TFSA", "RRSP", "FHSA", "CASH", "MARGIN"])
def test_supported_canadian_account_constraints_are_explicit(
    account_type: str, tmp_path: Path
) -> None:
    ticket = _ticket(account_type=account_type)
    gate = _stored_gate(tmp_path, ticket)
    snapshot = _snapshot(
        account_alias=f"primary_{account_type.lower()}",
        account_type=account_type,
        margin_enabled=account_type == "MARGIN",
    )

    evidence = gate.evaluate(ticket, snapshot, operator="marco", now=NOW)

    assert evidence["snapshot"]["account_type"] == account_type


@pytest.mark.parametrize(
    ("snapshot", "message"),
    [
        (_snapshot(captured_at=(NOW - timedelta(minutes=3)).isoformat()), "stale"),
        (_snapshot(buying_power_cad=100), "insufficient"),
        (_snapshot(account_type="RRSP"), "does not match"),
        (_snapshot(margin_enabled=True), "cannot use margin"),
    ],
)
def test_snapshot_fails_closed(snapshot, message, tmp_path: Path) -> None:
    gate = _stored_gate(tmp_path)
    with pytest.raises(CanadaMoneyGateError, match=message):
        gate.evaluate(_ticket(), snapshot, operator="marco", now=NOW)


def test_sell_cannot_exceed_attested_position(tmp_path: Path) -> None:
    ticket = _ticket(side="SELL", quantity=6)
    gate = _stored_gate(tmp_path, ticket)
    snapshot = _snapshot(
        cash_cad=9_500,
        positions=[
            {
                "symbol": "TD",
                "quantity": 5,
                "market_value_cad": 500,
                "currency": "CAD",
                "sector": "Financials",
            }
        ],
    )

    with pytest.raises(CanadaMoneyGateError, match="SELL quantity exceeds"):
        gate.evaluate(ticket, snapshot, operator="marco", now=NOW)


def test_usd_ticket_requires_verified_fx_and_checks_currency_exposure(tmp_path: Path) -> None:
    ticket = _ticket(
        currency="USD", account_type="RRSP", quantity=10, limit_price=100, planned_stop_risk=10
    )
    gate = _stored_gate(tmp_path, ticket)
    snapshot = _snapshot(account_alias="primary_rrsp", account_type="RRSP")

    with pytest.raises(CanadaMoneyGateError, match="USD/CAD evidence is required"):
        gate.evaluate(ticket, snapshot, operator="marco", now=NOW)
    fx = {
        "pair": "USD/CAD",
        "rate": 1.4,
        "source": "BANK_OF_CANADA_VALET_FXUSDCAD",
        "stale_fallback_used": False,
        "evidence_hash": "f" * 64,
    }
    with pytest.raises(CanadaMoneyGateError, match="order_notional"):
        gate.evaluate(ticket, snapshot, operator="marco", fx_evidence=fx, now=NOW)


def test_concurrent_tickets_cannot_double_spend_buying_power(tmp_path: Path) -> None:
    first = _ticket("ticket-money-1", quantity=6)
    second = _ticket("ticket-money-2", quantity=6)
    db = tmp_path / "money.sqlite3"
    store = TradeWorkflowStore(db)
    store.create_ticket(first)
    store.create_ticket(second)
    snapshot = _snapshot(buying_power_cad=10_000)

    def run(ticket: dict[str, object]) -> str:
        try:
            CanadaMoneyGate(TradeWorkflowStore(db), settings=_settings()).evaluate(
                ticket, snapshot, operator="marco", now=NOW
            )
            return "passed"
        except CanadaMoneyGateError:
            return "blocked"

    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = list(executor.map(run, (first, second)))

    assert sorted(outcomes) == ["blocked", "passed"]


class _ReservationStore:
    def reserve_money_gate(self, *_args, **_kwargs) -> float:
        return float(_kwargs["amount_cad"])


@hypothesis_settings(max_examples=30, deadline=None)
@given(quantity=st.integers(min_value=1, max_value=20))
def test_notional_boundary_property(quantity: int) -> None:
    ticket = _ticket(quantity=quantity, planned_stop_risk=0)
    gate = CanadaMoneyGate(_ReservationStore(), settings=_settings())  # type: ignore[arg-type]
    if quantity <= 10:
        evidence = gate.evaluate(ticket, _snapshot(), operator="marco", now=NOW)
        assert evidence["metrics"]["notional_pct_equity"] <= 10
    else:
        with pytest.raises(CanadaMoneyGateError, match="order_notional"):
            gate.evaluate(ticket, _snapshot(), operator="marco", now=NOW)
