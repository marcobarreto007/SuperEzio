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
        "quantity": 5,
        "limit_price": 100,
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


@pytest.mark.parametrize("required", [False, True, None])
def test_zero_commission_cannot_be_disabled_by_ticket_flag(required):
    with pytest.raises(TDCostGateError, match="requires commission-free"):
        normalize_td_preview_costs(
            _ticket(require_commission_free=required),
            _preview(estimated_commission=9.99, total_estimated_cost=10.05),
            actor="marco",
            now=NOW,
        )


@pytest.mark.parametrize(("spread", "accepted"), [(2.47, True), (2.48, False)])
def test_total_friction_includes_all_fees_at_half_percent_boundary(spread, accepted):
    preview = _preview(estimated_spread=spread, total_estimated_cost=round(spread + 0.03, 2))
    if accepted:
        assert normalize_td_preview_costs(_ticket(), preview, actor="marco", now=NOW)
    else:
        with pytest.raises(TDCostGateError, match="friction exceeds"):
            normalize_td_preview_costs(_ticket(), preview, actor="marco", now=NOW)


def test_missing_notional_cannot_prove_friction():
    with pytest.raises(TDCostGateError, match="ticket.quantity"):
        normalize_td_preview_costs(_ticket(quantity=None), _preview(), actor="marco", now=NOW)


def test_rounded_total_does_not_hide_excess_cost_components():
    with pytest.raises(TDCostGateError, match="friction exceeds"):
        normalize_td_preview_costs(
            _ticket(),
            _preview(estimated_spread=2.47001, total_estimated_cost=2.50),
            actor="marco",
            now=NOW,
        )


def test_tiny_commission_is_not_rounded_to_zero():
    with pytest.raises(TDCostGateError, match="requires commission-free"):
        normalize_td_preview_costs(
            _ticket(),
            _preview(estimated_commission=0.00001, total_estimated_cost=0.06001),
            actor="marco",
            now=NOW,
        )
