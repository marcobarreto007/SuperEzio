"""Contracts for the real multi-asset investment validation matrix."""

from __future__ import annotations

import runpy
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _overnight_cases():
    return runpy.run_path(str(ROOT / "scripts" / "overnight_100_tests.py"))["TESTS"]


def test_overnight_matrix_is_stratified_and_not_single_symbol():
    cases = _overnight_cases()
    real_tickers = {
        case.ticker for case in cases if case.ticker and case.stratum not in {"invalid_ticker"}
    }
    strata = {case.stratum for case in cases}

    assert len(cases) == 100
    assert len(real_tickers) >= 20
    assert {"equity_us", "equity_ca", "equity_br", "etf", "crypto", "portfolio"} <= strata
    assert {"macro_no_ticker", "risk_no_ticker", "invalid_ticker", "no_ticker_edge"} <= strata
    assert "AAPL" not in real_tickers


def test_asset_agnostic_questions_do_not_receive_a_hidden_ticker():
    cases = _overnight_cases()
    asset_agnostic = [
        case
        for case in cases
        if case.stratum in {"macro_no_ticker", "risk_no_ticker", "no_ticker_edge"}
    ]

    assert len(asset_agnostic) >= 25
    assert all(case.ticker is None for case in asset_agnostic)
