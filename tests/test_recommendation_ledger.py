"""Testes da caderneta de recomendacoes (recommendation_ledger.py).

Cobrem o que o modulo promete, um a um:

- registro da recomendacao (com o vocabulario do journal, para o fechador e os
  motores consumirem sem tradutor);
- marcacao de execucao pelo dono (o atuador), incluindo o estado DESCONHECIDO;
- desfecho contrafactual gerado pelo labeler, que e o `triple_barrier` REUSADO;
- a distincao entre desfecho REAL e CONTRAFACTUAL -- inclusive a precedencia: o
  real nunca e sobrescrito pelo contrafactual, e o contrafactual e preservado
  quando o real chega depois;
- idempotencia (re-gravar nao duplica; retry nao gera linha nova);
- leitura pelos motores (`learning_rows` no formato de `process_trade`).
"""

from __future__ import annotations

import json
import tempfile
from datetime import UTC, datetime
from pathlib import Path

import pytest

from core.trading.paper_journal import PaperJournal, PaperTrade
from core.trading.position_closer import STATUS_WOULD_CLOSE, close_positions
from core.trading.recommendation_ledger import (
    OUTCOME_SOURCE_COUNTERFACTUAL,
    OUTCOME_SOURCE_EXECUTED,
    LabelReport,
    LedgerError,
    Recommendation,
    RecommendationLedger,
    compute_pnl,
    record_recommendation_for_trade,
)

ENTRY_DATE = "2026-01-01T00:00:00Z"
SYMBOL = "XEQT.TO"


def _bar(open_: float, high: float, low: float, close: float, stamp: str) -> dict:
    return {"open": open_, "high": high, "low": low, "close": close, "datetime": stamp}


def _bars(*specs) -> list[dict]:
    return [
        _bar(o, h, low, c, f"2026-01-0{index + 2}T00:00:00Z")
        for index, (o, h, low, c) in enumerate(specs)
    ]


class _FakeHub:
    """DataHub minimo: devolve candles pre-fixados por ticker."""

    def __init__(self, candles: dict[str, list[dict]]):
        self._candles = candles
        self.calls: list[str] = []

    def get_candles(self, symbol: str, timeframe: str = "6M") -> dict:
        self.calls.append(symbol)
        if symbol not in self._candles:
            return {"error": "no_candles"}
        return {"symbol": symbol, "timeframe": timeframe, "candles": self._candles[symbol]}


@pytest.fixture
def ledger():
    with tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False, mode="w") as f:
        f.write("")
        path = Path(f.name)
    yield RecommendationLedger(path)
    for suffix in ("", ".lock", ".quarantine", ".tmp"):
        try:
            Path(str(path) + suffix).unlink()
        except OSError:
            pass


def _recommendation(**overrides) -> Recommendation:
    params = {
        "ticker": SYMBOL,
        "direction": "long",
        "entry_price": 40.0,
        "shares": 25.0,
        "stop_loss_price": 38.0,
        "take_profit_price": 45.0,
        "time_horizon_bars": 5,
        "rationale": "Momentum e valor no mesmo ETF; alvo 2,5:1 sobre o stop.",
        "expert_source": "momentum_technical",
        "created_at": ENTRY_DATE,
    }
    params.update(overrides)
    return Recommendation(**params)


def _same_instant(value: str, expected: str) -> bool:
    """Compara instantes, nao a grafia: a caderneta normaliza Z para +00:00."""
    return datetime.fromisoformat(value) == datetime.fromisoformat(expected)


def _read_lines(path: Path) -> list[dict]:
    return [
        json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()
    ]


# ──────────────────────────────────────────────────────────────────────────────
# 1. Registro
# ──────────────────────────────────────────────────────────────────────────────


def test_recomendacao_registrada_no_vocabulario_do_journal(ledger):
    result = ledger.record(_recommendation())

    assert result.created is True
    assert result.recommendation_id.startswith("rec-")
    row = ledger.get(result.recommendation_id)
    assert row is not None
    # Os nomes que o fechador e o triple_barrier leem, sem tradutor no meio.
    assert row["ticker"] == SYMBOL
    assert row["direction"] == "long"
    assert row["entry_price"] == 40.0
    assert row["shares"] == 25.0
    assert row["stop_loss_price"] == 38.0
    assert row["take_profit_price"] == 45.0
    assert row["time_horizon_bars"] == 5
    assert _same_instant(row["entry_date"], ENTRY_DATE)
    # A linha nasce SEM desfecho e com execucao DESCONHECIDA: o dono ainda nao falou.
    assert row["outcome"] is None
    assert row["outcome_source"] is None
    assert row["executed"] is None
    assert row["barriers"] == {"stop": True, "target": True, "horizon": True}
    assert row["provenance"] == "recommendation_ledger"


def test_recomendacao_sem_stop_declara_a_barreira_ausente(ledger):
    """Sem stop/alvo a linha e registrada, mas diz na propria linha que nao da para rotular."""
    result = ledger.record(_recommendation(stop_loss_price=None, take_profit_price=None))

    row = ledger.get(result.recommendation_id)
    assert row["barriers"] == {"stop": False, "target": False, "horizon": True}
    assert ledger.stats()["not_actionable"] == 1


def test_recomendacao_sem_preco_ou_sem_tamanho_e_recusada():
    """Nao se inventa default para o que a recomendacao precisa ter para ser acionavel."""
    with pytest.raises(ValueError, match="preco de entrada"):
        _recommendation(entry_price=0)
    with pytest.raises(ValueError, match="tamanho"):
        _recommendation(shares=0)
    with pytest.raises(ValueError, match="ticker"):
        _recommendation(ticker="  ")


def test_barreiras_invertidas_sao_recusadas_na_criacao():
    """Mesma regra do triple_barrier: stop acima do alvo num longo e erro de DADO."""
    with pytest.raises(ValueError, match="invertidas"):
        _recommendation(stop_loss_price=46.0, take_profit_price=45.0)
    with pytest.raises(ValueError, match="invertidas"):
        _recommendation(direction="short", stop_loss_price=45.0, take_profit_price=46.0)


def test_recusa_escrever_na_caderneta_do_operador_sob_pytest(monkeypatch):
    """A caderneta real nunca e tocada por teste -- mesma guarda do paper_journal."""
    from core.trading import recommendation_ledger as module

    monkeypatch.setattr(module, "_PRODUCTION_LEDGER", module.DEFAULT_LEDGER_PATH.resolve())
    monkeypatch.setenv("PYTEST_CURRENT_TEST", "test_x (call)")
    production = RecommendationLedger(module.DEFAULT_LEDGER_PATH)
    with pytest.raises(LedgerError, match="caderneta do operador"):
        production.record(_recommendation())


# ──────────────────────────────────────────────────────────────────────────────
# 2. Idempotencia
# ──────────────────────────────────────────────────────────────────────────────


def test_regravar_a_mesma_recomendacao_nao_duplica(ledger):
    first = ledger.record(_recommendation())
    second = ledger.record(_recommendation())

    assert first.created is True
    assert second.created is False
    assert first.recommendation_id == second.recommendation_id
    assert len(ledger.list_all()) == 1
    assert len(_read_lines(ledger.path)) == 1


def test_duas_emissoes_da_mesma_recomendacao_sao_duas_linhas(ledger):
    """Instantes diferentes = o sistema recomendou DUAS vezes. Insistencia e sinal."""
    first = ledger.record(_recommendation(created_at=ENTRY_DATE))
    second = ledger.record(_recommendation(created_at="2026-01-02T00:00:00Z"))

    assert first.recommendation_id != second.recommendation_id
    assert len(ledger.list_all()) == 2


def test_dedupe_key_amarra_a_gravacao_ao_run_id(ledger):
    first = ledger.record(_recommendation(), dedupe_key="rec-run-abc")
    second = ledger.record(_recommendation(), dedupe_key="rec-run-abc")

    assert first.recommendation_id == "rec-run-abc"
    assert second.created is False
    assert len(ledger.list_all()) == 1


def test_marcar_a_mesma_execucao_duas_vezes_nao_reescreve(ledger):
    result = ledger.record(_recommendation())
    first = ledger.mark_execution(result.recommendation_id, executed=True, executed_price=39.8)
    second = ledger.mark_execution(result.recommendation_id, executed=True, executed_price=39.8)

    assert first == second
    assert len(_read_lines(ledger.path)) == 1
    assert ledger.get(result.recommendation_id)["executed"] is True


def test_rotular_duas_vezes_nao_rotula_de_novo(ledger):
    result = ledger.record(_recommendation())
    hub = _FakeHub({SYMBOL: _bars((40, 41, 39.5, 40.5), (40.5, 46, 40.4, 45.8))})

    first = ledger.label_counterfactuals(data_hub=hub)
    second = ledger.label_counterfactuals(data_hub=hub)

    assert first.labeled == 1
    assert second.evaluated == 0
    assert second.labeled == 0
    assert len(ledger.list_all()) == 1
    assert ledger.get(result.recommendation_id)["outcome"] == "win"


# ──────────────────────────────────────────────────────────────────────────────
# 3. Execucao -- o dono e o atuador
# ──────────────────────────────────────────────────────────────────────────────


def test_dono_marca_que_executou(ledger):
    result = ledger.record(_recommendation())
    row = ledger.mark_execution(
        result.recommendation_id,
        executed=True,
        executed_at="2026-01-02T14:31:00Z",
        executed_price=39.9,
        note="Limite executado no TD",
    )

    assert row["executed"] is True
    assert row["executed_price"] == 39.9
    assert _same_instant(row["executed_at"], "2026-01-02T14:31:00Z")
    assert row["execution_note"] == "Limite executado no TD"
    assert row["execution_reported_at"] is not None
    assert ledger.stats()["executed_yes"] == 1


def test_dono_marca_que_nao_executou_e_o_preco_e_limpo(ledger):
    result = ledger.record(_recommendation())
    ledger.mark_execution(result.recommendation_id, executed=True, executed_price=39.9)

    row = ledger.mark_execution(result.recommendation_id, executed=False)

    assert row["executed"] is False
    # Nao existe preco de uma execucao que nao houve.
    assert row["executed_price"] is None
    assert ledger.stats()["executed_no"] == 1


def test_execucao_desconhecida_e_o_estado_inicial_e_pode_ser_restaurado(ledger):
    result = ledger.record(_recommendation())
    assert ledger.get(result.recommendation_id)["executed"] is None

    ledger.mark_execution(result.recommendation_id, executed=True, executed_price=39.9)
    row = ledger.mark_execution(result.recommendation_id, executed=None)

    assert row["executed"] is None
    assert row["executed_price"] is None
    # A fila de trabalho do dono: o sistema recomendou e ninguem disse o que fez.
    assert len(ledger.list_awaiting_owner()) == 1


def test_fila_do_dono_lista_so_o_que_ele_ainda_nao_marcou(ledger):
    first = ledger.record(_recommendation())
    second = ledger.record(_recommendation(created_at="2026-01-03T00:00:00Z"))
    ledger.mark_execution(first.recommendation_id, executed=False)

    awaiting = ledger.list_awaiting_owner()

    assert [row["recommendation_id"] for row in awaiting] == [second.recommendation_id]


# ──────────────────────────────────────────────────────────────────────────────
# 4. Desfecho contrafactual (o labeler)
# ──────────────────────────────────────────────────────────────────────────────


def test_labeler_gera_desfecho_contrafactual_pelo_alvo(ledger):
    result = ledger.record(_recommendation())
    hub = _FakeHub({SYMBOL: _bars((40, 41, 39.5, 40.5), (40.5, 46, 40.4, 45.8))})

    report = ledger.label_counterfactuals(data_hub=hub)

    assert isinstance(report, LabelReport)
    assert report.evaluated == 1
    assert report.labeled == 1
    row = ledger.get(result.recommendation_id)
    assert row["outcome"] == "win"
    assert row["outcome_source"] == OUTCOME_SOURCE_COUNTERFACTUAL
    assert row["exit_reason"] == "take_profit"
    assert row["exit_price"] == 45.0
    assert row["bars_held"] == 2
    # PnL contrafactual: (45 - 40) * 25 acoes.
    assert row["pnl_amount"] == 125.0
    assert row["pnl_percent"] == pytest.approx(12.5)


def test_labeler_gera_desfecho_contrafactual_pelo_stop(ledger):
    result = ledger.record(_recommendation())
    hub = _FakeHub({SYMBOL: _bars((40, 40.5, 39.5, 40.2), (40.2, 40.3, 37.5, 38.1))})

    ledger.label_counterfactuals(data_hub=hub)

    row = ledger.get(result.recommendation_id)
    assert row["outcome"] == "loss"
    assert row["exit_reason"] == "stop_loss"
    assert row["exit_price"] == 38.0
    assert row["outcome_source"] == OUTCOME_SOURCE_COUNTERFACTUAL


def test_labeler_nao_rotula_o_que_ainda_nao_venceu_e_diz_por_que(ledger):
    result = ledger.record(_recommendation())
    # Uma barra so, de um horizonte de 5: o prazo nao venceu, nada tocou.
    hub = _FakeHub({SYMBOL: _bars((40, 40.4, 39.8, 40.1))})

    report = ledger.label_counterfactuals(data_hub=hub)

    assert report.labeled == 0
    assert report.pending == 1
    assert report.skipped_reasons == {"horizon_not_elapsed": 1}
    row = ledger.get(result.recommendation_id)
    assert row["outcome"] is None
    # O motivo do silencio fica na propria linha.
    assert row["last_label_reason"] == "horizon_not_elapsed"


def test_labeler_nao_inventa_desfecho_sem_candles(ledger):
    result = ledger.record(_recommendation())
    report = ledger.label_counterfactuals(data_hub=_FakeHub({}))

    assert report.labeled == 0
    assert report.skipped_reasons == {"no_market_data": 1}
    assert ledger.get(result.recommendation_id)["outcome"] is None


def test_labeler_reaproveita_a_regra_do_fechador(ledger):
    """O contrafactual e o MESMO veredito que o fechador daria -- nao uma copia.

    A prova: a linha da caderneta, com as barreiras que ela ja carrega, avaliada
    pelo fechador em dry-run, da o mesmo preco e o mesmo motivo.
    """
    from core.trading.position_closer import evaluate_row

    result = ledger.record(_recommendation())
    hub = _FakeHub({SYMBOL: _bars((40, 41, 39.5, 40.5), (40.5, 46, 40.4, 45.8))})
    row = ledger.get(result.recommendation_id)

    decision = evaluate_row(row, data_hub=hub)
    ledger.label_counterfactuals(data_hub=hub)
    labeled = ledger.get(result.recommendation_id)

    assert decision.status == STATUS_WOULD_CLOSE
    assert decision.exit_price == labeled["exit_price"]
    assert decision.exit_reason == labeled["exit_reason"]
    assert decision.bars_held == labeled["bars_held"]


def test_labeler_dry_run_nao_escreve(ledger):
    result = ledger.record(_recommendation())
    hub = _FakeHub({SYMBOL: _bars((40, 41, 39.5, 40.5), (40.5, 46, 40.4, 45.8))})

    report = ledger.label_counterfactuals(data_hub=hub, dry_run=True)

    assert report.dry_run is True
    assert report.labeled == 0
    assert report.decisions[0]["reason"] == "labeled"
    assert ledger.get(result.recommendation_id)["outcome"] is None


# ──────────────────────────────────────────────────────────────────────────────
# 5. REAL vs CONTRAFACTUAL -- a distincao que o aprendizado usa
# ──────────────────────────────────────────────────────────────────────────────


def test_desfecho_real_usa_o_preco_que_o_dono_digitou(ledger):
    result = ledger.record(_recommendation())
    ledger.mark_execution(result.recommendation_id, executed=True, executed_price=40.0)

    row = ledger.record_executed_outcome(
        result.recommendation_id, exit_price=43.0, exit_reason="manual"
    )

    assert row["outcome_source"] == OUTCOME_SOURCE_EXECUTED
    assert row["exit_price"] == 43.0
    assert row["exit_reason"] == "manual"
    assert row["pnl_amount"] == 75.0


def test_desfecho_real_recusa_recomendacao_nao_marcada_como_executada(ledger):
    """Sem marcacao de execucao, um desfecho 'real' seria contrafactual disfarcado."""
    result = ledger.record(_recommendation())

    with pytest.raises(LedgerError, match="nao esta marcada como executada"):
        ledger.record_executed_outcome(result.recommendation_id, exit_price=43.0)


def test_contrafactual_nunca_sobrescreve_desfecho_real(ledger):
    """A regra de precedencia: realidade nao e reescrita por simulacao."""
    result = ledger.record(_recommendation())
    ledger.record_execution(result.recommendation_id, exit_price=41.7, exit_reason="manual")
    real = ledger.get(result.recommendation_id)

    # O mercado, depois, bateria o alvo -- mas a recomendacao ja tinha desfecho REAL.
    hub = _FakeHub({SYMBOL: _bars((40, 41, 39.5, 40.5), (40.5, 46, 40.4, 45.8))})
    ledger.label_counterfactuals(data_hub=hub)

    after = ledger.get(result.recommendation_id)
    assert after["outcome_source"] == OUTCOME_SOURCE_EXECUTED
    assert after["exit_price"] == real["exit_price"]
    assert after["pnl_amount"] == real["pnl_amount"]
    assert after["counterfactual"] is None


def test_desfecho_real_preserva_o_contrafactual_para_comparacao(ledger):
    """O dono que nao executou precisa ver as duas coisas: o que fez e o que teria sido."""
    result = ledger.record(_recommendation())
    hub = _FakeHub({SYMBOL: _bars((40, 41, 39.5, 40.5), (40.5, 46, 40.4, 45.8))})
    ledger.label_counterfactuals(data_hub=hub)
    assert ledger.get(result.recommendation_id)["outcome_source"] == OUTCOME_SOURCE_COUNTERFACTUAL

    # Ele executou depois: o desfecho real assume, e o contrafactual fica guardado.
    row = ledger.record_execution(result.recommendation_id, exit_price=42.0, exit_reason="manual")

    assert row["outcome_source"] == OUTCOME_SOURCE_EXECUTED
    assert row["exit_price"] == 42.0
    assert row["counterfactual"]["exit_price"] == 45.0
    assert row["counterfactual"]["outcome"] == "win"
    assert row["counterfactual"]["outcome_source"] == OUTCOME_SOURCE_COUNTERFACTUAL


def test_learning_rows_por_padrao_so_traz_desfecho_real(ledger):
    """Aprendizado e sobre dinheiro que existiu. O contrafactual entra so se pedido."""
    executed = ledger.record(_recommendation())
    ledger.record_execution(executed.recommendation_id, exit_price=43.0)

    skipped = ledger.record(_recommendation(created_at="2026-01-01T12:00:00Z"))
    hub = _FakeHub({SYMBOL: _bars((40, 41, 39.5, 40.5), (40.5, 46, 40.4, 45.8))})
    ledger.label_counterfactuals(data_hub=hub)

    real_only = ledger.learning_rows()
    with_shadow = ledger.learning_rows(include_counterfactual=True)

    assert [row["trade_id"] for row in real_only] == [executed.recommendation_id]
    assert all(row["outcome_source"] == OUTCOME_SOURCE_EXECUTED for row in real_only)
    assert len(with_shadow) == 2
    assert {row["outcome_source"] for row in with_shadow} == {
        OUTCOME_SOURCE_EXECUTED,
        OUTCOME_SOURCE_COUNTERFACTUAL,
    }
    assert skipped.recommendation_id in {row["trade_id"] for row in with_shadow}


def test_placar_conta_o_custo_de_oportunidade(ledger):
    missed = ledger.record(_recommendation())
    hub = _FakeHub({SYMBOL: _bars((40, 41, 39.5, 40.5), (40.5, 46, 40.4, 45.8))})
    ledger.label_counterfactuals(data_hub=hub)
    ledger.mark_execution(missed.recommendation_id, executed=False)

    stats = ledger.stats()

    assert stats["missed_winners"] == 1
    assert stats["avoided_losers"] == 0
    assert stats["executed_no"] == 1
    assert stats["outcomes_counterfactual"] == 1
    assert stats["outcomes_executed"] == 0


# ──────────────────────────────────────────────────────────────────────────────
# 6. Leitura pelos motores
# ──────────────────────────────────────────────────────────────────────────────


def test_motor_de_aprendizado_processa_a_linha_da_caderneta(ledger, tmp_path):
    """`OutcomeLearningEngine.process_trade` le a linha sem nenhum tradutor."""
    from core.trading.outcome_learning import OutcomeLearningEngine

    result = ledger.record(
        _recommendation(
            expert_predictions={
                "momentum_technical": {"direction": "UP", "confidence": 0.7},
            },
            expert_attribution={"momentum_technical": 0.7},
        )
    )
    ledger.record_execution(result.recommendation_id, exit_price=43.0, exit_reason="take_profit")

    engine = OutcomeLearningEngine(db_path=tmp_path / "outcomes.sqlite3")
    rows = ledger.learning_rows()
    assert len(rows) == 1

    outcome = engine.process_trade(rows[0])

    assert outcome.processed is True
    weights = engine.get_normalized_weights()
    assert "momentum_technical" in weights


def test_motor_de_aprendizado_reprocessa_sem_duplicar(ledger, tmp_path):
    """A idempotencia da caderneta chega inteira ao motor: mesmo payload, mesmo evento."""
    from core.trading.outcome_learning import OutcomeLearningEngine

    result = ledger.record(_recommendation())
    ledger.record_execution(result.recommendation_id, exit_price=43.0)
    engine = OutcomeLearningEngine(db_path=tmp_path / "outcomes.sqlite3")
    row = ledger.learning_rows()[0]

    first = engine.process_trade(row)
    second = engine.process_trade(row)

    assert first.processed is True
    assert second.processed is False
    assert first.event_id == second.event_id


def test_motor_de_aprendizado_recusa_linha_ainda_pendente(ledger, tmp_path):
    """Sem desfecho nao ha o que aprender -- e o motor diz isso, nao a caderneta."""
    from core.trading.outcome_learning import OutcomeLearningEngine

    ledger.record(_recommendation())
    assert ledger.learning_rows() == []

    engine = OutcomeLearningEngine(db_path=tmp_path / "outcomes.sqlite3")
    with pytest.raises(ValueError, match="terminal"):
        engine.process_trade(ledger.as_learning_row(ledger.list_pending()[0]))


def test_feedback_loop_le_a_caderneta_pela_mesma_linha(ledger):
    """O feedback_loop le `list_closed()` do journal; a caderneta produz a mesma forma."""
    result = ledger.record(_recommendation())
    ledger.record_execution(result.recommendation_id, exit_price=43.0)

    row = ledger.learning_rows()[0]

    # Os campos que `_update_adaptive_from_closed_trades` e `analyze_confidence_bias`
    # consomem do journal, presentes e no mesmo tipo.
    assert row["trade_id"]
    assert row["outcome"] in {"win", "loss", "breakeven"}
    assert row["exit_date"]
    assert row["entry_date"]
    assert isinstance(row["shares"], float)
    assert row["direction"] in {"long", "short"}
    assert set(ledger.list_resolved()[0]) >= {"outcome", "exit_price", "expert_predictions"}


# ──────────────────────────────────────────────────────────────────────────────
# 7. Integracao com o fechador
# ──────────────────────────────────────────────────────────────────────────────


def test_fechador_observa_a_caderneta_no_mesmo_ciclo(tmp_path):
    """`close_positions(ledger=...)` rotula o contrafactual com o MESMO cache de candles."""
    journal_path = tmp_path / "paper.jsonl"
    journal_path.write_text("", encoding="utf-8")
    journal = PaperJournal(journal_path)
    led = RecommendationLedger(tmp_path / "ledger.jsonl")

    trade = PaperTrade(
        trade_id="bob-teste-1",
        ticker=SYMBOL,
        thesis="trade paper aberto",
        direction="long",
        entry_date=ENTRY_DATE,
        entry_price=40.0,
        shares=25.0,
        entry_reasoning="teste",
        verdict_at_entry="BUY",
        risk_assessment="moderada",
        expected_holding_period="swing",
    )
    journal.open_trade(
        trade,
        extra={"stop_loss_price": 38.0, "take_profit_price": 45.0, "time_horizon_bars": 5},
    )
    result = led.record(_recommendation())
    hub = _FakeHub({SYMBOL: _bars((40, 41, 39.5, 40.5), (40.5, 46, 40.4, 45.8))})

    report = close_positions(journal=journal, data_hub=hub, dry_run=True, ledger=led)

    # O fechador continua nao fechando nada em dry-run...
    assert report.would_close == 1
    assert report.closed == 0
    # ...e a caderneta foi rotulada no mesmo ciclo.
    assert report.counterfactual_report["labeled"] == 1
    assert led.get(result.recommendation_id)["outcome"] == "win"
    # Um fetch por ticker, nao um por linha.
    assert hub.calls.count(SYMBOL) == 1


def test_fechador_sem_caderneta_nao_muda_de_comportamento(tmp_path):
    journal_path = tmp_path / "paper.jsonl"
    journal_path.write_text("", encoding="utf-8")
    report = close_positions(
        journal=PaperJournal(journal_path), data_hub=_FakeHub({}), dry_run=True
    )

    assert report.counterfactual_report is None
    assert report.to_dict()["counterfactual_report"] is None


def test_falha_ao_rotular_nao_derruba_o_fechamento(tmp_path, monkeypatch):
    """Fronteira de melhor esforco: a caderneta e trilho, o fechamento e dinheiro."""
    journal_path = tmp_path / "paper.jsonl"
    journal_path.write_text("", encoding="utf-8")
    led = RecommendationLedger(tmp_path / "ledger.jsonl")

    def _explode(*_args, **_kwargs):
        raise RuntimeError("candles fora do ar")

    monkeypatch.setattr(led, "label_counterfactuals", _explode)
    report = close_positions(
        journal=PaperJournal(journal_path), data_hub=_FakeHub({}), dry_run=True, ledger=led
    )

    assert report.evaluated == 0
    assert report.counterfactual_report is None


# ──────────────────────────────────────────────────────────────────────────────
# 8. Persistencia: mesmo padrao do journal
# ──────────────────────────────────────────────────────────────────────────────


def test_pnl_da_caderneta_bate_com_o_do_journal():
    """Se a aritmetica do journal mudar, este teste quebra e forca a decisao consciente."""
    for direction, entry, exit_price, shares in (
        ("long", 40.0, 45.0, 25.0),
        ("long", 40.0, 38.0, 25.0),
        ("short", 40.0, 38.0, 25.0),
        ("long", 40.0, 40.0, 25.0),
    ):
        ledger_amount, ledger_percent = compute_pnl(
            direction=direction, entry_price=entry, exit_price=exit_price, shares=shares
        )
        paper = PaperTrade(
            trade_id="x",
            ticker="X",
            thesis="",
            direction=direction,
            entry_date=ENTRY_DATE,
            entry_price=entry,
            shares=shares,
            entry_reasoning="",
            verdict_at_entry="",
            risk_assessment="",
            expected_holding_period="swing",
        )
        paper.close_trade(exit_price=exit_price)
        assert ledger_amount == pytest.approx(paper.pnl_amount)
        assert ledger_percent == pytest.approx(paper.pnl_percent)


def test_caderneta_e_append_only_e_sobrevive_a_releitura(ledger):
    first = ledger.record(_recommendation())
    second = ledger.record(_recommendation(created_at="2026-01-05T00:00:00Z"))
    ledger.mark_execution(first.recommendation_id, executed=True, executed_price=39.5)

    reread = RecommendationLedger(ledger.path)
    rows = reread.list_all()

    assert {row["recommendation_id"] for row in rows} == {
        first.recommendation_id,
        second.recommendation_id,
    }
    assert reread.get(first.recommendation_id)["executed_price"] == 39.5
    # O update reescreveu o arquivo, mas nao acrescentou linha.
    assert len(_read_lines(ledger.path)) == 2


def test_linha_corrompida_e_quarentenada_e_nao_derruba_a_leitura(ledger):
    result = ledger.record(_recommendation())
    with open(ledger.path, "a", encoding="utf-8") as f:
        f.write("{isso nao e json\n")

    rows = ledger.list_all()

    assert [row["recommendation_id"] for row in rows] == [result.recommendation_id]
    quarantine = Path(str(ledger.path) + ".quarantine")
    assert "isso nao e json" in quarantine.read_text(encoding="utf-8")


def test_recusa_truncar_a_caderneta_de_producao(monkeypatch):
    from core.trading import recommendation_ledger as module

    monkeypatch.setattr(module, "_PRODUCTION_LEDGER", module.DEFAULT_LEDGER_PATH.resolve())
    ledger = RecommendationLedger(module.DEFAULT_LEDGER_PATH)
    with pytest.raises(LedgerError, match="truncar"):
        ledger._rewrite([])


def test_atalho_do_pipeline_registra_a_recomendacao(ledger):
    result = record_recommendation_for_trade(
        ticker=SYMBOL,
        action="buy",
        qty=25,
        entry_price=40.0,
        barriers={
            "stop_loss_price": 38.0,
            "take_profit_price": 45.0,
            "time_horizon_bars": 10,
            "asymmetry_ratio": 2.5,
        },
        rationale="Alvo 2,5:1 sobre o stop, dentro da cota sem comissao.",
        expert_source="momentum_technical",
        learning_context={
            "expert_predictions": {"momentum_technical": {"direction": "UP", "confidence": 0.7}},
            "prediction_probability_at_entry": 0.62,
            "calibration_status": "calibrated",
            "prediction_class_at_entry": "UP",
        },
        expected_holding_period="swing",
        run_id="run-1",
        ledger=ledger,
    )

    row = ledger.get(result.recommendation_id)
    assert row["ticker"] == SYMBOL
    assert row["time_horizon_bars"] == 10
    assert row["expert_predictions"]["momentum_technical"]["confidence"] == 0.7
    assert row["prediction_probability_at_entry"] == 0.62
    assert row["run_id"] == "run-1"
    assert row["executed"] is None


def test_atalho_do_pipeline_nao_levanta_quando_a_linha_e_invalida(ledger):
    """Trilho de aprendizado nao derruba o ciclo que o produziu."""
    result = record_recommendation_for_trade(
        ticker="",
        action="buy",
        qty=25,
        entry_price=40.0,
        ledger=ledger,
    )

    assert result is None


def test_atalho_do_pipeline_sem_preco_nao_registra(ledger):
    result = record_recommendation_for_trade(
        ticker=SYMBOL, action="buy", qty=25, entry_price=0.0, ledger=ledger
    )

    assert result is None
    assert ledger.list_all() == []


def test_agora_default_e_utc_quando_nao_informado(ledger):
    result = ledger.record(_recommendation(created_at=None))
    row = ledger.get(result.recommendation_id)

    parsed = datetime.fromisoformat(row["created_at"])
    assert parsed.tzinfo is not None
    assert parsed.utcoffset() == UTC.utcoffset(None)


def test_linha_da_caderneta_alimenta_o_analisador_de_vies_do_feedback_loop(ledger):
    """`analyze_confidence_bias` le a confianca de `verdict_at_entry` -- e o mesmo campo."""
    from core.trading.feedback_loop import _extract_confidence

    result = record_recommendation_for_trade(
        ticker=SYMBOL,
        action="buy",
        qty=25,
        entry_price=40.0,
        barriers={"stop_loss_price": 38.0, "take_profit_price": 45.0, "time_horizon_bars": 10},
        verdict_at_entry="CONFIDENCE: 0.72",
        ledger=ledger,
    )

    row = ledger.get(result.recommendation_id)
    assert row["verdict_at_entry"] == "CONFIDENCE: 0.72"
    assert _extract_confidence(row["verdict_at_entry"]) == 0.72
