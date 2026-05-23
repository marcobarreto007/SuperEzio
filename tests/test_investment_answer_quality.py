from scripts.investment_answer_quality import evaluate_answer_quality


def test_rejects_bad_fallback_text():
    result = evaluate_answer_quality(
        "Should I dollar-cost average or wait?",
        "I couldn't decide on a tool. The request might be malformed.",
    )

    assert not result["ok"]
    assert any(reason.startswith("bad_fallback_text") for reason in result["reasons"])


def test_rejects_fake_ticker():
    result = evaluate_answer_quality(
        "Give me an allocation.",
        "Allocate 20% to VOOE as a money market ETF.",
    )

    assert not result["ok"]
    assert "fake_ticker:VOOE" in result["reasons"]


def test_rejects_spy_vti_overlap_in_allocation():
    result = evaluate_answer_quality(
        "Give me an allocation with percentages.",
        "Allocate 40% to SPY, 25% to VTI, 20% to BND, and 15% to cash.",
    )

    assert not result["ok"]
    assert "etf_overlap:SPY/VTI" in result["reasons"]


def test_allows_etf_comparison():
    result = evaluate_answer_quality(
        "Compare VOO, VTI, and SCHD.",
        (
            "VOO tracks the S&P 500. VTI covers the total US market. "
            "SCHD focuses on dividend quality. Recommendation: choose VTI "
            "for broad long-term exposure."
        ),
    )

    assert result["ok"]
