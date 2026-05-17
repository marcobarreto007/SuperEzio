"""Contract tests: agent_server.endpoints — API route registration & helpers."""

import pytest
from fastapi import HTTPException


def test_router_exists():
    from agent_server.endpoints import router

    assert router is not None


def test_router_has_critical_routes():
    from agent_server.endpoints import router

    paths = {r.path for r in router.routes}
    assert "/task/submit" in paths
    assert "/capabilities" in paths
    assert "/api/chart-data/{ticker}" in paths


def test_sanitize_ticker_valid():
    from agent_server.endpoints import _sanitize_ticker

    assert _sanitize_ticker("AAPL") == "AAPL"
    assert _sanitize_ticker("aapl") == "AAPL"
    assert _sanitize_ticker(" AAPL ") == "AAPL"
    assert _sanitize_ticker("a") == "A"


def test_sanitize_ticker_invalid_raises():
    from agent_server.endpoints import _sanitize_ticker

    with pytest.raises(HTTPException):
        _sanitize_ticker("")
    with pytest.raises(HTTPException):
        _sanitize_ticker("   ")


def test_build_ohlcv():
    from agent_server.endpoints import _build_ohlcv

    candles = [
        {
            "time": "2024-01-15 10:30:00",
            "open": 150.0,
            "high": 155.0,
            "low": 149.0,
            "close": 153.0,
            "volume": 1000000,
        }
    ]
    result = _build_ohlcv(candles)
    assert isinstance(result, list)
    assert len(result) == 1
    assert result[0]["open"] == 150.0
    assert result[0]["high"] == 155.0
    assert result[0]["low"] == 149.0
    assert result[0]["close"] == 153.0
    assert result[0]["volume"] == 1000000


def test_should_include_chart_context_financial():
    from agent_server.endpoints import _should_include_chart_context

    assert _should_include_chart_context("analisar AAPL stock", "AAPL") is True
    assert _should_include_chart_context("chart of TSLA", "TSLA") is True


def test_should_include_chart_context_casual():
    from agent_server.endpoints import _should_include_chart_context

    assert _should_include_chart_context("oi tudo bem", "") is False
    assert _should_include_chart_context("hello how are you", "") is False


def test_safe_error_detail():
    from agent_server.endpoints import _safe_error_detail

    assert _safe_error_detail(Exception("test")) == "test"
    # Empty exception returns the type name as fallback
    result = _safe_error_detail(ValueError(""))
    assert isinstance(result, str) and len(result) > 0
    assert isinstance(_safe_error_detail(RuntimeError("msg")), str)


def test_get_capabilities_contract():
    """get_capabilities requires a request arg; verify signature and route metadata."""
    import inspect
    from agent_server.endpoints import get_capabilities

    sig = inspect.signature(get_capabilities)
    params = list(sig.parameters)
    assert "request" in params


def test_product_manifest_contract():
    """product_manifest requires a request arg; verify signature."""
    import inspect
    from agent_server.endpoints import product_manifest

    sig = inspect.signature(product_manifest)
    params = list(sig.parameters)
    assert "request" in params
