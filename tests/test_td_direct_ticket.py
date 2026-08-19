"""Tests for fail-closed TD Direct Investing live-manual tickets."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from core.trading.td_direct_ticket import (
    TDDirectTicketError,
    append_td_direct_ticket,
    build_td_direct_ticket,
    load_td_commission_free_manifest,
    td_commission_eligibility,
)


NOW = datetime(2026, 8, 19, 2, 0, tzinfo=timezone.utc)


def _buy_payload(**overrides):
    payload = {
        "ticker": "TD.TO",
        "exchange": "TSX",
        "currency": "CAD",
        "side": "BUY",
        "quantity": 10,
        "order_type": "LIMIT",
        "limit_price": 110.0,
        "stop_price": 107.5,
        "risk_budget": 30.0,
        "account_type": "TFSA",
        "quote_price": 109.9,
        "quote_as_of": (NOW - timedelta(seconds=20)).isoformat(),
        "quote_source": "yfinance",
        "thesis": "Liquid Canadian bank setup with a defined entry.",
        "invalidation": "Exit if price trades through the declared stop.",
    }
    payload.update(overrides)
    return payload


def test_build_buy_ticket_is_live_manual_and_never_transmitted():
    ticket = build_td_direct_ticket(_buy_payload(), now=NOW)

    assert ticket["broker"] == "TD_DIRECT_INVESTING_CANADA"
    assert ticket["execution_mode"] == "LIVE_MANUAL"
    assert ticket["submitted_to_broker"] is False
    assert ticket["transmission_capability"] is False
    assert ticket["symbol"] == "TD"
    assert ticket["planned_stop_risk"] == 25.0
    assert ticket["status"] == "DRAFT_UNVERIFIED_QUOTE"
    assert ticket["commission"]["status"] == "NOT_LISTED"


@pytest.mark.parametrize("field", ["password", "username", "account_number", "cookie"])
def test_ticket_rejects_td_credentials_and_account_identifiers(field):
    with pytest.raises(TDDirectTicketError, match="forbidden"):
        build_td_direct_ticket(_buy_payload(**{field: "secret"}), now=NOW)


def test_ticket_rejects_stale_quote():
    with pytest.raises(TDDirectTicketError, match="stale"):
        build_td_direct_ticket(
            _buy_payload(quote_as_of=(NOW - timedelta(minutes=10)).isoformat()), now=NOW
        )


def test_ticket_expiry_is_anchored_to_quote_timestamp():
    ticket = build_td_direct_ticket(_buy_payload(), now=NOW)

    assert datetime.fromisoformat(ticket["expires_at"]) == NOW + timedelta(seconds=100)


def test_ticket_rejects_risk_over_budget():
    with pytest.raises(TDDirectTicketError, match="planned stop risk.*exceeds risk budget"):
        build_td_direct_ticket(_buy_payload(quantity=100), now=NOW)


def test_ticket_compares_stop_risk_before_rounding():
    with pytest.raises(TDDirectTicketError, match="exceeds risk budget"):
        build_td_direct_ticket(
            _buy_payload(quantity=1, limit_price=110.005, stop_price=109.0, risk_budget=1.0),
            now=NOW,
        )


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("SUPEREZIO_TD_TICKET_MAX_QUOTE_AGE_SEC", "not-an-int"),
        ("SUPEREZIO_TD_TICKET_MAX_LIMIT_DEVIATION_PCT", "nan"),
    ],
)
def test_ticket_rejects_invalid_safety_configuration(monkeypatch, name, value):
    monkeypatch.setenv(name, value)

    with pytest.raises(TDDirectTicketError, match=name):
        build_td_direct_ticket(_buy_payload(), now=NOW)


def test_ticket_rejects_market_order():
    with pytest.raises(TDDirectTicketError, match="LIMIT orders only"):
        build_td_direct_ticket(_buy_payload(order_type="MARKET"), now=NOW)


def test_sell_ticket_cannot_exceed_declared_position():
    payload = _buy_payload(
        side="SELL",
        quantity=11,
        position_qty=10,
        stop_price=None,
        risk_budget=None,
    )
    with pytest.raises(TDDirectTicketError, match="short selling is blocked"):
        build_td_direct_ticket(payload, now=NOW)


def test_append_ticket_writes_one_jsonl_record(tmp_path):
    ticket = build_td_direct_ticket(_buy_payload(), now=NOW)
    path = append_td_direct_ticket(ticket, tmp_path / "tickets.jsonl")

    records = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    assert records == [ticket]
    assert "password" not in records[0]


def test_append_ticket_rejects_duplicate_fingerprint(tmp_path):
    ticket = build_td_direct_ticket(_buy_payload(), now=NOW)
    path = tmp_path / "tickets.jsonl"
    append_td_direct_ticket(ticket, path)

    with pytest.raises(TDDirectTicketError, match="duplicate"):
        append_td_direct_ticket(ticket, path)


def test_official_commission_free_manifest_has_108_unique_etfs():
    manifest_path = (
        Path(__file__).resolve().parents[1] / "config" / "td_direct_commission_free_etfs.json"
    )
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    symbols = manifest["symbols"]["CAN"] + manifest["symbols"]["US"]

    assert len(manifest["symbols"]["CAN"]) == 83
    assert len(manifest["symbols"]["US"]) == 25
    assert len(symbols) == len(set(symbols)) == 108


def test_manifest_loader_fails_closed_for_invalid_data(tmp_path):
    path = tmp_path / "invalid.json"
    path.write_text('{"symbols":{"CAN":["QQQ"],"US":["QQQ"]}}', encoding="utf-8")

    with pytest.raises(TDDirectTicketError, match="unavailable or invalid"):
        load_td_commission_free_manifest(path)


def test_commission_free_eligibility_distinguishes_listed_etf_from_stock():
    assert td_commission_eligibility("QQQ", "NASDAQ")["eligible"] is True
    assert td_commission_eligibility("AAPL", "NASDAQ")["eligible"] is False


def test_ticket_can_require_proven_commission_free_symbol():
    payload = _buy_payload(
        ticker="QQQ",
        exchange="NASDAQ",
        currency="USD",
        require_commission_free=True,
    )
    ticket = build_td_direct_ticket(payload, now=NOW)
    assert ticket["commission"]["eligible"] is True
    assert ticket["commission"]["estimated_base_commission"] == 0.0


def test_ticket_blocks_unlisted_symbol_when_commission_free_is_required():
    with pytest.raises(TDDirectTicketError, match="not proven commission-free"):
        build_td_direct_ticket(_buy_payload(require_commission_free=True), now=NOW)
