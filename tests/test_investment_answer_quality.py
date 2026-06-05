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


def test_rejects_etf_semantic_mismatch():
    result = evaluate_answer_quality(
        "Give me a portfolio allocation with percentages and tickers.",
        (
            "Allocate 50% to VOO for US large caps, 20% to VXUS, "
            "15% to US Small Cap Value (VTV), 10% to BND, and 5% to VNQ."
        ),
        min_chars=20,
    )

    assert not result["ok"]
    assert "etf_semantic_mismatch:VTV:small_cap" in result["reasons"]


def test_allows_correct_small_cap_value_ticker():
    result = evaluate_answer_quality(
        "Give me a portfolio allocation with percentages and tickers.",
        (
            "Allocate 50% to VOO for US large caps, 20% to VXUS, "
            "15% to US Small Cap Value (VBR), 10% to BND, and 5% to VNQ."
        ),
        min_chars=20,
    )

    assert result["ok"]


def test_rejects_mutual_fund_mislabeled_as_bond_etf():
    result = evaluate_answer_quality(
        "Give me a portfolio allocation with percentages and tickers.",
        (
            "Allocate 50% to VOO, 20% to VEA, 15% to IJR, "
            "10% to Investment Grade Bond ETF (VWENX), and 5% to VNQ."
        ),
        min_chars=20,
    )

    assert not result["ok"]
    assert "fund_semantic_mismatch:VWENX:not_etf" in result["reasons"]


def test_rejects_unsourced_macro_precision_for_dca_advice():
    result = evaluate_answer_quality(
        "With current interest rates and market volatility, should I dollar-cost average or wait?",
        "Rates are near 4.8%, VIX is 18-22, and markets outperformed cash by 2.3% annually.",
        min_chars=20,
    )

    assert not result["ok"]
    assert "unsupported_macro_precision" in result["reasons"]


def test_rejects_tax_overstatement_for_dividend_advice():
    result = evaluate_answer_quality(
        "Build a passive income portfolio with dividend stocks. Consider tax efficiency and withholding taxes.",
        "Use a Canadian-listed U.S. ETF to avoid the 15% withholding tax.",
        min_chars=20,
    )

    assert not result["ok"]
    assert "tax_overstatement" in result["reasons"]


def test_rejects_rrsp_treaty_tax_overstatement_for_dividend_advice():
    result = evaluate_answer_quality(
        "Build a passive income portfolio with dividend stocks. Consider tax efficiency and withholding taxes.",
        (
            "US dividend stocks or ETFs held in an RRSP avoid the 15% US withholding tax "
            "thanks to the Canada-US tax treaty."
        ),
        min_chars=20,
    )

    assert not result["ok"]
    assert "tax_overstatement" in result["reasons"]


def test_rejects_tax_overstatement_for_concentrated_position():
    result = evaluate_answer_quality(
        "I hold a concentrated position in AAPL. How should I diversify without triggering a huge tax bill?",
        "Use your annual $25K long-term capital gains exemption.",
        min_chars=20,
    )

    assert not result["ok"]
    assert "tax_overstatement" in result["reasons"]


def test_rejects_currency_hedge_tax_overstatement_for_concentrated_position():
    result = evaluate_answer_quality(
        "I hold a concentrated position in AAPL. How should I diversify without triggering a huge tax bill?",
        (
            "Use an S&P 500 index ETF for U.S. exposure without currency hedging "
            "to avoid dividend withholding tax drag."
        ),
        min_chars=20,
    )

    assert not result["ok"]
    assert "tax_overstatement" in result["reasons"]


def test_rejects_transfer_in_kind_tax_overstatement_for_concentrated_position():
    result = evaluate_answer_quality(
        "I hold a concentrated position in AAPL. How should I diversify without triggering a huge tax bill?",
        (
            "Shift existing AAPL shares via a transfer-in-kind into a TFSA or RRSP; "
            "diversifying there doesn't trigger a taxable event."
        ),
        min_chars=20,
    )

    assert not result["ok"]
    assert "tax_overstatement" in result["reasons"]
