"""Tests for Stage 5 paper trading daily cycle."""

from __future__ import annotations

import pytest

from core.trading.daily_cycle import DailyCycle
from core.trading.paper_journal import PaperJournal


class FakePipeline:
    async def stream_events(self, message: str, **kwargs):
        yield {"type": "PIPELINE_STEP", "step": "graph", "status": "started"}
        yield {"type": "PAPER_EXEC", "ticker": kwargs.get("ticker", "AAPL"), "qty": 1}
        yield {"type": "PIPELINE_STEP", "step": "graph", "status": "completed"}


class FakePulse:
    def get_all_pulses(self):
        return [{"ticker": "AAPL", "sentiment": "NEUTRAL"}]


@pytest.mark.asyncio
async def test_morning_routine_reports_operational_state(tmp_path):
    journal = PaperJournal(tmp_path / "journal.jsonl")
    cycle = DailyCycle(journal=journal, sentiment_pulse=FakePulse())

    result = await cycle.morning_routine()

    assert result["phase"] == "morning"
    assert "kill_switch" in result
    assert "approvals" in result
    assert result["sentiment"]["count"] == 1


@pytest.mark.asyncio
async def test_trading_session_streams_pipeline_events(tmp_path):
    journal = PaperJournal(tmp_path / "journal.jsonl")
    cycle = DailyCycle(pipeline=FakePipeline(), journal=journal)

    result = await cycle.trading_session("paper train AAPL", ticker="AAPL")

    assert result["status"] == "completed"
    assert result["event_count"] == 3
    assert result["paper_events"][0]["type"] == "PAPER_EXEC"


@pytest.mark.asyncio
async def test_evening_routine_returns_postmortem(tmp_path):
    journal = PaperJournal(tmp_path / "journal.jsonl")
    cycle = DailyCycle(journal=journal)

    result = await cycle.evening_routine()

    assert result["phase"] == "evening"
    assert "performance" in result
    assert "biases" in result
