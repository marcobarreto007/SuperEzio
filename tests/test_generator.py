"""Unit tests for generator.py - answer/fallback/repair logic."""

from src.core.pipeline.nodes.generator import (
    _advisory_knowledge_fallback_answer,
    _complex_finance_fallback_answer,
    _contract_fallback_answer,
    _final_payload,
    _forced_tool_call_before_final,
    _has_actionable_market_request,
    _has_expert_evidence,
    _has_market_evidence,
    _has_tax_overstatement,
    _has_unsupported_macro_precision,
    _is_dca_macro_question,
    _is_etf_comparison_question,
    _is_portfolio_concentration_question,
    _loop_failsafe_answer,
    _repair_answer_quality,
    _repair_complex_finance_answer,
    _repair_known_etf_category_errors,
    _repair_overlapping_etf_tickers,
    _repair_short_term_return_forecasts,
    _repair_tax_overstatements,
    _repair_unsourced_etf_tickers,
    _repair_unsupported_exact_returns,
    _should_force_contract_fallback,
    _tool_blocked_answer,
)


class TestComplexFinanceFallback:
    def test_capital_allocation_detection(self):
        answer = _complex_finance_fallback_answer("I have CAD 50000 to allocate")
        assert "CAPITAL_ALLOCATION" in answer
        assert "Confidence:" in answer

    def test_10_section_structure(self):
        answer = _complex_finance_fallback_answer("allocate 25k CAD")
        for section in [
            "Question Classification",
            "Assumptions",
            "Missing Data",
            "Decision Variables",
            "Quantitative Thresholds",
            "Scenario Analysis",
            "Ranked Allocation",
            "Decision Gates",
            "Final Recommendation",
            "Confidence Level",
        ]:
            assert section in answer, f"Missing section: {section}"

    def test_verdict_present(self):
        answer = _complex_finance_fallback_answer("emergency fund allocation")
        assert "Final verdict:" in answer
        assert any(v in answer for v in ("PAY_DEBT", "CASH", "ETF", "STOCK_TRADE", "WAIT"))


class TestAdvisoryKnowledgeFallback:
    def test_etf_comparison(self):
        answer = _advisory_knowledge_fallback_answer({"message": "compare VOO vs VTI vs SCHD"})
        assert "ETF" in answer

    def test_generic_fallback(self):
        answer = _advisory_knowledge_fallback_answer({"message": "what is inflation?"})
        assert "thesis" in answer.lower() or "framework" in answer.lower()


class TestContractFallback:
    def test_capital_allocation_mode(self):
        answer = _contract_fallback_answer(
            {"cognitive_mode": "CAPITAL_ALLOCATION", "message": "allocate 25k"}
        )
        assert "CAPITAL_ALLOCATION" in answer

    def test_discovery_scan_mode(self):
        answer = _contract_fallback_answer(
            {"cognitive_mode": "DISCOVERY_SCAN", "message": "find opportunities"}
        )
        assert "REJECT_ALL" in answer


class TestRepairFunctions:
    def test_repair_vtv_small_cap(self):
        result = _repair_known_etf_category_errors(
            "For small-cap exposure, consider VTV for value."
        )
        assert "VBR" in result
        assert "VTV" not in result

    def test_repair_vwenx_bond(self):
        result = _repair_known_etf_category_errors("For bond ETF exposure, consider VWENX.")
        assert "BND" in result
        assert "VWENX" not in result

    def test_repair_unsourced_etf(self):
        result = _repair_unsourced_etf_tickers("Consider VCN for Canadian exposure.")
        assert "VCN" not in result
        assert "Canadian" in result

    def test_repair_guaranteed_return(self):
        result = _repair_unsupported_exact_returns(
            "Paying off 8% debt is like earning a guaranteed 8% return."
        )
        assert "guaranteed return equal to the avoided interest rate" in result

    def test_repair_tax_overstatement(self):
        result = _repair_tax_overstatements("Stay under your annual capital gains exemption.")
        assert "capital gains exemption" not in result

    def test_repair_short_term_forecast(self):
        result = _repair_short_term_return_forecasts(
            "The trade could return 5-10% in two weeks, very doable."
        )
        assert any(kw in result.lower() for kw in ("ilustrativo", "not a forecast"))

    def test_repair_answer_quality_chains(self):
        result = _repair_answer_quality(
            "Buy VCN for guaranteed 10% return. Stay under capital gains exemption."
        )
        assert "VCN" not in result

    def test_repair_complex_adds_note(self):
        result = _repair_complex_finance_answer(
            "allocate 25k CAD", "Final verdict: ETF\nConfidence: 70"
        )
        assert "illustrative assumptions" in result.lower()


class TestDetectionFunctions:
    def test_is_etf_comparison(self):
        assert _is_etf_comparison_question("compare VOO vs SPY")
        assert not _is_etf_comparison_question("buy VOO")

    def test_is_portfolio_concentration(self):
        assert _is_portfolio_concentration_question(
            "My portfolio is 40% concentrated in one stock, diversify?"
        )
        assert not _is_portfolio_concentration_question("buy some stocks")

    def test_is_dca_macro(self):
        assert _is_dca_macro_question("should I dollar-cost average?")
        assert not _is_dca_macro_question("buy AAPL")

    def test_has_unsupported_macro_precision(self):
        assert _has_unsupported_macro_precision("The VIX is at 22.5 and Treasury yields are 4.25%")
        assert not _has_unsupported_macro_precision("Market volatility is elevated")

    def test_has_tax_overstatement(self):
        assert _has_tax_overstatement("Use your annual capital gains exemption of $40K")
        assert not _has_tax_overstatement("Consider tax implications before selling")


class TestRepairOverlappingETFs:
    def test_dedup_spy_voo(self):
        result = _repair_overlapping_etf_tickers("Consider SPY and VOO for S&P 500.")
        assert result.count("SPY") + result.count("VOO") <= 1

    def test_preserves_etf_comparison(self):
        result = _repair_overlapping_etf_tickers(
            "Compare SPY vs VOO.", message="compare SPY vs VOO"
        )
        assert "SPY" in result
        assert "VOO" in result


class TestToolOrchestration:
    def test_should_force_with_scan(self):
        assert (
            _should_force_contract_fallback(
                {"scan": {"candidates": []}, "message": "test"}, "content"
            )
            is True
        )

    def test_has_actionable_market_request(self):
        assert _has_actionable_market_request({"route": "market_scan", "message": "find"}) is True
        assert _has_actionable_market_request({"route": "general", "message": "hello"}) is False

    def test_has_market_evidence(self):
        assert _has_market_evidence({"data": {"ticker": "AAPL"}}) is True
        assert _has_market_evidence({"message": "hello"}) is False

    def test_has_expert_evidence(self):
        assert _has_expert_evidence({"expert_summary": "all clear"}) is True
        assert _has_expert_evidence({"message": "hello"}) is False

    def test_forced_tool_call_noop(self):
        result = _forced_tool_call_before_final(
            {
                "route": "general",
                "message": "hello",
                "allowed_tools": ["final_answer"],
                "executed_tools": [],
            }
        )
        assert result is None

    def test_final_payload_structure(self):
        result = _final_payload("answer text", 3)
        assert result["final"] == "answer text"
        assert result["agent_tool_call"]["tool"] == "final_answer"
        assert result["agent_iterations"] == 4
        assert result["_pending_tool_calls"] == []


class TestLoopFailsafe:
    def test_failsafe_returns_string(self):
        answer = _loop_failsafe_answer({"message": "bob me ajuda com investimento"})
        assert isinstance(answer, str)
        assert "Bob:" in answer


class TestToolBlocked:
    def test_blocked_returns_message(self):
        answer = _tool_blocked_answer(
            {
                "tool_blocked": {"tool": "market_scan", "reason": "already executed"},
                "message": "test",
            }
        )
        assert isinstance(answer, str)
        assert "market_scan" in answer.lower()
