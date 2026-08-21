"""Contract tests for expert nodes: fan-out execution and result collection."""

import src.core.pipeline.nodes.experts as experts_node
from src.core.pipeline.nodes.experts import (
    EXPERT_PROVIDERS,
    calculate_weighted_expert_consensus,
    node_collect_experts,
    node_expert,
)


def test_learned_weights_change_deterministic_consensus():
    verdicts = {
        "fundamental_value": {"verdict": "UNDERVALUED", "confidence": 90},
        "macro_risk": {"verdict": "RISK_OFF", "confidence": 90},
    }

    fundamental_dominates = calculate_weighted_expert_consensus(
        verdicts, {"fundamental_value": 0.8, "macro_risk": 0.2}
    )
    risk_dominates = calculate_weighted_expert_consensus(
        verdicts, {"fundamental_value": 0.2, "macro_risk": 0.8}
    )

    assert fundamental_dominates["decision"] == "SUPPORT"
    assert risk_dominates["decision"] == "BLOCK"
    assert fundamental_dominates["score"] == -risk_dominates["score"]


def _noop_writer(_event: dict) -> None:
    return None


def test_expert_providers_has_required_roles():
    required = {"macro_risk", "fundamental_value", "momentum_technical", "contrarian_opportunity"}
    assert required.issubset(set(EXPERT_PROVIDERS))
    for role in required:
        assert EXPERT_PROVIDERS[role] == "deepseek"


def test_node_expert_skips_when_gateway_none():
    """Expert must skip gracefully when gateway is None."""
    import asyncio

    experts_node.get_stream_writer = lambda: _noop_writer

    async def _run():
        return await node_expert(
            {
                "role": "fundamental",
                "ticker": "AAPL",
                "data_context": "price=150",
                "run_id": "test-exp-1",
            },
            gateway=None,
        )

    result = asyncio.run(_run())
    assert "expert_results" in result
    assert isinstance(result["expert_results"], list)
    assert len(result["expert_results"]) == 1
    assert result["expert_results"][0]["ok"] is False
    assert result["expert_results"][0]["role"] == "fundamental"
    assert "gateway_unavailable" in result["expert_results"][0]["error"]


def test_expert_call_model():
    from src.core.pipeline.contracts import ExpertCall

    call = ExpertCall(role="technical", ticker="MSFT")
    assert call.role == "technical"
    assert call.ticker == "MSFT"
    assert call.context == ""
    assert call.provider_name == ""
    assert call.timeout == 60.0


def test_node_collect_experts_empty_results():
    """Collect with no expert results returns skip summary."""
    import asyncio

    experts_node.get_stream_writer = lambda: _noop_writer

    async def _run():
        return await node_collect_experts(
            {
                "run_id": "test-collect-empty",
                "route": "general",
            }
        )

    result = asyncio.run(_run())
    assert "expert_summary" in result
    assert "not triggered" in result["expert_summary"]


def test_node_collect_experts_with_results():
    """Collect with expert results produces summary."""
    import asyncio

    experts_node.get_stream_writer = lambda: _noop_writer

    async def _run():
        return await node_collect_experts(
            {
                "run_id": "test-collect-results",
                "route": "ticker_analysis",
                "expert_results": [
                    {"role": "fundamental", "ok": True, "response": "Strong buy, PE=15"},
                    {"role": "technical", "ok": True, "response": "RSI=45, neutral"},
                    {"role": "risk", "ok": False, "error": "timeout"},
                ],
            }
        )

    result = asyncio.run(_run())
    assert "expert_summary" in result
    summary = result["expert_summary"]
    # New JSON-aware format — experts output structured summaries
    assert "fundamental" in summary
    assert "technical" in summary
    assert "risk" in summary
    assert "FAILED" in summary
    assert "timeout" in summary


def test_node_collect_experts_parses_json_and_preserves_zero_score(monkeypatch):
    """Structured expert JSON should become Bob-readable without losing 0.0 scores."""
    import asyncio

    experts_node.get_stream_writer = lambda: _noop_writer
    monkeypatch.setattr(
        experts_node,
        "get_effective_expert_weights",
        lambda: {"sentiment": 0.4, "fundamental_value": 0.6},
    )

    async def _run():
        return await node_collect_experts(
            {
                "run_id": "test-collect-json-score-zero",
                "route": "ticker_analysis",
                "expert_results": [
                    {
                        "role": "sentiment",
                        "ok": True,
                        "response": (
                            'Here is the JSON: {"expert":"sentiment","ticker":"XYZ",'
                            '"verdict":"NEUTRAL","confidence":72,"sentiment_score":0.0,'
                            '"top_signals":["low message volume"],'
                            '"bob_readable":"Sentiment is balanced, with no strong crowd edge."}'
                        ),
                    }
                ],
            }
        )

    result = asyncio.run(_run())
    assert result["expert_structured"]["sentiment"]["verdict"] == "NEUTRAL"
    assert result["expert_structured"]["sentiment"]["sentiment_score"] == 0.0
    assert result["expert_weights"]["sentiment"] == 0.4
    assert result["expert_summary"].find("reliability=0.400") > -1
    assert "score=0.0" in result["expert_summary"]
    assert "Sentiment is balanced" in result["expert_summary"]


def test_node_expert_red_team_fallback_survives_stray_braces_in_context(monkeypatch):
    """Regression: red_team_agent_N (not in EXPERT_PROMPTS) must not crash with
    KeyError('provider') when data_context contains literal "{...}" text
    (e.g. a dict-repr fragment like "{provider}" copied from another
    expert's raw output). See docs/audit — the fallback prompt used to be
    built via f-string and then re-passed through .format(), which made
    str.format() treat any stray "{name}" inside the context as a
    placeholder and raise KeyError.
    """
    import asyncio

    experts_node.get_stream_writer = lambda: _noop_writer
    monkeypatch.setenv("SUPEREZIO_DEEPSEEK_MAX_TOKENS", "1800")

    class _FakeGateway:
        last_provider_used = "deepseek"
        calls = []

        async def chat_completion(self, **kwargs):
            self.calls.append(kwargs)
            # Prove the prompt actually built successfully and reached here.
            assert "{provider}" in kwargs["messages"][1]["content"]
            return '{"verdict":"NEUTRAL","confidence":50}'

    async def _run():
        return await node_expert(
            {
                "role": "red_team_agent_1",
                "ticker": "XYZ",
                "data_context": "prior expert says: {provider} used deepseek and returned NEUTRAL",
                "run_id": "test-red-team-braces",
            },
            gateway=_FakeGateway(),
        )

    result = asyncio.run(_run())
    assert result["expert_results"][0]["ok"] is True
    assert result["expert_results"][0].get("error") is None
    assert _FakeGateway.calls[0]["allow_fallback"] is False
    assert _FakeGateway.calls[0]["max_tokens"] == 1800


def test_node_collect_experts_partial_data_without_results():
    """Partial data quality with no expert results flags error."""
    import asyncio

    experts_node.get_stream_writer = lambda: _noop_writer

    async def _run():
        return await node_collect_experts(
            {
                "run_id": "test-collect-partial",
                "route": "ticker_analysis",
                "data": {"data_quality": "partial"},
            }
        )

    result = asyncio.run(_run())
    assert "expert_summary" in result
    assert "errors" in result
    assert "partial_data_without_expert_results" in result["errors"]
