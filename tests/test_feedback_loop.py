"""Tests for the paper-trading feedback loop (C7)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from core.trading.feedback_loop import FeedbackLoop
from core.trading.paper_journal import PaperJournal, PaperTrade


def _add_closed_trade(
    journal: PaperJournal,
    trade_id: str,
    *,
    win: bool,
    verdict: str,
) -> None:
    entry_dt = datetime.now(timezone.utc) - timedelta(days=1)
    trade = PaperTrade(
        trade_id=trade_id,
        ticker="NVDA" if win else "TSLA",
        thesis="momentum breakout with volume",
        direction="long",
        entry_date=entry_dt.isoformat(),
        entry_price=100,
        shares=10,
        entry_reasoning="test setup",
        verdict_at_entry=verdict,
        risk_assessment="moderate",
        expected_holding_period="swing",
    )
    journal.open_trade(trade)
    journal.close_trade(
        trade_id,
        exit_price=110 if win else 90,
        exit_reason="take_profit" if win else "stop_loss",
        exit_date=(entry_dt + timedelta(hours=6)).isoformat().replace("+00:00", "Z"),
    )


def test_confidence_bias_detects_overconfidence(tmp_path):
    journal = PaperJournal(tmp_path / "journal.jsonl")
    for index in range(10):
        _add_closed_trade(
            journal,
            f"trade-{index}",
            win=index < 3,
            verdict="BUY_CANDIDATE confidence 80",
        )

    loop = FeedbackLoop(
        journal_path=journal.path,
        learning_log_path=tmp_path / "learning.jsonl",
    )
    report = loop.analyze_confidence_bias()

    assert report["status"] == "analyzed"
    assert report["bias"] == "overconfidence"
    assert report["confidence_sample_size"] == 10
    assert report["win_rate"] == 0.3
    assert len(report["high_confidence_losses"]) == 7


def test_confidence_bias_requires_recorded_confidence(tmp_path):
    journal = PaperJournal(tmp_path / "journal.jsonl")
    for index in range(10):
        _add_closed_trade(
            journal,
            f"trade-{index}",
            win=index < 5,
            verdict="BUY_CANDIDATE",
        )

    loop = FeedbackLoop(
        journal_path=journal.path,
        learning_log_path=tmp_path / "learning.jsonl",
    )
    report = loop.analyze_confidence_bias()

    assert report["status"] == "missing_confidence_data"
    assert report["bias"] == "confidence_not_recorded"


def test_learning_cycle_includes_bias_report_without_real_memory_write(tmp_path):
    journal = PaperJournal(tmp_path / "journal.jsonl")
    for index in range(10):
        _add_closed_trade(
            journal,
            f"trade-{index}",
            win=index < 3,
            verdict="BUY_CANDIDATE confidence 80",
        )

    loop = FeedbackLoop(
        journal_path=journal.path,
        learning_log_path=tmp_path / "learning.jsonl",
    )
    results = loop.run_learning_cycle(record_memory=False)

    assert results["bias_report"]["bias"] == "overconfidence"
    assert results["theses_closed"] == 0
    assert "CALIBRACAO BOB VS OUTCOME" in results["bob_context"]
