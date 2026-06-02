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


def test_trace_span_decorator_callable():
    from core.observability.neural_log import trace_span

    # trace_span is a decorator factory
    assert callable(trace_span)


def test_span_context_callable():
    from core.observability.neural_log import SpanContext

    # SpanContext may be callable or a context manager
    assert callable(SpanContext) or hasattr(SpanContext, "__enter__")


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
    from core.model_serving.sanitizer import (
        _PRIVATE_CHANNEL_RE,
        strip_private_model_channels,
    )

    # _PRIVATE_CHANNEL_RE is a compiled regex pattern
    assert hasattr(_PRIVATE_CHANNEL_RE, "search")
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


def test_explain_engine_explain():
    from core.explanation.engine import ExplainEngine

    engine = ExplainEngine()
    result = engine.explain(
        {"confidence": 0.78, "passed": True, "factors": {}},
        "AAPL shows bullish momentum with RSI at 65.",
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
    from core.math.indicators import sma, ema, rsi, macd

    assert callable(sma)
    assert callable(ema)
    assert callable(rsi)
    assert callable(macd)


def test_math_sma():
    from core.math.indicators import calc_sma

    prices = [10, 12, 14, 13, 15, 16, 18, 17, 19, 20]
    result = calc_sma(prices, period=5)
    assert len(result) > 0
    assert isinstance(result[0], float) or result[0] is None


def test_math_rsi():
    from core.math.indicators import rsi

    prices = [10, 12, 14, 13, 15, 16, 18, 17, 19, 20, 18, 16, 15, 17, 19]
    result = rsi(prices, period=14)
    assert result is not None
    assert isinstance(result, (int, float))
    assert 0 <= result <= 100


def test_math_risk_metrics_import():
    from core.math.risk import (
        var_historic,
        cvar_historic,
        sharpe_ratio,
        max_drawdown,
    )

    assert callable(var_historic)
    assert callable(cvar_historic)
    assert callable(sharpe_ratio)
    assert callable(max_drawdown)


def test_math_max_drawdown():
    from core.math.risk import max_drawdown

    equity = [100, 105, 95, 90, 98, 102, 88, 92]
    mdd = max_drawdown(equity)
    assert isinstance(mdd, (int, float))


def test_math_sharpe():
    from core.math.risk import sharpe_ratio

    returns = [0.01, -0.02, 0.03, 0.01, -0.01, 0.02, 0.01]
    sharpe = sharpe_ratio(returns, risk_free_rate=0.02)
    assert isinstance(sharpe, (int, float))


def test_math_financial_engine_import():
    """Financial engine is importable as a module."""
    import core.math.financial_engine
    assert hasattr(core.math.financial_engine, "_compute_rsi")


def test_math_trading_losses_import():
    from core.math.trading_losses import directional_loss

    assert callable(directional_loss)


# ============================================================================
# Audit
# ============================================================================


def test_audit_log_import():
    from core.audit.decision_logger import DecisionLogger

    assert DecisionLogger is not None


def test_audit_record_decision():
    from core.audit.decision_logger import DecisionLogger

    logger = DecisionLogger()
    # Must not raise
    logger.record_decision(
        run_id="test-run-001",
        step="contract_test",
        decision="ALLOW",
        rationale={"reason": "testing"},
    )


# ============================================================================
# F51 Adapter
# ============================================================================


def test_f51_adapter_import():
    from core.f51_adapter.adapter import F51HubAdapter

    assert F51HubAdapter is not None


# ============================================================================
# Storage (package check)
# ============================================================================


def test_storage_module_import():
    import core.storage
    assert core.storage is not None


# ============================================================================
# Tool Registry
# ============================================================================


def test_tool_registry_import():
    from tools.custom_tools import register_custom_tools

    assert callable(register_custom_tools)


def test_tool_registry_register():
    from tools.custom_tools import register_custom_tools

    # register_custom_tools takes a registry parameter
    assert callable(register_custom_tools)


# ============================================================================
# DataHub Adapter (subprocess collector)
# ============================================================================


def test_subprocess_collector_import():
    from adapters.data_collector.subprocess_collector import SubprocessDataCollector

    assert SubprocessDataCollector is not None


# ============================================================================
# Health Probe
# ============================================================================


def test_http_probe_module_importable():
    import adapters.health

    assert adapters.health is not None
