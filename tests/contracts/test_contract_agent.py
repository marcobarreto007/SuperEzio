"""Contract tests for CEO prompt builder invariants."""

from src.core.pipeline.prompts.builder import (
    build_agent_prompt,
    agent_system_prompt,
    _agent_assistant_prefix,
    _required_module_presence,
    _render_module_contract,
    _evaluate_module_coverage,
    _format_pennylab,
    _format_neural_decision,
    _format_mandamentos,
    missing_agent_text,
)
from src.core.pipeline.prompts._prompts import (
    QWEN_SYSTEM_PROMPT,
    QWEN_PERSONA,
    MODEL_PROMPTS,
)
from src.core.pipeline.nodes.agent import _apply_grounding_guard, _repair_answer_quality


# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------


def test_agent_system_prompt_is_natural_language_advisor():
    prompt = agent_system_prompt()
    assert "natural-language financial analysis" in prompt
    assert "user's language" in prompt
    assert "not broker execution" in prompt


def test_agent_system_prompt_non_empty():
    assert len(agent_system_prompt()) > 100


def test_model_prompts_has_local():
    assert "local" in MODEL_PROMPTS
    assert "system" in MODEL_PROMPTS["local"]
    assert "persona" in MODEL_PROMPTS["local"]


# ---------------------------------------------------------------------------
# Casual / greeting detection
# ---------------------------------------------------------------------------


def test_build_agent_prompt_casual():
    state = {
        "message": "Hello, who are you?",
        "intent": "general_question",
        "route": "general",
    }
    prompt = build_agent_prompt(state)
    assert "USER:" in prompt
    assert "Hello" in prompt


def test_build_agent_prompt_general_financial_question_is_natural():
    state = {
        "message": "Quais cuidados devo tomar antes de comprar uma acao?",
        "intent": "general_question",
        "route": "general",
        "sdca_firewall": {"decision": "ALLOW", "confidence": 0.88},
    }
    prompt = build_agent_prompt(state)
    assert "USER:" in prompt
    assert "pretending market data was collected" in prompt
    assert "MANDATORY FORMAT" not in prompt


def test_module_coverage_skips_general_without_market_context():
    state = {
        "message": "Quais cuidados devo tomar antes de comprar uma acao?",
        "intent": "general_question",
        "route": "general",
        "sdca_firewall": {"decision": "ALLOW", "confidence": 0.88},
    }
    required, missing = _evaluate_module_coverage("resposta simples", state)
    assert required == []
    assert missing == []


def test_build_agent_prompt_ticker_analysis():
    state = {
        "message": "AAPL 14 dias",
        "ticker": "AAPL",
        "intent": "ticker_analysis",
        "route": "ticker_analysis",
        "time_horizon": "14 days",
        "data_context": "price=300.22 rsi=87.9",
        "expert_summary": "Experts: neutral outlook",
        "f51_verdict": {"confidence": 0.965, "passed": True},
    }
    prompt = build_agent_prompt(state)
    assert "Bob's read" in prompt
    assert "AAPL" in prompt
    assert "answer in the user's language" in prompt
    assert "direct trade order" in prompt


def test_build_agent_prompt_explain_capabilities():
    state = {
        "message": "What can you do?",
        "intent": "explain_capabilities",
        "route": "general",
    }
    prompt = build_agent_prompt(state)
    assert (
        "explain" in prompt.lower()
        or "capabilities" in prompt.lower()
        or "method" in prompt.lower()
    )


def test_build_agent_prompt_missing_agent():
    text = missing_agent_text(ticker="AAPL", route="ticker_analysis", local_ready=False)
    assert "MODEL_MISSING" in text
    assert "AAPL" in text


def test_build_agent_prompt_missing_agent_offline():
    text = missing_agent_text(local_ready=True)
    assert "MODEL_MISSING" in text
    assert "did not respond" in text


# ---------------------------------------------------------------------------
# Assistant prefix
# ---------------------------------------------------------------------------


def test_assistant_prefix_explain_returns_empty():
    state = {"intent": "explain_capabilities"}
    assert _agent_assistant_prefix(state) == ""


def test_assistant_prefix_with_ticker():
    state = {"ticker": "AAPL", "intent": "ticker_analysis", "route": "ticker_analysis"}
    assert "Bob guidance" in _agent_assistant_prefix(state)


def test_assistant_prefix_market_scan():
    state = {"route": "market_scan", "intent": "market_scan"}
    prefix = _agent_assistant_prefix(state)
    assert "Market Scan" in prefix or "market" in prefix.lower()


def test_grounding_guard_blocks_uncollected_ticker_recommendations():
    state = {
        "message": "What stock would you recommend for the next 14 days?",
        "ticker": "NVDA",
        "data": {"ticker": "NVDA", "data_quality": "partial", "source_errors": []},
        "data_context": "Collected ticker: NVDA",
    }
    draft = (
        "Go for MRVL at $315. I would also keep an eye on RDW "
        "(Redwood Materials) at $21.92."
    )

    guarded = _apply_grounding_guard(state, draft)

    assert "only have collected data" in guarded
    assert "NVDA" in guarded
    assert "MRVL" in guarded
    assert "RDW" in guarded
    assert "Redwood Materials" not in guarded
    assert "$315" not in guarded
    assert "$21.92" not in guarded
    assert "Final verdict: WAIT" in guarded


def test_grounding_guard_allows_scan_candidates():
    state = {
        "message": "Find a short-term stock idea",
        "scan": {
            "candidates": [
                {
                    "ticker": "MRVL",
                    "name": "Marvell Technology",
                    "price": 315,
                    "provider": "finnhub",
                }
            ]
        },
        "data_context": "MRVL scan candidate",
    }
    draft = "MRVL is the only scan-approved candidate."

    assert _apply_grounding_guard(state, draft) == draft


def test_answer_quality_softens_exact_short_term_return_ranges():
    draft = "A 5-8% pop in two weeks is plausible. But 5-8%? That's very doable."

    repaired = _repair_answer_quality(draft)

    assert "very doable" not in repaired
    assert "not a forecast" in repaired
    assert "Return-range caveat" in repaired


# ---------------------------------------------------------------------------
# Module presence detection
# ---------------------------------------------------------------------------


def test_required_module_presence_empty():
    state = {}
    presence = _required_module_presence(state)
    assert presence["price"] is False
    assert presence["f51"] is False
    assert presence["neural"] is False


def test_required_module_presence_with_data():
    state = {
        "data": {"price": {"value": 100}, "technicals": {"rsi": 50}},
        "ticker": "AAPL",
    }
    presence = _required_module_presence(state)
    assert presence["price"] is True
    assert presence["technical"] is True


def test_required_module_presence_f51():
    state = {"f51_verdict": {"confidence": 0.9}}
    presence = _required_module_presence(state)
    assert presence["f51"] is True


def test_required_module_presence_neural():
    state = {"neural_decision": {"direction_prob": {"up": 0.6}}}
    presence = _required_module_presence(state)
    assert presence["neural"] is True


# ---------------------------------------------------------------------------
# Module contract rendering
# ---------------------------------------------------------------------------


def test_render_module_contract_empty():
    state = {}
    result = _render_module_contract(state)
    assert result == ""


def test_render_module_contract_with_modules():
    state = {"data": {"price": {"value": 100}}, "ticker": "AAPL"}
    result = _render_module_contract(state)
    assert "MANDATORY_MODULE_COVERAGE" in result
    assert "price" in result


# ---------------------------------------------------------------------------
# Module coverage evaluation
# ---------------------------------------------------------------------------


def test_evaluate_module_coverage_empty():
    required, missing = _evaluate_module_coverage("", {})
    assert required == []
    assert missing == []


def test_evaluate_module_coverage_all_present():
    state = {"data": {"price": {"value": 100}}, "ticker": "AAPL"}
    required, missing = _evaluate_module_coverage("The price is 100 dollars", state)
    assert "price" in required
    assert "price" not in missing


def test_evaluate_module_coverage_missing():
    state = {
        "data": {"price": {"value": 100}, "technicals": {"rsi": 50}},
        "ticker": "AAPL",
    }
    required, missing = _evaluate_module_coverage("The price is good", state)
    assert "technical" in missing


# ---------------------------------------------------------------------------
# PennyLab formatting
# ---------------------------------------------------------------------------


def test_format_pennylab_empty():
    assert _format_pennylab({}) == ""
    assert _format_pennylab(None) == ""


def test_format_pennylab_with_decision():
    pl = {"decision": "WATCH_ONLY", "ticker": "AAPL", "confidence": 0.286}
    result = _format_pennylab(pl)
    assert "[PENNYLAB]" in result
    assert "WATCH_ONLY" in result


# ---------------------------------------------------------------------------
# Neural decision formatting
# ---------------------------------------------------------------------------


def test_format_neural_decision_empty():
    assert _format_neural_decision({}) == ""


def test_format_neural_decision_with_error():
    assert _format_neural_decision({"error": "timeout"}) == ""


def test_format_neural_decision_full():
    nd = {
        "direction_prob": {"up": 0.62, "down": 0.25, "sideways": 0.13},
        "expected_return": 0.0075,
        "drawdown_risk": 0.25,
        "uncertainty": 0.35,
        "regime": "trend_real",
        "recommendation": "alerta_forte",
        "veto": False,
    }
    result = _format_neural_decision(nd)
    assert "[NEURAL_DECISION]" in result
    assert "trend_real" in result
    assert "0.62" in result


# ---------------------------------------------------------------------------
# Mandamentos formatting
# ---------------------------------------------------------------------------


def test_format_mandamentos_empty():
    assert _format_mandamentos([]) == ""


def test_format_mandamentos_with_rules():
    class FakeRule:
        def __init__(self, id, data, regra):
            self.id = id
            self.data = data
            self.regra = regra

    rules = [FakeRule("R1", "2026-01-01", "No penny stocks")]
    result = _format_mandamentos(rules)
    assert "[USER_RULES]" in result
    assert "R1" in result


# ---------------------------------------------------------------------------
# QWEN prompts constants
# ---------------------------------------------------------------------------


def test_qwen_system_prompt_blocks_trade_orders():
    assert "Do not issue direct trade orders" in QWEN_SYSTEM_PROMPT
    assert "naked trade verdict" in QWEN_SYSTEM_PROMPT


def test_qwen_persona_has_bob():
    assert "Bob" in QWEN_PERSONA


def test_prompts_follow_user_language():
    assert "user's language" in QWEN_SYSTEM_PROMPT
    assert "user's language" in QWEN_PERSONA
