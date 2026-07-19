from datetime import datetime, timedelta, timezone

from core.trading.feedback_loop import FeedbackLoop
from core.trading.paper_journal import PaperJournal, PaperTrade
from core.trading.xp_system import XPSystem


def test_xp_trade_outcome_is_idempotent_across_reload(tmp_path):
    path = tmp_path / "xp.jsonl"
    xp = XPSystem(path)

    first = xp.record_trade_outcome("win", pnl_amount=100.0, trade_id="trade-001")
    replay = xp.record_trade_outcome("win", pnl_amount=100.0, trade_id="trade-001")
    reloaded = XPSystem(path)
    after_restart = reloaded.record_trade_outcome("win", pnl_amount=100.0, trade_id="trade-001")

    assert replay.event_id == first.event_id
    assert after_restart.event_id == first.event_id
    assert reloaded.get_stats().events_count == 1


def test_feedback_cycle_does_not_repeat_xp_or_streak(tmp_path):
    journal = PaperJournal(tmp_path / "journal.jsonl")
    entry_date = datetime.now(timezone.utc) - timedelta(hours=2)
    exit_date = entry_date + timedelta(hours=1)
    for index in range(3):
        trade = PaperTrade(
            trade_id=f"trade-{index}",
            ticker="AAPL",
            thesis="test",
            direction="long",
            entry_date=entry_date.isoformat(),
            entry_price=100.0,
            shares=1,
            entry_reasoning="test",
            verdict_at_entry="BUY confidence 80",
            risk_assessment="test",
            expected_holding_period="swing",
        )
        journal.open_trade(trade)
        journal.close_trade(
            trade.trade_id,
            exit_price=110.0,
            exit_date=exit_date.isoformat(),
        )

    xp = XPSystem(tmp_path / "xp.jsonl")
    loop = FeedbackLoop(
        journal_path=journal.path,
        learning_log_path=tmp_path / "learning.jsonl",
        outcome_db_path=tmp_path / "outcomes.sqlite3",
        xp_system=xp,
    )
    loop.run_learning_cycle(record_memory=False)
    first_count = xp.get_stats().events_count
    loop.run_learning_cycle(record_memory=False)

    assert first_count == 4  # three outcomes plus one win-streak event
    assert xp.get_stats().events_count == first_count
