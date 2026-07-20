"""Contract tests for MangalaTracker — compound capital tracker.

Each test validates a deterministic property of the tracker
without depending on external state or network.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from src.core.pipeline.nodes.mangala_tracker import (
    MangalaTracker,
    FlipRecord,
    get_mangala_tracker,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_tracker(starting_capital: float = 20.0) -> MangalaTracker:
    """Cria um tracker isolado com journal temporario."""
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".jsonl", mode="w")
    tmp.close()
    return MangalaTracker(
        starting_capital=starting_capital,
        journal_path=Path(tmp.name),
    )


# ---------------------------------------------------------------------------
# FlipRecord dataclass
# ---------------------------------------------------------------------------


def test_flip_record_defaults():
    """FlipRecord preenche campos obrigatorios e defaults."""
    r = FlipRecord(
        ticker="AAPL",
        entry_price=150.0,
        exit_price=155.0,
        shares=10,
        entry_date="2026-07-01",
        exit_date="2026-07-10",
        profit=50.0,
        profit_pct=3.3333,
    )
    assert r.ticker == "AAPL"
    assert r.direction == "long"
    assert r.trade_id == ""
    assert r.tags == []
    assert r.recorded_at is not None


def test_flip_record_to_dict():
    """FlipRecord.to_dict() serializa todos os campos."""
    r = FlipRecord(
        ticker="AAPL",
        entry_price=150.0,
        exit_price=155.0,
        shares=10,
        entry_date="2026-07-01",
        exit_date="2026-07-10",
        profit=50.0,
        profit_pct=3.3333,
    )
    d = r.to_dict()
    assert d["ticker"] == "AAPL"
    assert d["profit"] == 50.0
    assert d["profit_pct"] == 3.3333
    assert "recorded_at" in d


# ---------------------------------------------------------------------------
# MangalaTracker — init
# ---------------------------------------------------------------------------


def test_tracker_defaults():
    """Tracker comeca com $20 e 0 flips."""
    tracker = _make_tracker()
    assert tracker.starting_capital == 20.0
    assert tracker.current_capital == 20.0
    assert len(tracker.trades) == 0


def test_tracker_custom_starting_capital():
    """Tracker aceita capital inicial customizado."""
    tracker = _make_tracker(starting_capital=100.0)
    assert tracker.starting_capital == 100.0
    assert tracker.current_capital == 100.0


def test_tracker_rebuilds_from_journal():
    """Tracker reconstroi estado do journal ao inicializar."""
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".jsonl", mode="w")
    tmp.write(
        json.dumps(
            {
                "ticker": "AAPL",
                "entry_price": 150.0,
                "exit_price": 155.0,
                "shares": 10,
                "entry_date": "2026-07-01",
                "exit_date": "2026-07-10",
                "profit": 50.0,
                "profit_pct": 3.3333,
                "direction": "long",
                "trade_id": "mangala-AAPL-1",
            }
        )
        + "\n"
    )
    tmp.close()

    tracker = MangalaTracker(starting_capital=20.0, journal_path=Path(tmp.name))
    assert len(tracker.trades) == 1
    assert tracker.current_capital == 70.0  # 20 + 50


# ---------------------------------------------------------------------------
# MangalaTracker — record_flip
# ---------------------------------------------------------------------------


def test_record_flip_profit():
    """Flip lucrativo aumenta o capital."""
    tracker = _make_tracker()
    profit = tracker.record_flip(
        ticker="AAPL",
        entry_price=150.0,
        exit_price=155.0,
        shares=10,
    )
    assert profit == 50.0
    assert tracker.current_capital == 70.0
    assert len(tracker.trades) == 1


def test_record_flip_loss():
    """Flip com prejuizo reduz o capital."""
    tracker = _make_tracker()
    profit = tracker.record_flip(
        ticker="AAPL",
        entry_price=155.0,
        exit_price=150.0,
        shares=10,
    )
    assert profit == -50.0
    assert tracker.current_capital == -30.0  # 20 - 50
    assert len(tracker.trades) == 1


def test_record_flip_multiples():
    """Multiplos flips acumulam corretamente."""
    tracker = _make_tracker()
    tracker.record_flip("AAPL", 100, 110, 10)  # profit +100
    tracker.record_flip("MSFT", 200, 190, 5)  # profit -50
    tracker.record_flip("GOOGL", 150, 180, 2)  # profit +60

    assert tracker.current_capital == 130.0  # 20 + 100 - 50 + 60
    assert len(tracker.trades) == 3


def test_record_flip_append_to_journal():
    """Flip e persistido no journal em disco."""
    tracker = _make_tracker()
    tracker.record_flip("AAPL", 100, 110, 10)
    lines = tracker._journal_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    data = json.loads(lines[0])
    assert data["ticker"] == "AAPL"
    assert data["profit"] == 100.0


def test_record_flip_returns_rounded_profit():
    """Profit retornado e arredondado para 2 casas."""
    tracker = _make_tracker()
    profit = tracker.record_flip("AAPL", 100.1234, 110.5678, 3)
    assert profit == round((110.5678 - 100.1234) * 3, 2)


# ---------------------------------------------------------------------------
# MangalaTracker — compound_summary
# ---------------------------------------------------------------------------


def test_compound_summary_empty():
    """Summary com 0 flips reflete estado inicial."""
    tracker = _make_tracker()
    s = tracker.compound_summary()
    assert s["starting"] == 20.0
    assert s["current"] == 20.0
    assert s["total_flips"] == 0
    assert s["win_rate"] == 0.0
    assert s["total_profit"] == 0.0
    assert s["best_flip"] is None
    assert s["worst_flip"] is None
    assert s["growth_pct"] == 0.0
    assert s["next_target"] == 30.0  # 20 * 1.5


def test_compound_summary_with_flips():
    """Summary reflete estatisticas dos flips."""
    tracker = _make_tracker()
    tracker.record_flip("AAPL", 100, 110, 10)  # win +100
    tracker.record_flip("MSFT", 200, 190, 5)  # loss -50
    tracker.record_flip("GOOGL", 50, 60, 10)  # win +100

    s = tracker.compound_summary()
    assert s["starting"] == 20.0
    assert s["current"] == 170.0  # 20 + 100 - 50 + 100
    assert s["total_flips"] == 3
    assert s["wins"] == 2
    assert s["losses"] == 1
    assert s["win_rate"] == pytest.approx(66.67, rel=0.01)
    assert s["total_profit"] == 150.0
    assert s["best_flip"]["ticker"] in ("AAPL", "GOOGL")
    assert s["best_flip"]["profit"] == 100.0
    assert s["worst_flip"]["ticker"] == "MSFT"
    assert s["worst_flip"]["profit"] == -50.0
    assert s["growth_pct"] == pytest.approx(750.0, rel=0.01)  # (170/20 - 1) * 100
    assert s["next_target"] == 255.0  # 170 * 1.5
    assert s["remaining_to_target"] == 85.0
    assert s["progress_pct"] > 0


def test_compound_summary_progress_pct():
    """Progress pct mede avanco ate o proximo milestone (current * 1.5)."""
    tracker = _make_tracker(starting_capital=100.0)
    # 100 -> milestone 150 -> progress = 0%
    s = tracker.compound_summary()
    assert s["progress_pct"] == 0.0

    # 100 -> 125, next_target = 125 * 1.5 = 187.5
    # progress = (125-100)/(187.5-100) * 100 = 25/87.5 * 100 = 28.57%
    tracker.record_flip("AAPL", 100, 125, 1)  # profit +25
    s = tracker.compound_summary()
    assert s["progress_pct"] == pytest.approx(28.57, rel=0.01)


# ---------------------------------------------------------------------------
# MangalaTracker — reset
# ---------------------------------------------------------------------------


def test_reset_clears_trades():
    """Reset limpa trades e mantem capital."""
    tracker = _make_tracker()
    tracker.record_flip("AAPL", 100, 110, 10)
    assert len(tracker.trades) == 1
    tracker.reset()
    assert len(tracker.trades) == 0
    assert tracker.starting_capital == 20.0


def test_reset_with_new_capital():
    """Reset aceita novo capital inicial."""
    tracker = _make_tracker()
    tracker.record_flip("AAPL", 100, 110, 10)
    tracker.reset(new_starting_capital=50.0)
    assert tracker.starting_capital == 50.0
    assert len(tracker.trades) == 0


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------


def test_get_mangala_tracker_singleton():
    """get_mangala_tracker() retorna sempre a mesma instancia."""
    t1 = get_mangala_tracker()
    t2 = get_mangala_tracker()
    assert t1 is t2


# ---------------------------------------------------------------------------
# Integracao com PaperJournal
# ---------------------------------------------------------------------------


def test_flip_syncs_to_paper_journal():
    """Flip no Mangala gera entrada no PaperJournal."""
    # Usando journal temporario para isolar
    import tempfile
    from core.trading.paper_journal import PaperJournal

    tmp_paper = tempfile.NamedTemporaryFile(delete=False, suffix=".jsonl", mode="w")
    tmp_paper.close()
    paper_journal = PaperJournal(path=Path(tmp_paper.name))

    tmp_mangala = tempfile.NamedTemporaryFile(delete=False, suffix=".jsonl", mode="w")
    tmp_mangala.close()
    tracker = MangalaTracker(
        starting_capital=20.0,
        journal_path=Path(tmp_mangala.name),
    )

    # Monkey-patch _sync_to_paper_journal para usar nosso journal de teste
    _original_sync = tracker._sync_to_paper_journal

    def _test_sync(flip):
        try:
            paper_journal.add_trade(
                {
                    "trade_id": flip.get("trade_id"),
                    "ticker": flip.get("ticker"),
                    "direction": flip.get("direction", "long"),
                    "entry_price": flip.get("entry_price"),
                    "exit_price": flip.get("exit_price"),
                    "shares": flip.get("shares"),
                    "entry_date": flip.get("entry_date"),
                    "exit_date": flip.get("exit_date"),
                    "pnl_amount": flip.get("profit"),
                    "pnl_percent": flip.get("profit_pct"),
                    "outcome": "win" if (flip.get("profit") or 0) > 0.01 else "loss",
                    "thesis": f"Mangala flip: {flip.get('ticker')}",
                    "verdict_at_entry": "PASS",
                    "risk_assessment": "test",
                    "expected_holding_period": "swing",
                    "tags": ["mangala", "flip"],
                }
            )
        except Exception:
            pass

    tracker._sync_to_paper_journal = _test_sync  # type: ignore[method-assign]

    tracker.record_flip("AAPL", 150, 155, 10)
    all_paper = paper_journal.list_all()
    assert len(all_paper) >= 1
    assert all_paper[0]["ticker"] == "AAPL"

    # Cleanup temp files
    Path(tmp_paper.name).unlink(missing_ok=True)
    Path(tmp_mangala.name).unlink(missing_ok=True)
