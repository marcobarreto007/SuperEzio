"""Test IBKRService fast path when broker is degraded.

This test validates the cockpit-degraded-fast-path fix:
- get_positions() and get_account_equity() return <0.5s when degraded
- Cache structure is returned immediately without blocking
- Cockpit endpoints pass wait_timeout=0.0 to avoid blocking
"""

from __future__ import annotations

import time


def test_ibkr_degraded_fast_path_positions():
    """Test get_positions() returns fast when service is degraded."""
    from adapters.broker.ibkr_service import IBKRService

    service = IBKRService()
    service._connected = False  # Simulate degraded state
    service._consecutive_failures = 10  # Simulate repeated failures
    service._cooldown_until = time.monotonic() + 60  # In cooldown

    start = time.monotonic()
    positions = service.get_positions()
    elapsed = time.monotonic() - start

    # Should return immediately (<0.5s) without waiting for cache
    assert elapsed < 0.5, f"get_positions() took {elapsed:.3f}s, expected <0.5s when degraded"
    assert positions == [], "Expected empty positions list when service is degraded"


def test_ibkr_degraded_fast_path_equity():
    """Test get_account_equity() returns fast when service is degraded."""
    from adapters.broker.ibkr_service import IBKRService

    service = IBKRService()
    service._connected = False  # Simulate degraded state
    service._consecutive_failures = 10  # Simulate repeated failures
    service._cooldown_until = time.monotonic() + 60  # In cooldown

    start = time.monotonic()
    equity = service.get_account_equity()
    elapsed = time.monotonic() - start

    # Should return immediately (<0.5s) without waiting for cache
    assert elapsed < 0.5, f"get_account_equity() took {elapsed:.3f}s, expected <0.5s when degraded"
    assert equity == 0.0, "Expected 0.0 equity when service is degraded"


def test_ibkr_degraded_both_methods_fast():
    """Test both get_positions() and get_account_equity() return fast when degraded."""
    from adapters.broker.ibkr_service import IBKRService

    service = IBKRService()
    service._connected = False  # Simulate degraded state
    service._consecutive_failures = 10  # Simulate repeated failures
    service._cooldown_until = time.monotonic() + 60  # In cooldown

    start = time.monotonic()
    positions = service.get_positions()
    equity = service.get_account_equity()
    elapsed = time.monotonic() - start

    # Combined calls should still return fast (<0.5s total)
    assert elapsed < 0.5, f"Combined calls took {elapsed:.3f}s, expected <0.5s when degraded"
    assert positions == [], "Expected empty positions list when service is degraded"
    assert equity == 0.0, "Expected 0.0 equity when service is degraded"


def test_ibkr_is_degraded_detects_cooldown():
    """Test is_degraded() returns True during cooldown."""
    from adapters.broker.ibkr_service import IBKRService

    service = IBKRService()
    service._connected = False  # Disconnected
    service._cooldown_until = time.monotonic() + 60  # In cooldown

    assert service.is_degraded() is True, "is_degraded() should return True during cooldown"


def test_ibkr_is_degraded_detects_disconnected():
    """Test is_degraded() returns True when disconnected."""
    from adapters.broker.ibkr_service import IBKRService

    service = IBKRService()
    service._connected = False  # Disconnected
    service._cooldown_until = 0  # No cooldown

    assert service.is_degraded() is True, "is_degraded() should return True when disconnected"


def test_ibkr_is_degraded_returns_false_when_healthy():
    """Test is_degraded() returns False when service is healthy."""
    from adapters.broker.ibkr_service import IBKRService

    service = IBKRService()
    service._connected = True  # Connected
    service._cooldown_until = 0  # No cooldown

    assert service.is_degraded() is False, "is_degraded() should return False when service is healthy"


def test_ibkr_cache_returned_when_degraded():
    """Test that existing cache is returned even when degraded."""
    from adapters.broker.ibkr_service import IBKRService

    service = IBKRService()
    # Set up cache with some data
    service._positions_cache = [
        {"symbol": "AAPL", "quantity": 100, "avg_cost": 150.0},
        {"symbol": "MSFT", "quantity": 50, "avg_cost": 300.0},
    ]
    service._equity_cache = 50000.0
    service._cache_time = time.monotonic()  # Fresh cache

    # Simulate degraded state
    service._connected = False
    service._consecutive_failures = 10
    service._cooldown_until = time.monotonic() + 60

    start = time.monotonic()
    positions = service.get_positions()
    equity = service.get_account_equity()
    elapsed = time.monotonic() - start

    assert elapsed < 0.5, f"Cache return took {elapsed:.3f}s, expected <0.5s"
    assert len(positions) == 2, f"Expected 2 cached positions, got {len(positions)}"
    assert equity == 50000.0, f"Expected cached equity 50000.0, got {equity}"


def test_ibkr_stop_event_returns_fast():
    """Test that stop_event causes immediate return without wait."""
    from adapters.broker.ibkr_service import IBKRService

    service = IBKRService()
    service._stop_event.set()  # Stop the service

    start = time.monotonic()
    positions = service.get_positions()
    equity = service.get_account_equity()
    elapsed = time.monotonic() - start

    assert elapsed < 0.5, f"Stop event path took {elapsed:.3f}s, expected <0.5s"
    assert positions == [], "Expected empty list when stop_event is set"
    assert equity == 0.0, "Expected 0.0 equity when stop_event is set"


def test_ibkr_default_wait_timeout_preserved():
    """Test that default wait_timeout=2.0 is preserved for non-degraded cases."""
    from adapters.broker.ibkr_service import IBKRService

    service = IBKRService()
    service._connected = True  # Connected but not ready
    service._cooldown_until = 0  # No cooldown
    service._cache_time = 0  # Old cache (invalid)

    # This should use default wait_timeout=2.0 (will timeout but not return immediately)
    start = time.monotonic()
    _ = service.get_positions(wait_timeout=2.0)
    elapsed = time.monotonic() - start

    # Should have waited at least close to the timeout (minus small margin for thread scheduling)
    assert elapsed >= 1.8, f"Expected wait_timeout to be respected, but took {elapsed:.3f}s"


def test_cockpit_passes_zero_wait_timeout():
    """Test that cockpit endpoints pass wait_timeout=0.0 to avoid blocking."""
    from unittest.mock import MagicMock, patch

    # Mock the IBKRService to track calls
    mock_service = MagicMock()
    mock_service.get_positions.return_value = []
    mock_service.get_account_equity.return_value = 0.0
    mock_service.get_status.return_value = {
        "connected": False,
        "can_read": False,
        "equity": "$0.00",
        "positions_count": 0,
    }

    with patch("adapters.broker.get_ibkr_service", return_value=mock_service), \
         patch("core.mission_context.mission_health_summary", return_value={}), \
         patch("core.mission_context.get_mission_equity", return_value=100000.0), \
         patch("src.agent_server.endpoints._cockpit_ibkr_open_orders", return_value=[]), \
         patch("src.agent_server.endpoints._cockpit_local_order_tickets", return_value=[]), \
         patch("src.agent_server.endpoints._cockpit_trade_history", return_value={"count": 0, "trades": [], "stats": {}}):
        from src.agent_server.endpoints import _cockpit_portfolio_snapshot

        _cockpit_portfolio_snapshot()

    # Verify that cockpit called with wait_timeout=0.0
    mock_service.get_positions.assert_called_once_with(wait_timeout=0.0)
    mock_service.get_account_equity.assert_called_once_with(wait_timeout=0.0)


def test_ibkr_cold_start_healthy_still_waits_for_first_refresh():
    """Cold-start saudavel (sem nenhuma falha) NAO ativa fast-path: wait preservado."""
    from adapters.broker.ibkr_service import IBKRService

    service = IBKRService()
    assert service._connected is False
    assert service._consecutive_failures == 0
    assert service._last_error == ""
    service._cooldown_until = 0

    start = time.monotonic()
    _ = service.get_positions(wait_timeout=1.0)
    elapsed = time.monotonic() - start

    assert elapsed >= 0.8, (
        f"Cold-start saudavel deve esperar o primeiro refresh; voltou em {elapsed:.3f}s"
    )


def test_ibkr_import_error_fast_path_without_failures():
    """ImportError seta _last_error sem incrementar failures: fast-path ativo."""
    from adapters.broker.ibkr_service import IBKRService

    service = IBKRService()
    service._connected = False
    service._consecutive_failures = 0
    service._last_error = "ib_insync not installed"

    start = time.monotonic()
    positions = service.get_positions()
    elapsed = time.monotonic() - start

    assert elapsed < 0.5
    assert positions == []
