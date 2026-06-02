"""Contract tests for Observability, Security, Explanation, and Math Core modules."""

from __future__ import annotations

import pytest


# ============================================================================
# Observability
# ============================================================================


def test_log_event_no_error():
    """log_event must never raise."""
    from core.observability.neural_log import log_event

    log_event("TEST_DOMAIN", "TEST_ACTION", {"key": "value"})


def test_metrics_increment():
    from core.observability.neural_log import metrics

    metrics.increment("test.contract.counter")


def test_trace_span_context_manager():
    from core.observability.neural_log import trace_span

    with trace_span("test_span"):
        pass


def test_span_context_decorator():
    from core.observability.neural_log import SpanContext

    with SpanContext("test_ctx"):
        pass


def test_observability_module_exports():
    from core.observability.neural_log import log_event, trace_span, metrics, SpanContext

    # All must be callable or usable
    assert callable(log_event)
    assert callable(trace_span)
    assert hasattr(metrics, "increment")


# ============================================================================
# Security
# ============================================================================


def test_private_channel_patterns_exist():
    from core.security.sanitizer import (
        PRIVATE_CHANNEL_PATTERNS,
        strip_private_model_channels,
    )

    assert isinstance(PRIVATE_CHANNEL_PATTERNS, (list, tuple, set))
    assert callable(strip_private_model_channels)


def test_strip_private_model_channels_noop():
    import importlib

    try:
        mod = importlib.import_module("core.model_serving.sanitizer")
        strip = mod.strip_private_model_channels
    except (ImportError, AttributeError):
        from core.security.sanitizer import strip_private_model_channels

    text = "AAPL is trading at $195.32 with strong momentum."
    result = strip(text)
    assert isinstance(result, str)
    assert len(result) > 0


# ============================================================================
# Explanation Engine
# ============================================================================


def test_explain_engine_import():
    from core.explanation.engine import ExplainEngine

    assert ExplainEngine is not None


def test_explain_engine_generate():
    from core.explanation.engine import ExplainEngine

    engine = ExplainEngine()
    result = engine.generate(
        "AAPL shows bullish momentum with RSI at 65.",
        {"confidence": 0.78, "passed": True, "factors": {}},
        "ticker_analysis",
    )
    assert isinstance(result, str)
    assert len(result) > 0


# ============================================================================
# Math Core
# ============================================================================


def test_math_utils_sigmoid():
    from core.math.utils import sigmoid

    assert 0.0 < sigmoid(0.0) < 1.0
    assert sigmoid(100) > 0.99
    assert sigmoid(-100) < 0.01
    assert sigmoid(0) == 0.5


def test_math_utils_clamp():
    from core.math.utils import clamp

    assert clamp(0.5, 0, 1) == 0.5
    assert clamp(-1, 0, 1) == 0
    assert clamp(2, 0, 1) == 1
    assert clamp(0.5) == 0.5  # default bounds [0, 1]


def test_math_utils_t_norm():
    from core.math.utils import t_norm

    # t-norm ≤ min(a, b)
    result = t_norm(0.3, 0.7)
    assert result <= 0.3
    assert result >= 0


def test_math_utils_t_conorm():
    from core.math.utils import t_conorm

    # t-conorm ≥ max(a, b)
    result = t_conorm(0.3, 0.7)
    assert result >= 0.7
    assert result <= 1.0


def test_math_indicators_import():
    from core.math.indicators import (
        calculate_sma,
        calculate_ema,
        calculate_rsi,
        calculate_macd,
    )

    assert callable(calculate_sma)
    assert callable(calculate_ema)
    assert callable(calculate_rsi)
    assert callable(calculate_macd)


def test_math_sma():
    from core.math.indicators import calculate_sma

    prices = [10, 12, 14, 13, 15, 16, 18, 17, 19, 20]
    sma = calculate_sma(prices, window=5)
    assert len(sma) > 0
    assert isinstance(sma[0], (int, float))


def test_math_rsi():
    from core.math.indicators import calculate_rsi

    prices = [10, 12, 14, 13, 15, 16, 18, 17, 19, 20, 18, 16, 15, 17, 19]
    rsi = calculate_rsi(prices, window=14)
    assert rsi is not None
    assert isinstance(rsi, (int, float))
    assert 0 <= rsi <= 100


def test_math_risk_metrics_import():
    from core.math.risk import (
        calculate_var,
        calculate_cvar,
        calculate_sharpe,
        calculate_max_drawdown,
    )

    assert callable(calculate_var)
    assert callable(calculate_cvar)
    assert callable(calculate_sharpe)
    assert callable(calculate_max_drawdown)


def test_math_max_drawdown():
    from core.math.risk import calculate_max_drawdown

    prices = [100, 105, 95, 90, 98, 102, 88, 92]
    mdd = calculate_max_drawdown(prices)
    assert isinstance(mdd, (int, float))
    assert mdd >= 0


def test_math_sharpe():
    from core.math.risk import calculate_sharpe

    returns = [0.01, -0.02, 0.03, 0.01, -0.01, 0.02, 0.01]
    sharpe = calculate_sharpe(returns, risk_free_rate=0.02)
    assert isinstance(sharpe, (int, float))


def test_math_financial_engine_import():
    from core.math.financial_engine import calculate_dcf, calculate_wacc

    assert callable(calculate_dcf)
    assert callable(calculate_wacc)


def test_math_trading_losses_import():
    from core.math.trading_losses import analyze_losses

    assert callable(analyze_losses)


# ============================================================================
# Audit
# ============================================================================


def test_audit_log_import():
    from core.audit.logger import record_decision

    assert callable(record_decision)


def test_audit_record_decision():
    from core.audit.logger import record_decision

    # Must not raise
    record_decision(
        run_id="test-run-001",
        step="contract_test",
        decision="ALLOW",
        rationale={"reason": "testing"},
    )


# ============================================================================
# F51 Adapter
# ============================================================================


def test_f51_adapter_import():
    from core.f51_adapter.bridge import F51Bridge

    assert F51Bridge is not None


# ============================================================================
# Storage (mem0)
# ============================================================================


def test_storage_mem0_import():
    from core.storage.mem0_client import Mem0Client

    assert Mem0Client is not None


# ============================================================================
# Tool Registry
# ============================================================================


def test_tool_registry_import():
    from tools.custom_tools import register_tools

    assert callable(register_tools)


def test_tool_registry_register():
    from tools.custom_tools import register_tools

    tools = register_tools()
    assert isinstance(tools, list)
    if tools:
        for tool in tools:
            assert "name" in tool or hasattr(tool, "name")


# ============================================================================
# DataHub Adapter (subprocess collector)
# ============================================================================


def test_subprocess_collector_import():
    from adapters.data_collector.subprocess_collector import SubprocessCollector

    assert SubprocessCollector is not None


# ============================================================================
# Health Probe
# ============================================================================


def test_http_probe_import():
    from adapters.health.http_probe import HttpProbe

    assert HttpProbe is not None
