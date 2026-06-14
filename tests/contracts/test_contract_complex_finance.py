"""Contract tests for complex finance routing — P0 fix verification.

These tests verify that:
1. Complex finance questions do NOT trigger the market scanner.
2. Complex finance questions are classified correctly.
3. Explicit ticker queries still work (no regression).
4. The complex finance system prompt is activated for advisory questions.
"""

import pytest

from src.core.pipeline.intents import (
    detect_complex_finance_intent,
    detect_market_scan_intent,
    detect_ticker,
    parse_user_intent,
    should_block_vague_financial_prompt,
)
from src.core.pipeline.nodes.agent import (
    COMPLEX_FINANCE_SYSTEM_PROMPT,
    SYSTEM_PROMPT,
    _repair_complex_finance_answer,
)
from src.core.pipeline.prompts.builder import build_agent_prompt


# ---------------------------------------------------------------------------
# Test prompts from the mission spec
# ---------------------------------------------------------------------------

MACRO_THESIS_PROMPT = (
    "An investor believes AI will dominate the next decade and wants heavy exposure "
    "to AI infrastructure, semiconductors, cloud, energy, and automation. Build a thesis "
    "that separates real secular opportunity from hype, overvaluation, and concentration risk."
)

CAPITAL_ALLOCATION_PROMPT = (
    "A family has CAD 25,000 available. They are deciding between investing it, "
    "keeping cash, buying equipment for a side business, paying debt, or funding education. "
    "Build a ranked decision matrix using expected return, downside risk, time-to-cashflow, "
    "reversibility, and family stability."
)

LIVE_CAD_ALLOCATION_PROMPT = (
    "I live in Canada, earn and spend in CAD, have a family, unstable work income, "
    "and have CAD 25,000 to allocate between emergency cash reserve, debt, ETFs, "
    "side-business equipment, and education. Give me a concise serious framework."
)

REAL_ESTATE_VS_ETF_PROMPT = (
    "Build a decision framework for evaluating whether a rental property is a better "
    "investment than a diversified equity portfolio. Include leverage, vacancy risk, "
    "maintenance, taxes, liquidity, concentration risk, interest rates, and opportunity cost."
)

EXPLICIT_TICKER_PROMPT = "Analyze AAPL for the next 5 trading days using the current chart context."


# ===========================================================================
# Test 1 — AI macro thesis must NOT scan tickers
# ===========================================================================


class TestMacroThesisNoScan:
    """Macro thesis question: no scanner, no Chinese tickers."""

    def test_classified_as_complex_finance(self):
        assert detect_complex_finance_intent(MACRO_THESIS_PROMPT) is True

    def test_not_classified_as_market_scan(self):
        assert detect_market_scan_intent(MACRO_THESIS_PROMPT) is False

    def test_no_ticker_detected(self):
        assert detect_ticker(MACRO_THESIS_PROMPT) == ""

    def test_parse_routes_to_general(self):
        parsed = parse_user_intent(MACRO_THESIS_PROMPT)
        assert parsed.route == "general"
        assert parsed.intent == "general_question"
        assert parsed.action == "answer"
        assert "complex_finance_advisory_detected" in parsed.reasons

    def test_does_not_trigger_vague_block(self):
        assert should_block_vague_financial_prompt(MACRO_THESIS_PROMPT, "", "strict") is False


# ===========================================================================
# Test 2 — CAD 25,000 family allocation must be serious
# ===========================================================================


class TestCapitalAllocation:
    """Family capital allocation: no scanner, includes quantitative framework."""

    def test_classified_as_complex_finance(self):
        assert detect_complex_finance_intent(CAPITAL_ALLOCATION_PROMPT) is True

    def test_not_classified_as_market_scan(self):
        assert detect_market_scan_intent(CAPITAL_ALLOCATION_PROMPT) is False

    def test_no_ticker_detected(self):
        # CAD should not be detected as a ticker
        assert detect_ticker(CAPITAL_ALLOCATION_PROMPT) == ""

    def test_parse_routes_to_general(self):
        parsed = parse_user_intent(CAPITAL_ALLOCATION_PROMPT)
        assert parsed.route == "general"
        assert parsed.intent == "capital_allocation"
        assert "capital_allocation_decision_detected" in parsed.reasons

    def test_does_not_trigger_vague_block(self):
        assert should_block_vague_financial_prompt(CAPITAL_ALLOCATION_PROMPT, "", "strict") is False

    def test_live_cad_allocation_prompt_routes_to_capital_allocation(self):
        parsed = parse_user_intent(LIVE_CAD_ALLOCATION_PROMPT)

        assert detect_complex_finance_intent(LIVE_CAD_ALLOCATION_PROMPT) is True
        assert parsed.route == "general"
        assert parsed.intent == "capital_allocation"
        assert "capital_allocation_decision_detected" in parsed.reasons

    def test_repair_corrects_known_etf_category_mismatch(self):
        content = (
            "8. Ranked Allocation / Framework — 50% US Large Cap ETFs (VOO), "
            "20% International Developed Markets (VXUS), 15% US Small Cap Value (VTV), "
            "10% Bonds (BND), 5% REITs (VNQ).\n"
            "Final verdict: ETF\n"
            "Confidence: 76"
        )

        repaired = _repair_complex_finance_answer(CAPITAL_ALLOCATION_PROMPT, content)

        assert "US Small Cap Value (VTV)" not in repaired
        assert "US Small Cap Value (VBR)" in repaired

    def test_repair_removes_unsupported_exact_debt_return(self):
        content = (
            "8. Ranked Allocation / Framework — High-interest debt paydown "
            "(30% = CAD 7,500) — why: guaranteed 8-15% return vs market uncertainty.\n"
            "Final verdict: ETF\n"
            "Confidence: 76"
        )

        repaired = _repair_complex_finance_answer(CAPITAL_ALLOCATION_PROMPT, content)

        assert "8-15% return" not in repaired
        assert "avoided interest rate" in repaired

    def test_repair_removes_tax_free_exact_debt_return_phrase(self):
        content = (
            "Why here? Because paying off 7% debt is like earning a guaranteed, "
            "tax-free 7% return -- with zero volatility.\n"
            "Final verdict: ETF\n"
            "Confidence: 76"
        )

        repaired = _repair_complex_finance_answer(CAPITAL_ALLOCATION_PROMPT, content)

        assert "7% return" not in repaired
        assert "avoided interest rate" in repaired

    def test_repair_corrects_mutual_fund_used_as_bond_etf(self):
        content = (
            "8. Ranked Allocation / Framework — 50% US Large Cap ETF (VOO), "
            "20% International Developed Markets ETF (VEA), 15% US Small Cap ETF (IJR), "
            "10% Investment Grade Bond ETF (VWENX), 5% Real Estate REIT ETF (VNQ).\n"
            "Final verdict: ETF\n"
            "Confidence: 76"
        )

        repaired = _repair_complex_finance_answer(CAPITAL_ALLOCATION_PROMPT, content)

        assert "Bond ETF (VWENX)" not in repaired
        assert "Bond ETF (BND)" in repaired

    def test_repair_adds_canadian_registered_account_gate(self):
        content = (
            "This is an educational framework, not personalized financial advice.\n"
            "Question Classification: CAPITAL_ALLOCATION\n"
            "Missing Data: tax-advantaged account availability\n"
            "Decision Gates: tax account choices depend on the individual's situation.\n"
            "Final verdict: CASH\n"
            "Confidence: 72"
        )

        repaired = _repair_complex_finance_answer(CAPITAL_ALLOCATION_PROMPT, content)

        assert "TFSA, RRSP, RESP, or FHSA" in repaired
        assert repaired.rstrip().endswith("Confidence: 72")

    def test_repair_adds_scope_disclaimer_when_missing(self):
        # Disclaimers removidos — o Bob nao injeta mais scope note
        content = (
            "Short allocation sketch without legal framing.\nFinal verdict: WAIT\nConfidence: 70"
        )

        repaired = _repair_complex_finance_answer(CAPITAL_ALLOCATION_PROMPT, content)

        assert "scope note:" not in repaired.lower()
        assert "not personalized financial advice" not in repaired.lower()
        assert "Final verdict: WAIT" in repaired

    def test_repair_adds_assumptions_note_when_missing(self):
        content = "Short allocation sketch.\nFinal verdict: WAIT\nConfidence: 70"

        repaired = _repair_complex_finance_answer(CAPITAL_ALLOCATION_PROMPT, content)

        assert "assumptions note:" in repaired.lower()
        assert "illustrative assumptions" in repaired.lower()

    def test_repair_replaces_unsourced_canadian_etf_tickers(self):
        content = (
            "This is an educational framework, not personalized financial advice.\n"
            "Buy VCN and VCE for Canadian ETF exposure, then add ZAG.\n"
            "Final verdict: ETF\n"
            "Confidence: 70"
        )

        repaired = _repair_complex_finance_answer(CAPITAL_ALLOCATION_PROMPT, content)

        assert "VCN" not in repaired
        assert "VCE" not in repaired
        assert "ZAG" not in repaired
        assert "broad Canadian equity index ETF" in repaired
        assert "aggregate bond ETF" in repaired


# ===========================================================================
# Test 3 — Rental property vs ETF must include quantitative framework
# ===========================================================================


class TestRealEstateVsMarkets:
    """Real estate vs markets: no scanner, includes framework terms."""

    def test_classified_as_complex_finance(self):
        assert detect_complex_finance_intent(REAL_ESTATE_VS_ETF_PROMPT) is True

    def test_not_classified_as_market_scan(self):
        assert detect_market_scan_intent(REAL_ESTATE_VS_ETF_PROMPT) is False

    def test_no_ticker_detected(self):
        assert detect_ticker(REAL_ESTATE_VS_ETF_PROMPT) == ""

    def test_parse_routes_to_general(self):
        parsed = parse_user_intent(REAL_ESTATE_VS_ETF_PROMPT)
        assert parsed.route == "general"
        assert parsed.intent == "general_question"
        assert "complex_finance_advisory_detected" in parsed.reasons

    def test_does_not_trigger_vague_block(self):
        assert should_block_vague_financial_prompt(REAL_ESTATE_VS_ETF_PROMPT, "", "strict") is False


# ===========================================================================
# Test 4 — Explicit ticker still works (no regression)
# ===========================================================================


class TestExplicitTickerNoRegression:
    """Explicit ticker request must still route to ticker_analysis."""

    def test_not_classified_as_complex_finance(self):
        assert detect_complex_finance_intent(EXPLICIT_TICKER_PROMPT) is False

    def test_ticker_detected(self):
        assert detect_ticker(EXPLICIT_TICKER_PROMPT) == "AAPL"

    def test_parse_routes_to_ticker_analysis(self):
        parsed = parse_user_intent(EXPLICIT_TICKER_PROMPT)
        assert parsed.route == "ticker_analysis"
        assert parsed.intent == "ticker_analysis"
        assert parsed.ticker == "AAPL"


# ===========================================================================
# Test 5 — Complex finance detection accuracy
# ===========================================================================


class TestReferentialTickerNeedsScope:
    """A prompt pointing at "this ticket" needs a real ticker or UI context."""

    def test_unscoped_ticket_status_prompt_asks_for_ticker(self):
        parsed = parse_user_intent("cara vc esta travado neste ticket ?", rigor="strict", ticker="")

        assert parsed.route == "needs_scope"
        assert parsed.intent == "missing_required_slot"
        assert parsed.action == "ask_for_ticker"
        assert parsed.required_slots == ("ticker",)
        assert parsed.ticker == ""

    def test_context_ticker_allows_referential_prompt(self):
        parsed = parse_user_intent("cara vc esta travado neste ticket ?", ticker="NOK")

        assert parsed.route != "needs_scope"


class TestComplexFinanceDetection:
    """Unit tests for detect_complex_finance_intent edge cases."""

    def test_empty_message(self):
        assert detect_complex_finance_intent("") is False

    def test_simple_greeting(self):
        assert detect_complex_finance_intent("Hello Bob") is False

    def test_simple_buy_question(self):
        assert detect_complex_finance_intent("What should I buy?") is False

    def test_scan_request_not_complex(self):
        """Explicit scan commands should NOT be classified as complex finance."""
        assert (
            detect_complex_finance_intent("Scan Canadian penny stocks under $1 with high volume")
            is False
        )

    def test_ticker_query_not_complex(self):
        """Questions with explicit tickers should NOT be classified as complex."""
        assert (
            detect_complex_finance_intent("Build a thesis about NVDA semiconductor dominance")
            is False
        )

    def test_framework_with_multiple_hints(self):
        """Multiple complex finance keywords trigger detection."""
        assert (
            detect_complex_finance_intent(
                "Compare capital allocation options with concentration risk and opportunity cost"
            )
            is True
        )

    def test_structural_pattern_build_thesis(self):
        """Structural pattern 'build a thesis' triggers detection."""
        assert (
            detect_complex_finance_intent(
                "Build a thesis about the secular trend in renewable energy "
                "separating real opportunity from hype in a 30-word sentence"
            )
            is True
        )

    def test_real_estate_framework(self):
        """Real estate comparison triggers detection."""
        assert (
            detect_complex_finance_intent(
                "Should I buy a rental property or invest in ETFs? "
                "Include cap rate, vacancy risk, and concentration risk."
            )
            is True
        )


# ===========================================================================
# Test 6 — Agent system prompt selection
# ===========================================================================


class TestAgentPromptSelection:
    """Verify that the agent selects the correct system prompt."""

    def test_complex_finance_prompt_is_different(self):
        """Complex finance prompt must differ from the default."""
        assert COMPLEX_FINANCE_SYSTEM_PROMPT != SYSTEM_PROMPT

    def test_complex_finance_prompt_has_11_sections(self):
        """Complex finance prompt must contain the 11-section contract."""
        for section in (
            "Question Classification",
            "Key Assumptions",
            "Missing Data",
            "Decision Variables",
            "Quantitative Thresholds",
            "Scenario Analysis",
            "Ranked Decision",
            "Main Risks",
            "What Would Change the Decision",
            "Final Recommendation",
            "Confidence Level",
        ):
            assert section in COMPLEX_FINANCE_SYSTEM_PROMPT, f"Missing section: {section}"

    def test_complex_finance_prompt_blocks_scanner(self):
        """Complex finance prompt must explicitly block scanner calls."""
        assert "Do NOT call market_scan" in COMPLEX_FINANCE_SYSTEM_PROMPT


# ===========================================================================
# Test 7 — CEO prompt builder contract
# ===========================================================================


class TestAgentPromptBuilderComplexFinance:
    """Verify agent prompt builder uses the complex finance contract."""

    def test_macro_thesis_gets_complex_prompt(self):
        state = {
            "message": MACRO_THESIS_PROMPT,
            "intent": "general_question",
            "route": "general",
        }
        prompt = build_agent_prompt(state)
        assert "COMPLEX FINANCE ADVISORY CONTRACT" in prompt
        assert "Question Classification" in prompt
        assert "Scenario Analysis" in prompt

    def test_capital_allocation_gets_complex_prompt(self):
        state = {
            "message": CAPITAL_ALLOCATION_PROMPT,
            "intent": "general_question",
            "route": "general",
        }
        prompt = build_agent_prompt(state)
        assert "COMPLEX FINANCE ADVISORY CONTRACT" in prompt
        assert "emergency reserve" in prompt

    def test_real_estate_gets_complex_prompt(self):
        state = {
            "message": REAL_ESTATE_VS_ETF_PROMPT,
            "intent": "general_question",
            "route": "general",
        }
        prompt = build_agent_prompt(state)
        assert "COMPLEX FINANCE ADVISORY CONTRACT" in prompt
        assert "cap rate" in prompt

    def test_simple_greeting_gets_normal_prompt(self):
        state = {
            "message": "Hello, who are you?",
            "intent": "general_question",
            "route": "general",
        }
        prompt = build_agent_prompt(state)
        assert "COMPLEX FINANCE ADVISORY CONTRACT" not in prompt

    def test_ticker_analysis_gets_normal_prompt(self):
        state = {
            "message": "AAPL 14 days",
            "ticker": "AAPL",
            "intent": "ticker_analysis",
            "route": "ticker_analysis",
            "data_context": "price=300.22",
        }
        prompt = build_agent_prompt(state)
        assert "COMPLEX FINANCE ADVISORY CONTRACT" not in prompt


# ===========================================================================
# Test 8 — Forbidden output patterns for complex finance
# ===========================================================================


class TestForbiddenPatterns:
    """Ensure complex finance classification prevents scanner artifacts."""

    @pytest.mark.parametrize(
        "prompt",
        [MACRO_THESIS_PROMPT, CAPITAL_ALLOCATION_PROMPT, REAL_ESTATE_VS_ETF_PROMPT],
    )
    def test_no_scanner_route(self, prompt):
        parsed = parse_user_intent(prompt)
        assert parsed.route != "market_scan"
        assert parsed.action != "scan_market"

    @pytest.mark.parametrize(
        "prompt",
        [MACRO_THESIS_PROMPT, CAPITAL_ALLOCATION_PROMPT, REAL_ESTATE_VS_ETF_PROMPT],
    )
    def test_no_scanner_intent(self, prompt):
        parsed = parse_user_intent(prompt)
        assert parsed.intent != "market_scan"


# ===========================================================================
# Test 9 — Precision and Allocation Math Rules
# ===========================================================================


class TestPrecisionAndMathRules:
    """Verify that complex finance prompts contain precise rules for return ranges, scenarios, allocations, and AI topics."""

    def test_agent_prompt_has_precision_rules(self):
        assert "fake precision" in COMPLEX_FINANCE_SYSTEM_PROMPT
        assert "annualized return" in COMPLEX_FINANCE_SYSTEM_PROMPT
        assert "illustrative" in COMPLEX_FINANCE_SYSTEM_PROMPT
        assert "sum to exactly 100%" in COMPLEX_FINANCE_SYSTEM_PROMPT

    def test_agent_prompt_has_macro_thematic_exposure_logic(self):
        assert (
            "first build the thematic exposure logic before giving stock-screening criteria"
            in COMPLEX_FINANCE_SYSTEM_PROMPT
        )

    def test_agent_prompt_has_ai_thesis_segmentation(self):
        for term in [
            "infrastructure winners",
            "monetization-risk companies",
            "hype/pivot companies",
            "valuation traps",
            "portfolio sizing",
            "rebalancing rules",
            "maximum total AI-theme exposure",
        ]:
            assert term in COMPLEX_FINANCE_SYSTEM_PROMPT

    def test_builder_prompt_has_precision_rules(self):
        state = {
            "message": "AI investment thesis options",
            "intent": "general_question",
            "route": "general",
        }
        prompt = build_agent_prompt(state)
        assert "fake precision" in prompt
        assert "annualized return" in prompt
        assert "illustrative" in prompt
        assert "sum to exactly 100%" in prompt
        assert (
            "first build the thematic exposure logic before giving stock-screening criteria"
            in prompt
        )
        assert "infrastructure winners" in prompt
        assert "monetization-risk companies" in prompt
        assert "hype/pivot companies" in prompt
        assert "valuation traps" in prompt
        assert "portfolio sizing" in prompt
        assert "rebalancing rules" in prompt
        assert "maximum total AI-theme exposure" in prompt


class TestAgentP2CapitalAllocationQuality:
    """Verify that Bob's prompt builder enforces P2 capital allocation rules."""

    def test_prompt_has_actionable_gates(self):
        assert "emergency fund months" in COMPLEX_FINANCE_SYSTEM_PROMPT
        assert "debt interest rate" in COMPLEX_FINANCE_SYSTEM_PROMPT
        assert "income stability" in COMPLEX_FINANCE_SYSTEM_PROMPT
        assert "liquidity need" in COMPLEX_FINANCE_SYSTEM_PROMPT
        assert "time-to-cashflow for business equipment" in COMPLEX_FINANCE_SYSTEM_PROMPT
        assert "tax-advantaged account availability" in COMPLEX_FINANCE_SYSTEM_PROMPT

    def test_prompt_has_canadian_tax_note(self):
        assert "TFSA" in COMPLEX_FINANCE_SYSTEM_PROMPT
        assert "RRSP" in COMPLEX_FINANCE_SYSTEM_PROMPT
        assert "tax rules depend on the individual" in COMPLEX_FINANCE_SYSTEM_PROMPT
        # Prompt must warn against concatenating account types
        assert "NEVER concatenate" in COMPLEX_FINANCE_SYSTEM_PROMPT

    def test_prompt_has_allocation_why_rule(self):
        assert (
            "Every allocation must include why each bucket gets that percentage"
            in COMPLEX_FINANCE_SYSTEM_PROMPT
        )

    def test_prompt_has_what_changes_allocation(self):
        assert "what changes the allocation" in COMPLEX_FINANCE_SYSTEM_PROMPT

    def test_prompt_has_no_invented_returns_rule(self):
        assert (
            "Do NOT invent exact expected returns or probabilities unless they are explicitly sourced"
            in COMPLEX_FINANCE_SYSTEM_PROMPT
        )

    def test_prompt_has_anti_exact_probability_rule(self):
        assert "NEVER output exact probability values" in COMPLEX_FINANCE_SYSTEM_PROMPT
        assert "illustrative risk range, not forecast" in COMPLEX_FINANCE_SYSTEM_PROMPT
        assert "qualitative ranges" in COMPLEX_FINANCE_SYSTEM_PROMPT

    def test_prompt_has_anti_etf_ticker_rule(self):
        assert "NEVER recommend specific ETF tickers" in COMPLEX_FINANCE_SYSTEM_PROMPT
        assert "VGRO" in COMPLEX_FINANCE_SYSTEM_PROMPT  # must call out examples to avoid
        assert "broad diversified Canadian-listed ETF" in COMPLEX_FINANCE_SYSTEM_PROMPT

    def test_prompt_has_final_verdict_format(self):
        assert "FINAL OUTPUT FORMAT" in COMPLEX_FINANCE_SYSTEM_PROMPT
        assert "Final verdict:" in COMPLEX_FINANCE_SYSTEM_PROMPT
        assert "PAY_DEBT / CASH / ETF / STOCK_TRADE / WAIT" in COMPLEX_FINANCE_SYSTEM_PROMPT
        assert "Confidence: <0-100>" in COMPLEX_FINANCE_SYSTEM_PROMPT
        assert "Pick exactly ONE verdict" in COMPLEX_FINANCE_SYSTEM_PROMPT

    def test_cad_25k_allocation_answer_contract(self):
        """Add contract test: CAD 25k allocation answer must contain emergency fund gate,
        debt interest gate, business cashflow gate, tax-account note, and no unsupported exact probability.
        """
        import urllib.request
        import json

        # 1. Check if both API and agent servers are running
        try:
            req = urllib.request.Request("http://127.0.0.1:8002/health")
            urllib.request.urlopen(req, timeout=3)
            api_ok = True
        except Exception:
            api_ok = False

        if not api_ok:
            pytest.skip("API server not running, skipping runtime response contract test")

        # 2. Make post request to http://127.0.0.1:8002/task/submit
        payload = {
            "from": "test-runner",
            "to": "bob",
            "type": "TASK.SUBMIT",
            "payload": {
                "message": (
                    "I live in Canada, earn and spend in CAD, have a family, unstable work income, "
                    "health/energy constraints, and want to build financial independence over the next 10-15 years. "
                    "I have CAD 25,000 available today and want to decide how to allocate it between "
                    "emergency cash reserve, paying debt, ETFs, side-business equipment, and education. "
                    "Build a serious capital allocation plan."
                ),
                "session_id": "test-cad-25k-allocation",
            },
        }

        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            "http://127.0.0.1:8002/task/submit",
            data=data,
            headers={"Content-Type": "application/json"},
        )

        try:
            resp = urllib.request.urlopen(req, timeout=300)
            body = resp.read().decode("utf-8")
        except Exception as e:
            pytest.fail(f"Failed to submit task to local API: {e}")

        lines = [line.strip() for line in body.strip().split("\n") if line.strip()]
        full_content = ""
        for line in lines:
            try:
                ev = json.loads(line)
                if ev.get("type") == "CHUNK":
                    full_content += ev.get("content", "")
            except json.JSONDecodeError:
                pass

        try:
            # Verification asserts:
            assert len(full_content) > 0, "Response content is empty"
            disclaimer_markers = (
                "not personalized financial advice",
                "not a registered financial advisor",
                "not licensed",
                "not regulated",
                "educational framework",
                "scope note:",
            )
            assert any(marker in full_content.lower() for marker in disclaimer_markers)

            # 1. Emergency fund gate (emergency fund, emergency cash, reserve + months)
            assert any(term in full_content.lower() for term in ["emergency", "reserva"]), (
                "Missing emergency fund/reserve reference"
            )
            assert any(term in full_content.lower() for term in ["month", "meses", "mês"]), (
                "Missing emergency fund months reference"
            )

            # 2. Debt interest gate (interest, rate, juro, taxa + debt, dívida)
            assert any(term in full_content.lower() for term in ["debt", "divida", "dívida"]), (
                "Missing debt reference"
            )
            assert any(
                term in full_content.lower() for term in ["interest", "juro", "rate", "taxa"]
            ), "Missing debt interest/rate reference"

            # 3. Business cashflow gate (equipment, business, cashflow, time-to-cashflow, etc.)
            assert any(
                term in full_content.lower()
                for term in ["equipment", "equipamento", "business", "negocio", "negócio"]
            ), "Missing business/equipment reference"
            assert any(
                term in full_content.lower()
                for term in [
                    "cashflow",
                    "flow",
                    "fluxo",
                    "time-to-cashflow",
                    "caixa",
                    "payback",
                    "retorno",
                    "receita",
                ]
            ), "Missing business cashflow/time-to-cashflow reference"

            # 4. Tax-account note (TFSA, RRSP, RESP, FHSA + individual/situation dependency)
            assert any(term in full_content for term in ["TFSA", "RRSP", "RESP", "FHSA"]), (
                "Missing Canadian tax account names (TFSA, RRSP, RESP, FHSA)"
            )
            assert any(
                term in full_content.lower() for term in ["depend", "situa", "individ", "person"]
            ), "Missing tax dependency on individual/personal context note"

            # 5. No unsupported exact probability or return (check presence of illustrative scenarios / assumptions labeling)
            assert any(
                term in full_content.lower()
                for term in ["illustrative", "ilustrativ", "assum", "supo"]
            ), "Missing illustrative scenario labels or assumptions warning"

            # Assert no unsupported exact probability (e.g. 60% probability, 25% probability)
            # Unless explicitly labeled as illustrative / assumption in the surrounding text
            import re

            prob_matches = re.findall(
                r"(\b\d+%\s*(?:probability|chance|return|de probabilidade|de retorno|de chance)\b)",
                full_content.lower(),
            )
            for match in prob_matches:
                idx = full_content.lower().index(match)
                context_window = full_content.lower()[
                    max(0, idx - 80) : min(len(full_content), idx + 80)
                ]
                assert any(
                    term in context_window
                    for term in ["illustrative", "assumption", "ilustrativ", "supo", "assum"]
                ), (
                    f"Found unsupported exact probability/return: '{match}' without illustrative label in context: '{context_window}'"
                )
        except AssertionError as e:
            print("\n--- FULL CONTENT ON FAILURE ---")
            print(full_content)
            print("--------------------------------\n")
            raise e


@pytest.mark.asyncio
async def test_complex_finance_invalid_model_json_gets_deterministic_fallback(monkeypatch):
    """If agent JSON mode fails, complex finance must still emit a useful answer."""
    from src.core.pipeline.nodes import agent as agent_module

    events = []
    monkeypatch.setattr(agent_module, "get_stream_writer", lambda: events.append)

    class BadJsonGateway:
        async def chat_completion(self, **kwargs):
            return "not json"

    message = (
        "I live in Canada, earn and spend in CAD, have a family, unstable work income, "
        "health/energy constraints, and want to build financial independence over the next 10-15 years. "
        "I have CAD 25,000 available today and want to decide how to allocate it between "
        "emergency cash reserve, paying debt, ETFs, side-business equipment, and education. "
        "Build a serious capital allocation plan."
    )

    result = await agent_module.node_agent(
        {"run_id": "cad25k-fallback-test", "route": "general", "message": message},
        gateway=BadJsonGateway(),
    )

    content = result["final"]
    assert "emergency cash reserve" in content.lower()
    assert "3-6 months" in content
    assert "debt" in content.lower()
    assert "interest" in content.lower()
    assert "equipment" in content.lower()
    assert "time-to-cashflow" in content.lower()
    assert "TFSA, RRSP, RESP, or FHSA" in content
    assert "Final verdict:" in content
    assert any(event.get("type") == "CHUNK" for event in events)
