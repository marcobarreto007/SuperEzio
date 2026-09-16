"""Peça 3: janela assimétrica de causa. Sem LLM."""

from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo

from core.heart.attribution import session_impact_date

ET = ZoneInfo("America/New_York")


def test_filing_after_regular_close_explains_the_next_session():
    occurred = datetime(2026, 9, 15, 16, 10, tzinfo=ET)
    assert session_impact_date(occurred) == date(2026, 9, 16)


def test_filing_during_the_session_explains_the_same_day():
    occurred = datetime(2026, 9, 15, 9, 0, tzinfo=ET)
    assert session_impact_date(occurred) == date(2026, 9, 15)


def test_exact_close_is_next_session():
    occurred = datetime(2026, 9, 15, 16, 0, tzinfo=ET)
    assert session_impact_date(occurred) == date(2026, 9, 16)
