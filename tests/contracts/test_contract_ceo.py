"""Contract tests for CEO prompt builder invariants."""
from src.core.pipeline.prompts.builder import (
    build_ceo_prompt,
    ceo_system_prompt,
    _ceo_assistant_prefix,
    _required_module_presence,
    _render_module_contract,
    _evaluate_module_coverage,
    _format_pennylab,
    _format_neural_decision,
    _format_mandamentos,
    missing_ceo_text,
)
from src.core.pipeline.prompts._prompts import QWEN_SYSTEM_PROMPT, QWEN_PERSONA, MODEL_PROMPTS


# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

def test_ceo_system_prompt_is_english():
    prompt = ceo_system_prompt()
    assert "ENGLISH" in prompt
    assert "LANGUAGE" in prompt

def test_ceo_system_prompt_non_empty():
    assert len(ceo_system_prompt()) > 100

def test_model_prompts_has_local():
    assert "local" in MODEL_PROMPTS
    assert "system" in MODEL_PROMPTS["local"]
    assert "persona" in MODEL_PROMPTS["local"]


# ---------------------------------------------------------------------------
# Casual / greeting detection
# ---------------------------------------------------------------------------

def test_build_ceo_prompt_casual():
    state = {
        "message": "Hello, who are you?",
        "intent": "general_question",
        "route": "general",
    }
    prompt = build_ceo_prompt(state)
    assert "USER:" in prompt
    assert "Hello" in prompt

def test_build_ceo_prompt_ticker_analysis():
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
    prompt = build_ceo_prompt(state)
    assert "VERDICT" in prompt
    assert "AAPL" in prompt
    assert "LANGUAGE: WRITE 100% IN ENGLISH" in prompt

def test_build_ceo_prompt_explain_capabilities():
    state = {
        "message": "What can you do?",
        "intent": "explain_capabilities",
        "route": "general",
    }
    prompt = build_ceo_prompt(state)
    assert "explain" in prompt.lower() or "capabilities" in prompt.lower() or "method" in prompt.lower()

def test_build_ceo_prompt_missing_ceo():
    text = missing_ceo_text(ticker="AAPL", route="ticker_analysis", local_ready=False)
    assert "MODEL_MISSING" in text
    assert "AAPL" in text

def test_build_ceo_prompt_missing_ceo_offline():
    text = missing_ceo_text(local_ready=True)
    assert "MODEL_MISSING" in text
    assert "did not respond" in text


# ---------------------------------------------------------------------------
# Assistant prefix
# ---------------------------------------------------------------------------

def test_assistant_prefix_explain_returns_empty():
    state = {"intent": "explain_capabilities"}
    assert _ceo_assistant_prefix(state) == ""

def test_assistant_prefix_with_ticker():
    state = {"ticker": "AAPL", "intent": "ticker_analysis", "route": "ticker_analysis"}
    assert "VERDICT" in _ceo_assistant_prefix(state)

def test_assistant_prefix_market_scan():
    state = {"route": "market_scan", "intent": "market_scan"}
    prefix = _ceo_assistant_prefix(state)
    assert "Market Scan" in prefix or "market" in prefix.lower()


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
    state = {"data": {"price": {"value": 100}, "technicals": {"rsi": 50}}, "ticker": "AAPL"}
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
    state = {"data": {"price": {"value": 100}, "technicals": {"rsi": 50}}, "ticker": "AAPL"}
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

def test_qwen_system_prompt_has_verdict_format():
    assert "VERDICT: BUY / SELL / HOLD" in QWEN_SYSTEM_PROMPT

def test_qwen_persona_has_bob():
    assert "Bob" in QWEN_PERSONA

def test_prompts_are_english():
    assert "ENGLISH" in QWEN_SYSTEM_PROMPT
    assert "English" in QWEN_PERSONA
