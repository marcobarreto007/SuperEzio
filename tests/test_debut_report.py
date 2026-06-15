"""Tests for the Stage 5 debut report."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from scripts.debut_report import build_debut_report
from core.trading.paper_journal import PaperJournal, PaperTrade


def _add_aged_closed_trade(
    journal: PaperJournal,
    trade_id: str,
    *,
    win: bool,
    as_of: datetime,
) -> None:
    entry_dt = as_of - timedelta(days=20)
    trade = PaperTrade(
        trade_id=trade_id,
        ticker="NVDA",
        thesis="breakout momentum with volume",
        direction="long",
        entry_date=entry_dt.isoformat(),
        entry_price=100,
        shares=10,
        entry_reasoning="test setup",
        verdict_at_entry="BUY_CANDIDATE confidence 80",
        risk_assessment="moderate",
        expected_holding_period="swing",
    )
    journal.open_trade(trade)
    journal.close_trade(
        trade_id,
        exit_price=110 if win else 90,
        exit_reason="take_profit" if win else "stop_loss",
        exit_date=(entry_dt + timedelta(days=3)).isoformat(),
    )


def test_debut_report_marks_c6_c7_when_sample_is_proven(tmp_path):
    as_of = datetime(2026, 6, 15, tzinfo=timezone.utc)
    journal = PaperJournal(tmp_path / "paper_journal.jsonl")
    for index in range(10):
        _add_aged_closed_trade(journal, f"trade-{index}", win=index < 3, as_of=as_of)

    journal.review_aged_closed_theses(now=as_of, record_memory=False)

    report = build_debut_report(
        journal_path=journal.path,
        days=14,
        min_trades=10,
        as_of=as_of,
    )

    assert "=== SUPEREZIO DEBUT REPORT ===" in report
    assert "C6 Track result              [OK] PROVEN" in report
    assert "C7 Learn from errors         [OK] PROVEN" in report
    assert "C8 Never execute live        [OK] PROVEN" in report
    assert "Bias: overconfidence (analyzed)" in report
    assert "Trades: 10 (3 wins, 7 losses)" in report


def test_debut_report_keeps_c6_c7_pending_without_sample(tmp_path):
    as_of = datetime(2026, 6, 15, tzinfo=timezone.utc)
    journal = PaperJournal(tmp_path / "paper_journal.jsonl")

    report = build_debut_report(
        journal_path=journal.path,
        days=14,
        min_trades=10,
        as_of=as_of,
    )

    assert "C5 Register thesis           [..] PENDING" in report
    assert "C6 Track result              [..] PENDING" in report
    assert "C7 Learn from errors         [..] PENDING" in report
    assert "RECOMMENDATION: CONTINUE PAPER until C6/C7 sample is proven." in report
