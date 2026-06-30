from core.math.math_hub import MathHub
from core.pipeline.prompts.math_prompt import format_math_context


def _sample_state():
    candles = []
    for i in range(30):
        close = 10.0 + i * 0.2
        candles.append(
            {
                "open": close - 0.1,
                "high": close + 0.2,
                "low": close - 0.2,
                "close": close,
                "volume": 100000 + i * 1000,
            }
        )
    return {
        "run_id": "math-hub-test",
        "ticker": "AAPL",
        "data": {
            "ticker": "AAPL",
            "price": {"current": candles[-1]["close"]},
            "ohlcv": candles,
            "profile": {
                "free_cash_flow": 10_000_000,
                "shares_outstanding": 1_000_000,
            },
        },
    }


def test_math_hub_calculates_report_with_coverage():
    report = MathHub().calculate_all(_sample_state())

    assert report["ticker"] == "AAPL"
    assert report["coverage"]["total_modules"] == 14
    assert report["coverage"]["ok_modules"] >= 8
    assert report["modules"]["technical_indicators"]["status"] == "ok"
    assert report["modules"]["var_cvar"]["status"] == "ok"
    assert report["summary"]["latest_price"] == 15.8


def test_math_hub_renders_numeric_prompt():
    report = MathHub().calculate_all(_sample_state())
    prompt = MathHub.to_deepseek_prompt(report)

    assert "[MATH_CONTEXT]" in prompt
    assert "Ticker: AAPL" in prompt
    assert "Sharpe=" in prompt
    assert "VaR_95=" in prompt
    assert "[/MATH_CONTEXT]" in prompt
    assert len(prompt.splitlines()) <= 8


def test_format_math_context_is_compact_and_hides_crisis_details():
    prompt = format_math_context(
        {
            "ticker": "AAPL",
            "summary": {
                "latest_price": 215.30,
                "return_annualized": -0.011,
                "volatility_annualized": 0.029,
                "sharpe": -39.24,
                "max_drawdown": -0.039,
                "var_95": -0.0031,
                "kelly_fraction": None,
                "crisis_score": 0.2,
            },
            "modules": {
                "technical_indicators": {
                    "status": "ok",
                    "values": {"vwap": 210.956, "rsi14": None, "macd": None},
                },
                "crisis_aggregate": {
                    "status": "ok",
                    "values": {
                        "regime": "normal",
                        "aggregate_score": 0.2,
                        "model_scores": [{"name": "hidden"}],
                    },
                },
            },
        }
    )

    lines = prompt.splitlines()
    assert lines[0] == "[MATH_CONTEXT]"
    assert lines[-1] == "[/MATH_CONTEXT]"
    assert len(lines) <= 8
    assert "Price: $215.30" in prompt
    assert "annualized=-1.1%" in prompt
    assert "volatility=2.9%" in prompt
    assert "VaR_95=-$0.67" in prompt
    assert "Kelly=N/A" in prompt
    assert "regime=NORMAL | score=20/100 (low risk)" in prompt
    assert "VWAP=$210.96" in prompt
    assert "model_scores" not in prompt
    assert "{" not in prompt
