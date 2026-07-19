"""Testes para PaperJournal (C6) e PerformanceEngine (C7)."""

import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import pytest

from core.trading.paper_journal import PaperJournal, PaperTrade
from core.trading.performance_metrics import PerformanceEngine


# Fixtures


@pytest.fixture
def journal():
    """Journal temporario limpo para cada teste."""
    with tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False, mode="w") as f:
        f.write("")
        path = Path(f.name)
    journal = PaperJournal(path)
    yield journal
    # Cleanup
    try:
        path.unlink()
    except OSError:
        pass


@pytest.fixture
def sample_trade():
    return PaperTrade(
        trade_id="test-001",
        ticker="AAPL",
        thesis="AAPL undervalued after earnings pullback",
        direction="long",
        entry_date="2026-06-01T10:00:00Z",
        entry_price=185.50,
        shares=100,
        entry_reasoning="Strong earnings, support at 180, RSI oversold",
        verdict_at_entry="STUDY_MORE",
        risk_assessment="Market risk: moderate. Sector risk: low.",
        expected_holding_period="swing",
    )


# C6: PaperJournal


class TestPaperJournal:
    def test_open_trade(self, journal, sample_trade):
        """Abre um trade e verifica que foi salvo."""
        journal.open_trade(sample_trade)
        assert journal.count() == 1
        opened = journal.list_open()
        assert len(opened) == 1
        assert opened[0]["trade_id"] == "test-001"
        assert opened[0]["ticker"] == "AAPL"
        assert opened[0]["outcome"] is None  # Ainda nao fechado

    def test_decision_snapshot_survives_close(self, journal, sample_trade):
        sample_trade.confidence_at_entry = 0.82
        sample_trade.risk_at_entry = 250.0
        sample_trade.expert_attribution = {"crisis": 0.7, "fundamental": 0.9}
        journal.open_trade(sample_trade)

        journal.close_trade("test-001", exit_price=195.0, exit_reason="take_profit")
        stored = journal.list_closed()[0]

        assert stored["confidence_at_entry"] == pytest.approx(0.82)
        assert stored["risk_at_entry"] == pytest.approx(250.0)
        assert stored["expert_attribution"] == {"crisis": 0.7, "fundamental": 0.9}

    def test_auto_journal_maps_buy_to_long_and_captures_experts(self, monkeypatch):
        import core.trading.paper_journal as journal_module
        from core.pipeline.nodes.auto_execute_paper import _journal_trade

        captured = {}

        class FakeJournal:
            def open_trade(self, trade):
                captured["trade"] = trade
                return trade.trade_id

        monkeypatch.setattr(journal_module, "PaperJournal", FakeJournal)
        trade_id = _journal_trade(
            {
                "message": "buy thesis",
                "expert_results": [
                    {
                        "role": "crisis",
                        "ok": True,
                        "confidence": 70,
                        "verdict": "BEARISH",
                    },
                    {
                        "role": "fundamental",
                        "ok": True,
                        "confidence": 0.9,
                        "verdict": "BULLISH",
                    },
                ],
                "f51_verdict": {
                    "decision_score": 0.8,
                    "score_type": "uncalibrated_decision_score",
                },
                "neural_decision": {
                    "status": "ready",
                    "decision": "UP",
                    "direction_prob": {"up": 0.7, "down": 0.1, "sideways": 0.2},
                    "calibration_status": "calibrated",
                    "model_id": "neural-test-v1",
                    "as_of": "2026-07-19T12:00:00+00:00",
                    "horizon": 1,
                },
                "adaptive_config": {"stop_loss_pct": 0.05},
            },
            {},
            "AAPL",
            "buy",
            10,
            100.0,
            "run-001",
        )

        assert trade_id == "bob-run-001"
        assert captured["trade"].direction == "long"
        assert captured["trade"].confidence_at_entry == pytest.approx(0.7)
        assert captured["trade"].prediction_probability_at_entry == pytest.approx(0.7)
        assert captured["trade"].model_id == "neural-test-v1"
        assert captured["trade"].risk_at_entry == pytest.approx(50.0)
        assert captured["trade"].expert_attribution == {
            "crisis": 0.7,
            "fundamental": 0.9,
        }
        assert captured["trade"].expert_predictions["crisis"]["direction"] == "DOWN"
        assert captured["trade"].expert_predictions["fundamental"]["direction"] == "UP"

    def test_close_trade_long_win(self, journal, sample_trade):
        """Fecha um trade long com lucro."""
        journal.open_trade(sample_trade)
        closed = journal.close_trade("test-001", exit_price=195.00, exit_reason="take_profit")
        assert closed is not None
        assert closed.outcome == "win"
        assert closed.pnl_amount == pytest.approx(950.00, rel=0.01)
        assert closed.pnl_percent == pytest.approx(5.12, rel=0.1)

    def test_close_trade_long_loss(self, journal, sample_trade):
        """Fecha um trade long com prejuizo."""
        journal.open_trade(sample_trade)
        closed = journal.close_trade("test-001", exit_price=175.00, exit_reason="stop_loss")
        assert closed.outcome == "loss"
        assert closed.pnl_amount == pytest.approx(-1050.00, rel=0.01)

    def test_close_trade_short_win(self, journal):
        """Fecha um trade short com lucro."""
        trade = PaperTrade(
            trade_id="test-short-001",
            ticker="TSLA",
            thesis="TSLA overbought",
            direction="short",
            entry_date="2026-06-01T10:00:00Z",
            entry_price=250.00,
            shares=50,
            entry_reasoning="Overbought RSI, resistance at 260",
            verdict_at_entry="SMALL_POSITION",
            risk_assessment="High volatility",
            expected_holding_period="day_trade",
        )
        journal.open_trade(trade)
        closed = journal.close_trade("test-short-001", exit_price=240.00, exit_reason="take_profit")
        assert closed.outcome == "win"
        assert closed.pnl_amount == pytest.approx(500.00, rel=0.01)  # (250-240)*50

    def test_list_open_vs_closed(self, journal, sample_trade):
        """Diferencia trades abertos de fechados."""
        # Trade 1: aberto
        journal.open_trade(sample_trade)
        # Trade 2: aberto e fechado
        t2 = PaperTrade(
            trade_id="test-002",
            ticker="MSFT",
            thesis="test",
            direction="long",
            entry_date="2026-06-02T10:00:00Z",
            entry_price=400.00,
            shares=10,
            entry_reasoning="test",
            verdict_at_entry="WAIT",
            risk_assessment="test",
            expected_holding_period="position",
        )
        journal.open_trade(t2)
        journal.close_trade("test-002", exit_price=410.00, exit_reason="take_profit")

        assert len(journal.list_open()) == 1
        assert len(journal.list_closed()) == 1
        assert journal.count() == 2

    def test_add_reflection(self, journal, sample_trade):
        """Adiciona reflexao post-mortem a um trade fechado."""
        journal.open_trade(sample_trade)
        journal.close_trade("test-001", exit_price=195.00, exit_reason="take_profit")
        reflected = journal.add_reflection(
            "test-001",
            thesis_correct=True,
            what_went_right="Catalyst confirmed within 3 days",
            what_went_wrong="Entered too early, could have waited for volume confirmation",
            lesson_learned="Wait for volume spike after support test before entering",
        )
        assert reflected is not None
        assert reflected.thesis_correct is True
        assert reflected.lesson_learned is not None
        assert "volume" in reflected.lesson_learned

    def test_get_trade_not_found(self, journal):
        """Retorna None para trade inexistente."""
        assert journal.get_trade("nonexistent") is None

    def test_get_stats_empty(self, journal):
        """Stats com journal vazio."""
        stats = journal.get_stats()
        assert stats["total_trades"] == 0
        assert stats["win_rate_pct"] == 0

    def test_get_stats_with_trades(self, journal):
        """Stats agregadas com trades."""
        # Win
        t1 = PaperTrade(
            trade_id="w1",
            ticker="AAPL",
            thesis="test",
            direction="long",
            entry_date="2026-06-01T10:00:00Z",
            entry_price=100,
            shares=10,
            entry_reasoning="test",
            verdict_at_entry="test",
            risk_assessment="test",
            expected_holding_period="swing",
        )
        journal.open_trade(t1)
        journal.close_trade("w1", exit_price=110, exit_reason="take_profit")

        # Loss
        t2 = PaperTrade(
            trade_id="l1",
            ticker="TSLA",
            thesis="test",
            direction="long",
            entry_date="2026-06-02T10:00:00Z",
            entry_price=200,
            shares=5,
            entry_reasoning="test",
            verdict_at_entry="test",
            risk_assessment="test",
            expected_holding_period="swing",
        )
        journal.open_trade(t2)
        journal.close_trade("l1", exit_price=190, exit_reason="stop_loss")

        stats = journal.get_stats()
        assert stats["total_trades"] == 2
        assert stats["closed_trades"] == 2
        assert stats["wins"] == 1
        assert stats["losses"] == 1
        assert stats["win_rate_pct"] == 50.0

    def test_journal_persistence(self, journal, sample_trade):
        """Dados persistem no arquivo JSONL."""
        journal.open_trade(sample_trade)
        # Reabrir o journal do mesmo arquivo
        journal2 = PaperJournal(journal.path)
        assert journal2.count() == 1
        assert journal2.list_open()[0]["trade_id"] == "test-001"

    def test_production_guard_refuses_truncation(self, tmp_path):
        """Journal no caminho de producao NAO pode ser truncado via _rewrite vazio."""
        from core.trading.paper_journal import _PRODUCTION_JOURNAL

        # Cria um journal fake no tmp_path, mas vamos testar a logica da guarda:
        # Se o path resolve para o de producao, _rewrite([]) deve levantar.
        prod_journal = PaperJournal(_PRODUCTION_JOURNAL)
        with pytest.raises(RuntimeError, match="Refusing to truncate production journal"):
            prod_journal._rewrite([])

    def test_temp_journal_can_be_truncated(self, journal):
        """Journal temporario (nao-producao) PODE ser truncado."""
        # journal fixture usa tempfile - nao e o path de producao
        journal._rewrite([])  # nao deve levantar
        assert journal.count() == 0

    def test_review_aged_closed_thesis_records_post_mortem_once(self, journal):
        """Fecha C6 em trades fechados com 14+ dias e registra memoria uma vez."""

        class FakeMemory:
            def __init__(self):
                self.turns = []

            def add_turn(self, **kwargs):
                self.turns.append(kwargs)

        trade = PaperTrade(
            trade_id="aged-001",
            ticker="NVDA",
            thesis="breakout momentum should continue",
            direction="long",
            entry_date="2026-05-20T10:00:00Z",
            entry_price=100,
            shares=10,
            entry_reasoning="volume breakout",
            verdict_at_entry="BUY_CANDIDATE confidence 72",
            risk_assessment="moderate",
            expected_holding_period="swing",
        )
        journal.open_trade(trade)
        journal.close_trade(
            "aged-001",
            exit_price=94,
            exit_reason="stop_loss",
            exit_date="2026-06-03T10:00:00Z",
        )

        memory = FakeMemory()
        reviewed = journal.review_aged_closed_theses(
            now=datetime(2026, 6, 15, tzinfo=timezone.utc),
            memory=memory,
        )

        assert len(reviewed) == 1
        assert reviewed[0]["trade_id"] == "aged-001"
        assert reviewed[0]["thesis_correct"] is False
        assert reviewed[0]["memory_recorded"] is True

        stored = journal.get_trade("aged-001")
        assert stored is not None
        assert "thesis_closed" in stored["tags"]
        assert stored["lesson_learned"].startswith("C6 post-mortem")
        assert memory.turns[0]["category"] == "thesis_closed"
        assert "thesis_closed" in memory.turns[0]["tags"]

        second_review = journal.review_aged_closed_theses(
            now=datetime(2026, 6, 15, tzinfo=timezone.utc),
            memory=memory,
        )
        assert second_review == []
        assert len(memory.turns) == 1


# C7: PerformanceEngine


class TestPerformanceEngine:
    def test_empty_journal(self, journal):
        """Relatorio de performance com journal vazio."""
        engine = PerformanceEngine(journal)
        report = engine.evaluate()
        assert report.total_trades == 0
        assert report.closed_trades == 0
        assert "insufficient_data" in report.detected_biases[0] if report.detected_biases else False

    def test_single_trade_insufficient(self, journal, sample_trade):
        """Um trade so nao gera metricas robustas."""
        journal.open_trade(sample_trade)
        journal.close_trade("test-001", exit_price=195.00, exit_reason="take_profit")
        engine = PerformanceEngine(journal)
        report = engine.evaluate()
        assert report.closed_trades == 1
        assert report.win_rate_pct == 100.0
        # Sem reflexao ainda
        assert report.reflection_rate_pct == 0.0
        assert (
            "insufficient_sample" in str(report.detected_biases)
            if report.detected_biases
            else False
        )

    def test_multiple_trades_detects_biases(self, journal):
        """Multiplos trades ativam deteccao de vieses."""
        for i in range(6):
            tid = f"t{i}"
            trade = PaperTrade(
                trade_id=tid,
                ticker=f"TICK{i}",
                thesis=f"thesis {i}",
                direction="long",
                entry_date=f"2026-06-0{i + 1}T10:00:00Z",
                entry_price=100,
                shares=10,
                entry_reasoning="test",
                verdict_at_entry="test",
                risk_assessment="test",
                expected_holding_period="swing",
            )
            journal.open_trade(trade)
            # 4 wins, 2 losses
            if i < 4:
                journal.close_trade(tid, exit_price=102, exit_reason="take_profit")
                journal.add_reflection(tid, thesis_correct=True, lesson_learned="ok")
            else:
                journal.close_trade(tid, exit_price=90, exit_reason="stop_loss")
                journal.add_reflection(tid, thesis_correct=False, lesson_learned="bad")

        engine = PerformanceEngine(journal)
        report = engine.evaluate()

        assert report.total_trades == 6
        assert report.closed_trades == 6
        assert report.win_rate_pct == pytest.approx(66.67, rel=0.1)
        assert report.profit_factor > 0
        assert report.reflection_rate_pct == 100.0
        assert report.thesis_accuracy_pct == pytest.approx(66.67, rel=0.1)
        # Deve ter vieses detectados (losers outpace winners)
        assert len(report.detected_biases) > 0

    def test_sharpe_ratio_calculation(self, journal):
        """Sharpe ratio com trades consistentes."""
        for i in range(10):
            tid = f"s{i}"
            trade = PaperTrade(
                trade_id=tid,
                ticker="SPY",
                thesis="momentum",
                direction="long",
                entry_date=f"2026-06-{i + 1:02d}T10:00:00Z",
                entry_price=500,
                shares=10,
                entry_reasoning="test",
                verdict_at_entry="test",
                risk_assessment="test",
                expected_holding_period="swing",
            )
            journal.open_trade(trade)
            # Pequenos ganhos consistentes
            journal.close_trade(tid, exit_price=501 + i * 0.5, exit_reason="take_profit")

        engine = PerformanceEngine(journal)
        report = engine.evaluate()
        assert report.sharpe_ratio > 0  # Retornos positivos consistentes
        assert report.max_drawdown_percent == 0.0  # Sem drawdown

    def test_drawdown_calculation(self, journal):
        """Max drawdown com sequencia de perdas."""
        prices = [100, 98, 96, 94, 102, 101, 100]  # Drawdown depois recuperacao
        for i, px in enumerate(prices):
            tid = f"dd{i}"
            trade = PaperTrade(
                trade_id=tid,
                ticker="XYZ",
                thesis="test",
                direction="long",
                entry_date=f"2026-06-{i + 1:02d}T10:00:00Z",
                entry_price=100,
                shares=10,
                entry_reasoning="test",
                verdict_at_entry="test",
                risk_assessment="test",
                expected_holding_period="day_trade",
            )
            journal.open_trade(trade)
            journal.close_trade(tid, exit_price=px, exit_reason="manual")

        engine = PerformanceEngine(journal)
        report = engine.evaluate()
        assert report.max_drawdown_percent > 0

    def test_performance_report_serializable(self, journal, sample_trade):
        """Relatorio e serializavel para JSON."""
        journal.open_trade(sample_trade)
        journal.close_trade("test-001", exit_price=195.00, exit_reason="take_profit")
        journal.add_reflection("test-001", thesis_correct=True, lesson_learned="test")

        engine = PerformanceEngine(journal)
        report = engine.evaluate()
        d = report.to_dict()
        assert isinstance(d, dict)
        # Deve ser serializavel
        json_str = json.dumps(d, indent=2)
        assert len(json_str) > 0
        assert "win_rate_pct" in json_str
