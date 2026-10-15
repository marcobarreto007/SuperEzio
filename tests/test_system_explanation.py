"""Architecture questions must not become an empty evidence report."""

import pytest


def test_spoken_opinion_is_kept_and_silence_is_not():
    from core.pipeline.nodes.agent import _spoken_opinion

    opinion = (
        "ATXG em 2022 teve um salto enorme e retorno anormal zero. "
        "Eu nao compraria isso com o arquivo nesse estado."
    )
    assert _spoken_opinion(opinion) == opinion
    assert _spoken_opinion("") == ""
    assert _spoken_opinion('{"tool":"final_answer"}') == ""


def test_detects_architecture_question():
    from core.pipeline.intents import detect_system_explanation_request

    assert detect_system_explanation_request("bob , me explica sua arquitetura")
    assert detect_system_explanation_request("como voce funciona")
    assert detect_system_explanation_request("what is your architecture")
    assert detect_system_explanation_request("analisa AAPL") is False
    assert detect_system_explanation_request("me explica o grafico") is False
    assert detect_system_explanation_request("compre SPY") is False


def test_architecture_contract_blocks_market_tools():
    from core.pipeline.intents import infer_cognitive_contract

    contract = infer_cognitive_contract(
        "bob , me explica sua arquitetura",
        route="agent",
        intent="bob_decides",
        action="analyze_and_execute",
        ticker="VLB",
    )

    assert contract["information_need"] == "system_architecture"
    assert contract["allowed_tools"] == ["final_answer"]
    assert contract["scanner_allowed"] is False
    assert contract["ticker_allowed"] is False


def test_architecture_prompt_drops_missing_contract():
    from core.pipeline.prompts.builder import build_agent_prompt

    prompt = build_agent_prompt(
        {
            "message": "bob , me explica sua arquitetura",
            "intent": "bob_decides",
            "route": "agent",
            "ticker": "",
            "rag_context": "VLB similaridade 0.30",
            "sdca_firewall": {"decision": "ALLOW", "confidence": 0.8823},
            "math_report": {"coverage": {"ok_modules": 0}},
        }
    )

    assert "CRITICAL_OUTPUT_REQUIREMENT" not in prompt
    assert "MISSING -- confidence reduced" not in prompt
    assert "VLB" not in prompt
    assert ":8002" in prompt
    assert "Coracao" in prompt
    assert "USER: bob , me explica sua arquitetura" in prompt


def test_ticker_prompt_keeps_evidence_contract():
    from core.pipeline.prompts.builder import build_agent_prompt

    prompt = build_agent_prompt(
        {
            "message": "analisa AAPL",
            "intent": "bob_decides",
            "route": "agent",
            "ticker": "AAPL",
            "data_context": "price=100",
        }
    )

    assert "VOZ:" in prompt
    assert "opiniao" in prompt
    assert "CRITICAL_OUTPUT_REQUIREMENT" not in prompt
    assert "AAPL" in prompt


def test_verdict_template_does_not_demand_missing_modules():
    from core.pipeline.nodes.agent import _add_verdict_template

    messages: list[dict[str, str]] = []
    _add_verdict_template(
        messages,
        {
            "message": "bob , me explica sua arquitetura",
            "intent": "bob_decides",
            "rag_context": "VLB similaridade 0.30",
        },
    )

    content = messages[0]["content"]
    assert "arquitetura" in content
    assert "DADOS DO PIPELINE: RSI" not in content
    assert "VLB" not in content


@pytest.mark.asyncio
async def test_architecture_question_skips_market_organs(monkeypatch):
    from src.core.pipeline import graph as graph_module

    events: list[dict] = []
    monkeypatch.setattr(graph_module, "get_stream_writer", lambda: events.append)

    class FakeHub:
        def calculate_all(self, state):
            raise AssertionError("MathHub must not run for an architecture question")

        def to_deepseek_prompt(self, report):
            raise AssertionError("math prompt must not run")

    async def fake_sdca(state):
        raise AssertionError("SDCA must not run")

    async def fake_guard(state):
        raise AssertionError("guardrail hub must not run")

    monkeypatch.setattr(graph_module, "MathHub", FakeHub)
    monkeypatch.setattr(graph_module, "node_sdca_firewall", fake_sdca)
    monkeypatch.setattr(graph_module, "node_guardrail_hub", fake_guard)

    result = await graph_module._auto_full_analysis(
        {
            "run_id": "arch",
            "route": "agent",
            "intent": "bob_decides",
            "ticker": "VLB",
            "message": "bob , me explica sua arquitetura",
            "rag_context": "VLB similaridade 0.30",
            "errors": [],
        }
    )

    assert result["skip_trinity"] is True
    assert result["rag_context"] == ""
    assert result["ticker"] == ""
    assert "VLB" not in str(events)
