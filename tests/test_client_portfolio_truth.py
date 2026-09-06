"""Account snapshots never substitute configured mission capital for broker data."""

from unittest.mock import MagicMock

import pytest


@pytest.mark.parametrize(
    ("connected", "balance", "expected"),
    [(False, 0, None), (False, 12000, None), (True, 0, None), (True, 1234.56, "1234.56")],
)
def test_account_equity_requires_available_broker_data(monkeypatch, connected, balance, expected):
    from agent_server import endpoints

    service = MagicMock()
    service.get_positions.return_value = []
    service.get_account_equity.return_value = balance
    service.get_status.return_value = {"connected": connected, "can_read": connected}
    monkeypatch.setattr("adapters.broker.get_ibkr_service", lambda: service)
    monkeypatch.setattr("core.mission_context.mission_health_summary", lambda: {})
    monkeypatch.setattr("core.mission_context.get_mission_equity", lambda: 100000)
    monkeypatch.setattr(endpoints, "_cockpit_ibkr_open_orders", lambda *a, **k: [])
    monkeypatch.setattr(endpoints, "_cockpit_local_order_tickets", lambda *a, **k: [])
    monkeypatch.setattr(endpoints, "_cockpit_trade_history", lambda *a, **k: {})
    result = endpoints._cockpit_portfolio_snapshot()
    assert result["equity"] == expected
    assert result["equity_source"] == ("ibkr" if expected else "unavailable")
