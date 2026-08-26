from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from core.trading.td_cost_gate import TDCostGateError, normalize_td_preview_costs

NOW = datetime(2026, 8, 19, 5, 30, tzinfo=UTC)


def _ticket(**overrides: object) -> dict[str, object]:
    ticket: dict[str, object] = {
        "fingerprint": "a" * 64,
        "currency": "CAD",
        "commission": {
            "eligible": True,
            "verified_at": "2026-08-18",
            "source_url": "https://www.td.com/official",
        },
        "require_commission_free": False,
    }
    ticket.update(overrides)
    return ticket


def _preview(**overrides: object) -> dict[str, object]:
    preview: dict[str, object] = {
        "commission_confirmed": True,
        "commission_free_eligibility_confirmed": True,
        "digital_trade": True,
        "strategy_order": False,
        "td_easy_trade": False,
        "estimated_commission": 0,
        "estimated_spread": 0.03,
        "estimated_fx": 0,
        "estimated_ecn_fees": 0.01,
        "estimated_regulatory_fees": 0.02,
        "estimated_other_fees": 0,
        "total_estimated_cost": 0.06,
        "fx_conversion_required": False,
        "fx_rate": None,
        "cost_currency": "CAD",
        "td_preview_as_of": (NOW - timedelta(seconds=10)).isoformat(),
        "platform": "WEBBROKER",
    }
    preview.update(overrides)
    return preview


def test_preview_hash_covers_all_economic_costs() -> None:
    result = normalize_td_preview_costs(_ticket(), _preview(), actor="marco", now=NOW)

    assert result["total_estimated_cost"] == 0.06
    assert result["estimated_ecn_fees"] == 0.01
    assert result["estimated_regulatory_fees"] == 0.02
    assert len(result["evidence_hash"]) == 64


@pytest.mark.parametrize(
    ("override", "message"),
    [
        ({"strategy_order": True}, "strategy orders"),
        ({"td_easy_trade": True}, "Easy Trade"),
        ({"digital_trade": False}, "digital TD trade"),
        ({"td_preview_as_of": (NOW - timedelta(minutes=3)).isoformat()}, "stale"),
        ({"cost_currency": "USD"}, "cost_currency"),
        ({"total_estimated_cost": 99}, "all cost components"),
    ],
)
def test_preview_conditions_fail_closed(override, message) -> None:
    with pytest.raises(TDCostGateError, match=message):
        normalize_td_preview_costs(_ticket(), _preview(**override), actor="marco", now=NOW)


def test_usd_conversion_requires_rate_and_explicit_fx_cost() -> None:
    ticket = _ticket(currency="USD", commission={"eligible": False})
    preview = _preview(
        cost_currency="USD",
        commission_free_eligibility_confirmed=False,
        estimated_fx=1.25,
        fx_conversion_required=True,
        fx_rate=1.36,
        total_estimated_cost=1.31,
    )

    result = normalize_td_preview_costs(ticket, preview, actor="marco", now=NOW)

    assert result["fx_rate"] == 1.36
    assert result["estimated_fx"] == 1.25


def test_required_commission_free_ticket_blocks_unexpected_commission() -> None:
    with pytest.raises(TDCostGateError, match="requires commission-free"):
        normalize_td_preview_costs(
            _ticket(require_commission_free=True),
            _preview(estimated_commission=9.99, total_estimated_cost=10.05),
            actor="marco",
            now=NOW,
        )
