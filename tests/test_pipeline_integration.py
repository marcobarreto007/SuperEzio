"""Integration tests for the pipeline -- MathHub, observation_builder, builder, contracts.

These tests mock external dependencies and do NOT require a live server.
Coverage target: math_hub, observation_builder, builder, contracts.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

import pytest

from core.math.math_hub import MathHub
from core.pipeline.nodes.observation_builder import (
    build_observations,
    format_math_report,
    format_f51_verdict,
    format_neural_decision,
    format_sdca,
    format_guardrail_hub,
    format_decision_trace,
    format_pennylab,
)
from core.pipeline.prompts.builder import build_agent_prompt


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _sample_ohlcv(
    days: int = 30, start_price: float = 10.0, trend: float = 0.2
) -> list[dict[str, Any]]:
    """Generate synthetic OHLCV candles with a steady uptrend."""
    candles: list[dict[str, Any]] = []
    start = date(2026, 1, 1)
    for i in range(days):
        close = round(start_price + i * trend, 2)
        candles.append(
            {
                "open": round(close - 0.1, 2),
                "high": round(close + 0.2, 2),
                "low": round(close - 0.2, 2),
                "close": close,
                "volume": 100_000 + i * 1_000,
                "date": (start + timedelta(days=i)).isoformat(),
            }
        )
    return candles


def _mock_math_state() -> dict[str, Any]:
    """Synthetic state with 60-day OHLCV data for MathHub tests."""
    candles = _sample_ohlcv(60, start_price=150.0, trend=0.5)
    return {
        "run_id": "test-math-hub-integration",
        "ticker": "AAPL",
        "data": {
            "ticker": "AAPL",
            "price": {"current": candles[-1]["close"]},
            "ohlcv": candles,
            "profile": {
                "free_cash_flow": 100_000_000,
                "shares_outstanding": 1_000_000,
                "growth_rate": 0.05,
                "discount_rate": 0.10,
            },
        },
    }


def _mock_pipeline_state(**overrides: Any) -> dict[str, Any]:
    """Synthetic PipelineState dict with all key sections populated.

    Includes pre-computed math_report, f51_verdict, expert_summary,
    sdca_firewall, guardrail_hub, decision_trace, pennylab_result,
    neural_decision, and basic identity fields.
    """
    state: dict[str, Any] = {
        "run_id": "test-pipeline-integration",
        "session_id": "session-001",
        "ticker": "AAPL",
        "message": "What do you think about AAPL?",
        "route": "ticker_analysis",
        "intent": "ticker_analysis",
        "action": "analyze",
        "intent_confidence": 0.95,
        "data_context": "AAPL reported strong Q2 earnings. Revenue grew 8% YoY.",
        "expert_summary": (
            "Fundamental: BULLISH (confidence 0.75) -- strong revenue growth, expanding margins. "
            "Technical: NEUTRAL (confidence 0.60) -- RSI at 55, no clear trend. "
            "Risk: LOW (confidence 0.80) -- VaR within normal bounds."
        ),
        "errors": [],
    }

    # Inject 60-day OHLCV data for MathHub
    candles = _sample_ohlcv(60, start_price=150.0, trend=0.5)
    state["data"] = {
        "ticker": "AAPL",
        "price": {"current": candles[-1]["close"]},
        "ohlcv": candles,
        "profile": {
            "free_cash_flow": 100_000_000,
            "shares_outstanding": 1_000_000,
        },
    }

    # Pre-compute math_report via MathHub (no network needed -- uses synthetic data)
    state["math_report"] = MathHub().calculate_all(state)
    # Pre-compute math_prompt from math_report (injected separately as a compact block)
    state["math_prompt"] = MathHub.to_deepseek_prompt(state["math_report"])

    # F51 Verdict
    state["f51_verdict"] = {
        "score": 0.72,
        "passed": True,
        "decision_score": 0.72,
        "factors": {"momentum": 0.6, "value": 0.8, "sentiment": 0.7},
    }

    # SDCA Firewall
    state["sdca_firewall"] = {
        "decision": "ALLOW",
        "risk_level": "low",
        "cognitive_checks": 5,
        "total_checks": 5,
        "reason": "No cognitive biases detected.",
    }

    # Guardrail Hub
    state["guardrail_hub"] = {
        "summary": {
            "completed": 28,
            "total": 30,
            "decision_counts": {"ALLOW": 25, "BLOCK": 2, "REVIEW": 1},
            "blocking_guardrails": ["market_cap_check"],
        }
    }

    # Decision Trace
    state["decision_trace"] = {
        "decision": "ALLOW",
        "confidence": 0.85,
        "model": "llama.cpp",
        "path": ["Intent classified", "Data collected", "F51 evaluated", "SDCA passed"],
    }

    # PennyLab
    state["pennylab_result"] = {
        "signal": "CLEAN",
        "score": 0.92,
        "decision": "approve",
        "details": "No manipulation patterns detected. Volume patterns normal.",
    }

    # Neural Decision
    state["neural_decision"] = {
        "regime": "bullish",
        "direction": "UP",
        "confidence": 0.65,
        "recommendation": "accumulate",
        "drawdown_risk": -12.5,
    }

    # Apply overrides (allows test-specific customization)
    state.update(overrides)
    return state


# ===========================================================================
# 1. MathHub with mock data
# ===========================================================================


class TestMathHubWithMockData:
    """MathHub processes synthetic OHLCV data and computes all indicators."""

    def test_math_hub_calculates_rsi(self):
        """RSI must be a float between 0 and 100."""
        report = MathHub().calculate_all(_mock_math_state())
        rsi_val = report["numbers"].get("rsi")
        assert rsi_val is not None, "RSI should be computed"
        assert isinstance(rsi_val, (int, float)), "RSI should be numeric"
        assert 0 <= rsi_val <= 100, f"RSI out of range: {rsi_val}"

    def test_math_hub_calculates_macd(self):
        """MACD must be computed from price closes (returns dict with macd/signal/histogram)."""
        report = MathHub().calculate_all(_mock_math_state())
        macd_val = report["numbers"].get("macd")
        assert macd_val is not None, "MACD should be computed"
        assert isinstance(macd_val, dict), "MACD should be a dict with macd/signal/histogram"
        assert isinstance(macd_val.get("macd"), (int, float)), "MACD inner value should be numeric"

    def test_math_hub_calculates_sharpe(self):
        """Sharpe ratio must be computed from return series."""
        report = MathHub().calculate_all(_mock_math_state())
        sharpe = report["summary"].get("sharpe")
        assert sharpe is not None, "Sharpe ratio should be computed"
        assert isinstance(sharpe, (int, float)), "Sharpe should be numeric"

    def test_math_hub_calculates_var(self):
        """Value at Risk (VaR) 95% must be computed from returns."""
        report = MathHub().calculate_all(_mock_math_state())
        var95 = report["numbers"].get("var_95")
        assert var95 is not None, "VaR_95 should be computed"
        assert isinstance(var95, (int, float)), "VaR_95 should be numeric"

    def test_math_hub_calculates_kelly(self):
        """Kelly fraction module must be present (needs both wins and losses)."""
        report = MathHub().calculate_all(_mock_math_state())
        assert "kelly" in report["modules"], "Kelly module should exist"
        # Kelly may be skipped if all returns are same sign -- that is OK
        # The module presence is the contract check

    def test_math_hub_report_has_all_top_level_keys(self):
        """The math_report dict must have all expected structural keys."""
        report = MathHub().calculate_all(_mock_math_state())
        assert "ticker" in report
        assert "status" in report
        assert "modules" in report
        assert "summary" in report
        assert "numbers" in report
        assert "coverage" in report
        assert report["ticker"] == "AAPL"

    def test_math_hub_report_has_all_14_modules(self):
        """All 14 module keys must be present in the report."""
        report = MathHub().calculate_all(_mock_math_state())
        expected_modules = {
            "price_series",
            "technical_indicators",
            "return_metrics",
            "sharpe_sortino",
            "drawdown",
            "var_cvar",
            "kelly",
            "dcf_proxy",
            "crisis_aggregate",
            "return_bootstrap",
            "portfolio_hrp",
            "f51_unified",
            "penny_momentum",
            "trading_losses",
        }
        missing = expected_modules - set(report["modules"].keys())
        assert not missing, f"Missing modules: {missing}"

    def test_math_hub_summary_includes_expected_fields(self):
        """Summary must include latest_price, sharpe, max_drawdown, var_95."""
        report = MathHub().calculate_all(_mock_math_state())
        summary = report["summary"]
        assert "latest_price" in summary
        assert "return_annualized" in summary
        assert "sharpe" in summary
        assert "max_drawdown" in summary
        assert "var_95" in summary

    def test_math_hub_latest_price(self):
        """Latest price must match the last close from our synthetic data."""
        report = MathHub().calculate_all(_mock_math_state())
        expected_price = round(150.0 + 59 * 0.5, 2)  # 179.5
        assert report["summary"]["latest_price"] == pytest.approx(expected_price, rel=0.01)

    def test_math_hub_handles_minimal_data(self):
        """MathHub must return a partial report even with minimal price data."""
        minimal_state = {
            "ticker": "TEST",
            "data": {
                "prices": [100.0, 101.0, 102.0, 101.5, 103.0],
            },
        }
        report = MathHub().calculate_all(minimal_state)
        assert report["coverage"]["total_modules"] == 14
        assert report["modules"]["price_series"]["status"] == "ok"

    def test_math_hub_handles_empty_state_gracefully(self):
        """An empty state must not crash MathHub -- returns partial/error."""
        report = MathHub().calculate_all({})
        assert report["status"] in ("partial", "error")
        assert report["coverage"]["total_modules"] == 14

    def test_math_hub_technical_indicators_module_ok(self):
        """Technical indicators module must succeed with 60 price points."""
        report = MathHub().calculate_all(_mock_math_state())
        assert report["modules"]["technical_indicators"]["status"] == "ok"
        tech_values = report["modules"]["technical_indicators"].get("values", {})
        assert "sma20" in tech_values
        assert "sma50" in tech_values
        assert "ema20" in tech_values
        assert "rsi14" in tech_values
        assert "macd" in tech_values

    def test_math_hub_var_cvar_module_ok(self):
        """VaR and CVaR must compute with a return series present."""
        report = MathHub().calculate_all(_mock_math_state())
        assert report["modules"]["var_cvar"]["status"] == "ok"
        var_values = report["modules"]["var_cvar"].get("values", {})
        assert "var_95" in var_values
        assert "cvar_95" in var_values

    def test_math_hub_sharpe_sortino_module_ok(self):
        """Sharpe and Sortino must compute with sufficient returns."""
        report = MathHub().calculate_all(_mock_math_state())
        assert report["modules"]["sharpe_sortino"]["status"] == "ok"
        sharpe_values = report["modules"]["sharpe_sortino"].get("values", {})
        assert "volatility" in sharpe_values
        assert "sharpe" in sharpe_values
        assert "sortino" in sharpe_values

    def test_math_hub_dcf_proxy_ok(self):
        """DCF module must succeed when FCF and shares data are provided."""
        report = MathHub().calculate_all(_mock_math_state())
        assert report["modules"]["dcf_proxy"]["status"] == "ok"

    def test_math_hub_f51_unified_skipped_pre_experts(self):
        """F51 module must be skipped (pre-expert stage) unless f51_verdict present."""
        report = MathHub().calculate_all(_mock_math_state())
        assert report["modules"]["f51_unified"]["status"] == "skipped"
        assert "f51_verdict_not_available" in report["modules"]["f51_unified"]["reason"]


# ===========================================================================
# 2. Observation Builder formats
# ===========================================================================


class TestObservationBuilderFormats:
    """Observation builder converts JSON pipeline state into formatted text.

    All format_*() functions must return plain text (not JSON) with the
    expected section headers.
    """

    def test_build_observations_returns_list_of_strings(self):
        """build_observations must produce a list of non-empty strings."""
        state = _mock_pipeline_state()
        obs = build_observations(state)
        assert isinstance(obs, list)
        assert len(obs) > 0, "Should have at least one observation"
        for item in obs:
            assert isinstance(item, str), f"Each observation should be str, got {type(item)}"
            assert len(item) > 0, "Observations should not be empty"

    def test_observations_contain_math_report_header(self):
        """Observations must include the '═══ MATH REPORT ═══' header."""
        state = _mock_pipeline_state()
        obs = build_observations(state)
        all_text = "\n".join(obs)
        assert "═══ MATH REPORT ═══" in all_text

    def test_observations_contain_f51_verdict_header(self):
        """Observations must include the '═══ F51 VERDICT ═══' header."""
        state = _mock_pipeline_state()
        obs = build_observations(state)
        all_text = "\n".join(obs)
        assert "═══ F51 VERDICT ═══" in all_text

    def test_observations_contain_expert_summary(self):
        """Observations must include the expert committee summary text."""
        state = _mock_pipeline_state()
        obs = build_observations(state)
        all_text = "\n".join(obs)
        assert "Expert Committee Summary:" in all_text

    def test_observations_contain_system_status(self):
        """Observations must include the SYSTEM STATUS section."""
        state = _mock_pipeline_state()
        obs = build_observations(state)
        all_text = "\n".join(obs)
        assert "SYSTEM STATUS:" in all_text

    def test_observations_contain_ticker_status(self):
        """Observations must include current ticker and DATA AVAILABLE status."""
        state = _mock_pipeline_state()
        obs = build_observations(state)
        all_text = "\n".join(obs)
        assert "Current Ticker: AAPL" in all_text
        assert "DATA AVAILABLE" in all_text

    def test_observations_contain_math_analysis_block(self):
        """Observations must include Math Analysis (RSI, MACD, Sharpe) block."""
        state = _mock_pipeline_state()
        obs = build_observations(state)
        all_text = "\n".join(obs)
        assert "Math Analysis (RSI, MACD, Sharpe, VaR, Kelly):" in all_text

    def test_format_math_report_returns_plain_text(self):
        """format_math_report must return plain text, not JSON."""
        report = _mock_pipeline_state()["math_report"]
        text = format_math_report(report)
        assert isinstance(text, str)
        assert len(text) > 0
        assert "═══ MATH REPORT ═══" in text
        # Verify the output is not raw multi-line JSON
        assert not text.startswith("{"), "Should not start with JSON object"

    def test_format_math_report_contains_ticker(self):
        """format_math_report must include the ticker symbol."""
        report = _mock_pipeline_state()["math_report"]
        text = format_math_report(report)
        assert "Ticker:" in text
        assert "AAPL" in text

    def test_format_f51_verdict_returns_plain_text(self):
        """format_f51_verdict must return plain text with header."""
        f51 = _mock_pipeline_state()["f51_verdict"]
        text = format_f51_verdict(f51)
        assert isinstance(text, str)
        assert "═══ F51 VERDICT ═══" in text
        assert "score=" in text

    def test_format_neural_decision_returns_plain_text(self):
        """format_neural_decision must return plain text with header."""
        neural = {
            "regime": "bullish",
            "direction": "UP",
            "confidence": 0.65,
        }
        text = format_neural_decision(neural)
        assert isinstance(text, str)
        assert "═══ NEURAL DECISION ═══" in text
        assert "Regime: bullish" in text

    def test_format_sdca_returns_plain_text(self):
        """format_sdca must return plain text with header."""
        sdca = {"decision": "ALLOW", "risk_level": "low"}
        text = format_sdca(sdca)
        assert isinstance(text, str)
        assert "═══ SDCA FIREWALL ═══" in text
        assert "ALLOW" in text

    def test_format_guardrail_hub_returns_plain_text(self):
        """format_guardrail_hub must return plain text with header."""
        guardrail = {
            "summary": {
                "completed": 28,
                "total": 30,
                "decision_counts": {"ALLOW": 25, "BLOCK": 2, "REVIEW": 1},
            }
        }
        text = format_guardrail_hub(guardrail)
        assert isinstance(text, str)
        assert "═══ GUARDRAIL HUB ═══" in text
        assert "28/30" in text

    def test_format_decision_trace_returns_plain_text(self):
        """format_decision_trace must return plain text with header."""
        trace = {"decision": "ALLOW", "confidence": 0.85, "model": "llama.cpp"}
        text = format_decision_trace(trace)
        assert isinstance(text, str)
        assert "═══ DECISION TRACE ═══" in text
        assert "llama.cpp" in text

    def test_format_pennylab_returns_plain_text(self):
        """format_pennylab must return plain text with header."""
        pennylab = {"signal": "CLEAN", "score": 0.92}
        text = format_pennylab(pennylab)
        assert isinstance(text, str)
        assert "═══ PENNYLAB RESULT ═══" in text

    def test_observations_without_math_report_graceful(self):
        """build_observations must handle missing math_report without crash."""
        state = _mock_pipeline_state()
        state.pop("math_report", None)
        obs = build_observations(state)
        all_text = "\n".join(obs)
        assert "═══ MATH REPORT ═══" not in all_text
        assert "═══ F51 VERDICT ═══" in all_text  # Still present

    def test_observations_without_f51_verdict_graceful(self):
        """build_observations must handle missing f51_verdict without crash."""
        state = _mock_pipeline_state()
        state.pop("f51_verdict", None)
        obs = build_observations(state)
        all_text = "\n".join(obs)
        assert "═══ F51 VERDICT ═══" not in all_text
        assert "═══ MATH REPORT ═══" in all_text  # Still present

    def test_observations_contain_sdca_firewall_section(self):
        """Observations must include SDCA firewall when present."""
        state = _mock_pipeline_state()
        obs = build_observations(state)
        all_text = "\n".join(obs)
        assert "═══ SDCA FIREWALL ═══" in all_text

    def test_observations_contain_guardrail_hub_section(self):
        """Observations must include guardrail hub when present."""
        state = _mock_pipeline_state()
        obs = build_observations(state)
        all_text = "\n".join(obs)
        assert "═══ GUARDRAIL HUB ═══" in all_text

    def test_observations_contain_decision_trace_section(self):
        """Observations must include decision trace when present."""
        state = _mock_pipeline_state()
        obs = build_observations(state)
        all_text = "\n".join(obs)
        assert "═══ DECISION TRACE ═══" in all_text

    def test_observations_contain_pennylab_section(self):
        """Observations must include pennylab result when present."""
        state = _mock_pipeline_state()
        obs = build_observations(state)
        all_text = "\n".join(obs)
        assert "═══ PENNYLAB RESULT ═══" in all_text

    def test_observations_contain_neural_decision_section(self):
        """Observations must include neural decision when present."""
        state = _mock_pipeline_state()
        obs = build_observations(state)
        all_text = "\n".join(obs)
        assert "═══ NEURAL DECISION ═══" in all_text

    def test_observations_contain_data_context(self):
        """Observations must include the data/scan context section."""
        state = _mock_pipeline_state()
        obs = build_observations(state)
        all_text = "\n".join(obs)
        assert "Data/Scan Context" in all_text


# ===========================================================================
# 3. Build Agent Prompt
# ===========================================================================


class TestBuildAgentPrompt:
    """build_agent_prompt constructs the full CEO prompt from pipeline state."""

    def test_build_agent_prompt_contains_pipeline_obligation(self):
        """The prompt must include PIPELINE_OBLIGATION."""
        state = _mock_pipeline_state()
        prompt = build_agent_prompt(state)
        assert "PIPELINE_OBLIGATION" in prompt

    def test_build_agent_prompt_contains_math_report_section(self):
        """The prompt must have a MATH_REPORT section."""
        state = _mock_pipeline_state()
        prompt = build_agent_prompt(state)
        assert "MATH_REPORT" in prompt

    def test_build_agent_prompt_contains_f51_verdict(self):
        """The prompt must reference F51_VERDICT."""
        state = _mock_pipeline_state()
        prompt = build_agent_prompt(state)
        assert "F51_VERDICT" in prompt

    def test_build_agent_prompt_contains_expert_section(self):
        """The prompt must have an EXPERTS section."""
        state = _mock_pipeline_state()
        prompt = build_agent_prompt(state)
        assert "EXPERTS" in prompt

    def test_build_agent_prompt_contains_critical_output_requirement(self):
        """The prompt must include CRITICAL_OUTPUT_REQUIREMENT."""
        state = _mock_pipeline_state()
        prompt = build_agent_prompt(state)
        assert "CRITICAL_OUTPUT_REQUIREMENT" in prompt

    def test_build_agent_prompt_includes_task_and_intent(self):
        """The prompt must include the user's original task and intent."""
        state = _mock_pipeline_state(message="Analyze AAPL for me")
        prompt = build_agent_prompt(state)
        assert "Analyze AAPL for me" in prompt
        assert "ticker_analysis" in prompt

    def test_build_agent_prompt_handles_minimal_state(self):
        """build_agent_prompt must handle a state with minimal data without crash."""
        state = _mock_pipeline_state(
            ticker="",
            message="Hi there",
            route="general",
            intent="general_question",
            math_report={},
            f51_verdict={},
            expert_summary="",
            data_context="",
        )
        prompt = build_agent_prompt(state)
        assert isinstance(prompt, str)
        assert len(prompt) > 0

    def test_build_agent_prompt_handles_greeting(self):
        """build_agent_prompt must handle a plain greeting without financial data."""
        state = _mock_pipeline_state(
            ticker="",
            message="Oi, tudo bem?",
            route="general",
            intent="general_question",
            math_report={},
            f51_verdict={},
            expert_summary="",
            data_context="",
            neural_decision={},
            pennylab_result={},
        )
        prompt = build_agent_prompt(state)
        assert isinstance(prompt, str)
        assert len(prompt) > 0

    def test_build_agent_prompt_contains_language_instruction(self):
        """The prompt must include the LANGUAGE instruction."""
        state = _mock_pipeline_state()
        prompt = build_agent_prompt(state)
        assert "LANGUAGE" in prompt

    def test_build_agent_prompt_contains_mandatory_format(self):
        """The prompt must include the MANDATORY FORMAT block."""
        state = _mock_pipeline_state()
        prompt = build_agent_prompt(state)
        assert "MANDATORY FORMAT" in prompt or "MANDATORY_OUTPUT" in prompt

    def test_build_agent_prompt_includes_horizon(self):
        """The prompt must include a timeframe/horizon constraint."""
        state = _mock_pipeline_state()
        prompt = build_agent_prompt(state)
        assert "horizon" in prompt.lower() or "CRITICAL_TIMEFRAME" in prompt

    def test_build_agent_prompt_contains_rules_block(self):
        """The prompt must include the RULES section."""
        state = _mock_pipeline_state()
        prompt = build_agent_prompt(state)
        assert "RULES" in prompt

    def test_build_agent_prompt_renders_sdca_when_present(self):
        """The prompt must include SDCA_FIREWALL when state has sdca_firewall."""
        state = _mock_pipeline_state()
        prompt = build_agent_prompt(state)
        assert "SDCA_FIREWALL" in prompt

    def test_build_agent_prompt_renders_pennylab_when_present(self):
        """The prompt must include PENNYLAB when state has pennylab data."""
        state = _mock_pipeline_state()
        prompt = build_agent_prompt(state)
        assert "PENNYLAB" in prompt

    def test_build_agent_prompt_renders_neural_when_present(self):
        """The prompt must include NEURAL_DECISION when state has neural data."""
        state = _mock_pipeline_state()
        prompt = build_agent_prompt(state)
        assert "NEURAL_DECISION" in prompt

    def test_build_agent_prompt_output_section_headers(self):
        """The prompt's CRITICAL_OUTPUT_REQUIREMENT must list expected headers."""
        state = _mock_pipeline_state()
        prompt = build_agent_prompt(state)
        assert "## DATA" in prompt
        assert "## F51_VERDICT" in prompt
        assert "## EXPERTS" in prompt
        assert "## MATH_REPORT" in prompt


# ===========================================================================
# 4. Pipeline State Contract
# ===========================================================================


class TestPipelineStateContract:
    """PipelineState TypedDict contract validation.

    PipelineState is a TypedDict(total=False), so no field is technically
    required at runtime. These tests validate the structural contract:
    documented fields exist in the type annotations.
    """

    def test_pipeline_state_has_expected_fields(self):
        """PipelineState must have all documented core fields."""
        from core.pipeline.contracts import PipelineState

        annotations = PipelineState.__annotations__
        expected_fields = {
            "run_id",
            "session_id",
            "message",
            "context",
            "route",
            "intent",
            "action",
            "ticker",
            "filters",
            "cognitive_mode",
            "math_report",
            "f51_verdict",
            "expert_summary",
            "data",
            "data_context",
            "final",
            "errors",
        }
        missing = expected_fields - set(annotations.keys())
        assert not missing, f"Missing PipelineState fields: {missing}"

    def test_pipeline_state_has_pennylab_field(self):
        """PipelineState must include pennylab_result."""
        from core.pipeline.contracts import PipelineState

        annotations = PipelineState.__annotations__
        assert "pennylab_result" in annotations

    def test_pipeline_state_has_sdca_fields(self):
        """PipelineState must include sdca_firewall and sdca_blocked."""
        from core.pipeline.contracts import PipelineState

        annotations = PipelineState.__annotations__
        assert "sdca_firewall" in annotations
        assert "sdca_blocked" in annotations

    def test_pipeline_state_has_orchestrator_fields(self):
        """PipelineState must include orchestrator output fields."""
        from core.pipeline.contracts import PipelineState

        annotations = PipelineState.__annotations__
        for field in ("intent_confidence", "intent_source", "entities"):
            assert field in annotations, f"Missing field: {field}"

    def test_pipeline_state_has_expert_and_trinity_fields(self):
        """PipelineState must include expert_results and trinity fields."""
        from core.pipeline.contracts import PipelineState

        annotations = PipelineState.__annotations__
        assert "expert_results" in annotations
        assert "expert_summary" in annotations
        assert "trinity_report" in annotations
        assert "trinity_blocked" in annotations

    def test_pipeline_state_has_rag_field(self):
        """PipelineState must include rag_context."""
        from core.pipeline.contracts import PipelineState

        annotations = PipelineState.__annotations__
        assert "rag_context" in annotations

    def test_pipeline_state_has_agent_loop_fields(self):
        """PipelineState must include agent loop fields."""
        from core.pipeline.contracts import PipelineState

        annotations = PipelineState.__annotations__
        assert "agent_tool_call" in annotations
        assert "executed_tools" in annotations
        assert "last_tool_result" in annotations

    def test_pipeline_state_total_false_allows_empty(self):
        """PipelineState(total=False) allows creating an empty instance."""
        from core.pipeline.contracts import PipelineState

        state: PipelineState = {}
        assert isinstance(state, dict)
        assert len(state) == 0

    def test_intent_result_has_sensible_defaults(self):
        """IntentResult must have sensible default values."""
        from core.pipeline.contracts import IntentResult

        result = IntentResult()
        assert result.route == "general"
        assert result.intent == "general_question"
        assert result.action == "answer"
        assert result.confidence == 0.0
        assert result.source == "deterministic"

    def test_agent_request_has_defaults(self):
        """AgentRequest must have sensible default values."""
        from core.pipeline.contracts import AgentRequest

        req = AgentRequest(task="test")
        assert req.task == "test"
        assert req.route == "general"
        assert req.intent == "general_question"

    def test_agent_tool_call_validates_tool_name(self):
        """AgentToolCall must accept valid tool names."""
        from core.pipeline.contracts import AgentToolCall

        call = AgentToolCall(tool="final_answer", args={"answer": "test"})
        assert call.tool == "final_answer"
        assert call.args["answer"] == "test"

    def test_agent_tool_call_rejects_invalid_tool(self):
        """AgentToolCall must reject invalid tool names."""
        from core.pipeline.contracts import AgentToolCall

        with pytest.raises(ValueError):
            AgentToolCall(tool="nonexistent_tool")  # type: ignore[arg-type]

    def test_expert_call_has_defaults(self):
        """ExpertCall must have sensible default values."""
        from core.pipeline.contracts import ExpertCall

        ec = ExpertCall(role="fundamental", ticker="AAPL")
        assert ec.role == "fundamental"
        assert ec.ticker == "AAPL"
        assert ec.timeout == 60.0
        assert ec.context == ""
