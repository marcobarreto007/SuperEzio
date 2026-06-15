import pytest

from core.pipeline.nodes.trinity import node_trinity


class RecordingGateway:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    async def chat_completion(self, **kwargs):
        self.calls.append(kwargs)
        return self.responses.pop(0)


def _state():
    return {
        "run_id": "trinity-test",
        "ticker": "TLRY",
        "data": {
            "ticker": "TLRY",
            "sentiment": {
                "source": "news_scout_multisource",
                "sentiment_label": "bullish",
                "sentiment_score": 0.3,
                "news_count": 8,
                "top_headline": "TLRY Joins European Cannabis Talks",
            },
            "reddit": {
                "signal_label": "spike 12x normal",
                "qualified_count": 5,
                "total_posts": 340,
                "suspicious_accounts": ["acct1", "acct2", "acct3"],
                "top_posts": [{"title": "TLRY getting coordinated attention"}],
            },
        },
        "math_report": {
            "ticker": "TLRY",
            "summary": {
                "latest_price": 1.85,
                "return_annualized": -0.011,
                "volatility_annualized": 0.029,
                "sharpe": -39.2,
                "max_drawdown": -0.039,
                "var_95": -0.003,
                "crisis_score": 0.2,
            },
            "modules": {
                "dcf_proxy": {
                    "status": "ok",
                    "values": {"dcf_value_per_share": 1.10},
                },
                "crisis_aggregate": {
                    "status": "ok",
                    "values": {"regime": "normal", "aggregate_score": 0.2},
                },
            },
        },
    }


@pytest.mark.asyncio
async def test_node_trinity_skips_without_gateway():
    result = await node_trinity(_state(), gateway=None)

    assert result["trinity_blocked"] is False
    assert result["trinity_structured"]["skipped"] is True
    assert "Trinity skipped: gateway_unavailable" in result["trinity_report"]
    assert "[MATH_CONTEXT]" in result["math_prompt"]
    assert "[SENTIMENT_CONTEXT]" in result["sentiment_prompt"]


@pytest.mark.asyncio
async def test_node_trinity_runs_deep_and_genie_followups():
    gateway = RecordingGateway(
        [
            '{"verdict":"OVERVALUED","confidence":68,"bob_readable":"DCF below market."}',
            '{"verdict":"OVERVALUED","confidence":72,"bob_readable":"Still below market."}',
            '{"verdict":"SUSPICIOUS","confidence":72,"bob_readable":"Reddit spike looks coordinated."}',
            '{"verdict":"SUSPICIOUS","confidence":80,"bob_readable":"Duplicate social pattern confirmed."}',
        ]
    )

    result = await node_trinity(_state(), gateway=gateway)

    assert len(gateway.calls) == 4
    assert gateway.calls[0]["preferred_provider"] == "deepseek"
    assert "[MATH_CONTEXT]" in gateway.calls[0]["messages"][1]["content"]
    assert "DCF fair value" in gateway.calls[1]["messages"][1]["content"]
    assert gateway.calls[2]["preferred_provider"] == "gemini"
    assert "[SENTIMENT_CONTEXT]" in gateway.calls[2]["messages"][1]["content"]
    assert "Reddit/social spike" in gateway.calls[3]["messages"][1]["content"]
    assert "GENIE (sentiment)" in result["trinity_report"]
    assert "DEEP (fundamental)" in result["trinity_report"]
    assert "CONSENSUS: Both negative. No divergence." in result["trinity_report"]
    assert result["trinity_structured"]["bob_decision"] == "WAIT"
    assert result["trinity_blocked"] is False


@pytest.mark.asyncio
async def test_node_trinity_marks_unanimous_block():
    gateway = RecordingGateway(
        [
            '{"verdict":"BLOCK","confidence":90,"bob_readable":"Math blocks it."}',
            '{"verdict":"AVOID","confidence":91,"bob_readable":"Social risk blocks it."}',
        ]
    )
    state = _state()
    state["math_report"]["modules"]["dcf_proxy"]["values"]["dcf_value_per_share"] = 1.84
    state["data"]["reddit"] = {"signal_label": "neutral", "qualified_count": 0}

    result = await node_trinity(state, gateway=gateway)

    assert len(gateway.calls) == 2
    assert result["trinity_blocked"] is True
    assert result["trinity_structured"]["bob_decision"] == "BLOCK"
    assert "BLOCK unanimous" in result["trinity_report"]
