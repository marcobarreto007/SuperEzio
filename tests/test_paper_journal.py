"""Testes para PaperJournal (C6) e PerformanceEngine (C7)."""

import tempfile
from datetime import UTC, datetime
from pathlib import Path

import pytest

from core.trading.paper_journal import PaperJournal, PaperTrade

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

    def test_pytest_cannot_append_to_operator_journal(self):
        """Even an accidental default constructor must fail before touching operator data."""
        from core.trading.paper_journal import _PRODUCTION_JOURNAL

        prod_journal = PaperJournal(_PRODUCTION_JOURNAL)
        with pytest.raises(RuntimeError, match="Tests may not write"):
            prod_journal._append({"trade_id": "must-not-exist"})

    def test_close_trade_holds_the_lock_across_read_and_write(self, tmp_path, sample_trade):
        """close_trade precisa reter o lock durante leitura E escrita.

        Sem isso, dois fechamentos concorrentes leem a mesma lista, cada um
        aplica a sua mudanca e o segundo _rewrite sobrescreve o primeiro — um
        fechamento perdido em silencio. Verificado de forma deterministica: de
        outra thread, um acquire nao-bloqueante falha enquanto o lock e retido.
        """
        import threading

        journal = PaperJournal(tmp_path / "paper.jsonl")
        journal.open_trade(sample_trade)

        acquired_from_other_thread: list[bool] = []
        original_rewrite = journal._rewrite

        def _spy(entries):
            result: list[bool] = []

            def _probe():
                if journal._lock.acquire(blocking=False):
                    result.append(True)
                    journal._lock.release()
                else:
                    result.append(False)

            prober = threading.Thread(target=_probe)
            prober.start()
            prober.join()
            acquired_from_other_thread.extend(result)
            return original_rewrite(entries)

        journal._rewrite = _spy
        journal.close_trade("test-001", exit_price=200.0)

        assert acquired_from_other_thread == [False], (
            "o lock deve estar retido durante o _rewrite de close_trade"
        )

    def test_journal_file_lock_blocks_other_processes(self, tmp_path):
        """O lock de arquivo bloqueia OUTRO PROCESSO (nao thread).

        msvcrt.locking e per-processo — threads do mesmo processo compartilham
        o lock, entao a prova so vale com um subprocesso tentando LK_NBLCK na
        mesma regiao. close_trade e add_reflection usam _journal_file_lock no
        span completo de leitura+escrita.
        """
        import subprocess
        import sys

        from core.trading.paper_journal import _journal_file_lock

        journal = PaperJournal(tmp_path / "paper.jsonl")
        lock_path = journal.path.with_name(journal.path.name + ".lock")
        probe_code = (
            "import sys, msvcrt\n"
            "h = open(sys.argv[1], 'r+b')\n"
            "h.seek(0)\n"
            "try:\n"
            "    msvcrt.locking(h.fileno(), msvcrt.LK_NBLCK, 1)\n"
            "    print('unlocked')\n"
            "except OSError:\n"
            "    print('locked')\n"
        )

        def _probe() -> str:
            result = subprocess.run(
                [sys.executable, "-c", probe_code, str(lock_path)],
                capture_output=True,
                text=True,
                timeout=60,
            )
            assert not result.stderr, f"probe subprocesso falhou: {result.stderr}"
            return result.stdout.strip()

        with _journal_file_lock(journal.path):
            assert _probe() == "locked", "outro processo deve encontrar o arquivo trancado"
        assert _probe() == "unlocked", "o lock deve ser liberado ao sair do contexto"

    def test_corrupt_line_is_quarantined_not_destroyed(self, tmp_path, sample_trade):
        """Linha corrompida sobrevive ao _rewrite, preservada em arquivo-irmao.

        Antes: _read_all descartava a linha com um warning e o _rewrite
        seguinte persistia apenas os sobreviventes — apagando a evidencia
        permanentemente, sem backup e sem trilha.
        """
        journal = PaperJournal(tmp_path / "paper.jsonl")
        journal.open_trade(sample_trade)

        corrupt = '{"trade_id": "corrupt-001", "ticker": "MSFT"'  # JSON truncado
        with open(journal.path, "a", encoding="utf-8") as f:
            f.write(corrupt + "\n")

        # close_trade percorre _read_all -> _rewrite, o caminho destrutivo
        journal.close_trade("test-001", exit_price=200.0)

        quarantine = journal.path.with_name(journal.path.name + ".quarantine")
        assert quarantine.exists(), "linha corrompida deve ser preservada, nao descartada"
        assert corrupt in quarantine.read_text(encoding="utf-8")
        assert journal.count() == 1  # journal segue sem a linha invalida

    def test_rewrite_leaves_journal_intact_when_write_fails(self, tmp_path, sample_trade):
        """Falha no meio do _rewrite nao pode truncar o journal.

        Antes: open(path, "w") truncava o arquivo ANTES de escrever, entao uma
        excecao durante a gravacao deixava o journal vazio ou pela metade.
        """
        journal = PaperJournal(tmp_path / "paper.jsonl")
        journal.open_trade(sample_trade)
        original = journal.path.read_text(encoding="utf-8")
        assert original.strip(), "pre-condicao: journal precisa ter conteudo"

        # Entrada nao-serializavel na primeira posicao: json.dumps levanta antes
        # de qualquer escrita valida sair.
        entries = [{"trade_id": "bad", "payload": object()}] + journal.list_all()
        with pytest.raises(TypeError):
            journal._rewrite(entries)

        assert journal.path.read_text(encoding="utf-8") == original, (
            "journal original deve permanecer intacto apos falha de escrita"
        )

    def test_default_constructor_honors_isolated_env_path(self, monkeypatch, tmp_path):
        isolated = tmp_path / "default-paper-journal.jsonl"
        monkeypatch.setenv("SUPEREZIO_PAPER_JOURNAL_PATH", str(isolated))

        journal = PaperJournal()
        journal._append({"trade_id": "isolated-default"})

        assert journal.path == isolated
        assert isolated.is_file()

    def test_new_rows_carry_storage_environment_and_provenance(self, journal, sample_trade):
        journal.open_trade(sample_trade)

        row = journal.list_all()[0]
        assert row["storage_environment"] == "isolated"
        assert row["provenance"] == "paper_journal"

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
            now=datetime(2026, 6, 15, tzinfo=UTC),
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
            now=datetime(2026, 6, 15, tzinfo=UTC),
            memory=memory,
        )
        assert second_review == []
        assert len(memory.turns) == 1
