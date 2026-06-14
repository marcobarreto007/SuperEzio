from core.math.math_hub import MathHub


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
    assert report["coverage"]["total_modules"] == 12
    assert report["coverage"]["ok_modules"] >= 8
    assert report["modules"]["technical_indicators"]["status"] == "ok"
    assert report["modules"]["var_cvar"]["status"] == "ok"
    assert report["summary"]["latest_price"] == 15.8


def test_math_hub_renders_numeric_prompt():
    report = MathHub().calculate_all(_sample_state())
    prompt = MathHub.to_deepseek_prompt(report)

    assert "[MATH_REPORT]" in prompt
    assert "ticker=AAPL" in prompt
    assert "sharpe=" in prompt
    assert "var_95=" in prompt
    assert "[/MATH_REPORT]" in prompt
