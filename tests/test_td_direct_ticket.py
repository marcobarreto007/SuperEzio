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
        "thesis": "Liquid Canadian bank setup with a defined entry.",
        "invalidation": "Exit if price trades through the declared stop.",
    }
    payload.update(overrides)
    return payload


def _trusted_quote(**overrides):
    quote = {
        "symbol": "TD",
        "exchange": "TSX",
        "currency": "CAD",
        "price": 109.9,
        "as_of": (NOW - timedelta(seconds=20)).isoformat(),
        "server_acquired_at": NOW.isoformat(),
        "sources": [
            {"provider": "twelve_data", "price": 109.88},
            {"provider": "finnhub", "price": 109.92},
        ],
        "source_count": 2,
        "divergence_pct": 0.0364,
        "trust": "SERVER_VERIFIED_CONSENSUS",
        "stale_fallback_used": False,
        "evidence_hash": "a" * 64,
    }
    quote.update(overrides)
    return quote


def _build(payload=None, *, quote=None, now=NOW):
    return build_td_direct_ticket(
        payload or _buy_payload(),
        trusted_quote=quote or _trusted_quote(),
        now=now,
    )


def test_build_buy_ticket_is_live_manual_and_never_transmitted():
    ticket = _build()

    assert ticket["broker"] == "TD_DIRECT_INVESTING_CANADA"
    assert ticket["execution_mode"] == "LIVE_MANUAL"
    assert ticket["submitted_to_broker"] is False
    assert ticket["transmission_capability"] is False
    assert ticket["symbol"] == "TD"
    assert ticket["planned_stop_risk"] == 25.0
    assert ticket["status"] == "DRAFT_QUOTE_VERIFIED"
    assert ticket["quote"]["trust"] == "SERVER_VERIFIED_CONSENSUS"
    assert ticket["commission"]["status"] == "NOT_LISTED"


@pytest.mark.parametrize("field", ["password", "username", "account_number", "cookie"])
def test_ticket_rejects_td_credentials_and_account_identifiers(field):
    with pytest.raises(TDDirectTicketError, match="forbidden"):
        _build(_buy_payload(**{field: "secret"}))


def test_ticket_rejects_stale_quote():
    with pytest.raises(TDDirectTicketError, match="stale"):
        _build(
            quote=_trusted_quote(as_of=(NOW - timedelta(minutes=10)).isoformat())
        )


def test_ticket_expiry_is_anchored_to_quote_timestamp():
    ticket = _build()

    assert datetime.fromisoformat(ticket["expires_at"]) == NOW + timedelta(seconds=100)


def test_ticket_rejects_risk_over_budget():
    with pytest.raises(TDDirectTicketError, match="planned stop risk.*exceeds risk budget"):
        _build(_buy_payload(quantity=100))


def test_ticket_compares_stop_risk_before_rounding():
    with pytest.raises(TDDirectTicketError, match="exceeds risk budget"):
        _build(
            _buy_payload(quantity=1, limit_price=110.005, stop_price=109.0, risk_budget=1.0),
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
        _build()


def test_ticket_rejects_market_order():
    with pytest.raises(TDDirectTicketError, match="LIMIT orders only"):
        _build(_buy_payload(order_type="MARKET"))


def test_sell_ticket_cannot_exceed_declared_position():
    payload = _buy_payload(
        side="SELL",
        quantity=11,
        position_qty=10,
        stop_price=None,
        risk_budget=None,
    )
    with pytest.raises(TDDirectTicketError, match="short selling is blocked"):
        _build(payload)


def test_append_ticket_writes_one_jsonl_record(tmp_path):
    ticket = _build()
    path = append_td_direct_ticket(ticket, tmp_path / "tickets.jsonl")

    records = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    assert records == [ticket]
    assert "password" not in records[0]


def test_append_ticket_is_idempotent_for_completed_audit(tmp_path):
    ticket = _build()
    path = tmp_path / "tickets.jsonl"
    append_td_direct_ticket(ticket, path)

    append_td_direct_ticket(ticket, path)

    assert len(path.read_text(encoding="utf-8").splitlines()) == 1


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


def test_manifest_loader_fails_closed_when_official_list_is_stale(tmp_path):
    path = tmp_path / "stale.json"
    path.write_text(
        json.dumps(
            {
                "verified_at": "2020-01-01",
                "source_url": "https://www.td.com/ca/en/investing/direct-investing/commission-free-etfs",
                "symbols": {"CAN": ["TTP"], "US": ["QQQ"]},
            }
        ),
        encoding="utf-8",
    )

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
    ticket = _build(
        payload,
        quote=_trusted_quote(
            symbol="QQQ", exchange="NASDAQ", currency="USD", price=109.9
        ),
    )
    assert ticket["commission"]["eligible"] is True
    assert ticket["commission"]["estimated_base_commission"] == 0.0


def test_ticket_blocks_unlisted_symbol_when_commission_free_is_required():
    with pytest.raises(TDDirectTicketError, match="not proven commission-free"):
        _build(_buy_payload(require_commission_free=True))


@pytest.mark.parametrize("field", ["quote_price", "quote_as_of", "quote_source"])
def test_ticket_rejects_client_supplied_quote_assertions(field):
    with pytest.raises(TDDirectTicketError, match="unsupported fields"):
        _build(_buy_payload(**{field: "forged"}))


def test_ticket_requires_trusted_server_quote():
    with pytest.raises(TDDirectTicketError, match="trusted server quote is required"):
        build_td_direct_ticket(_buy_payload(), now=NOW)


@pytest.mark.parametrize(
    ("override", "message"),
    [
        ({"source_count": 1}, "at least two"),
        ({"stale_fallback_used": True}, "stale quote fallback"),
        ({"exchange": "NYSE"}, "exchange does not match"),
        ({"currency": "USD"}, "currency does not match"),
    ],
)
def test_ticket_rejects_untrusted_quote_evidence(override, message):
    with pytest.raises(TDDirectTicketError, match=message):
        _build(quote=_trusted_quote(**override))
