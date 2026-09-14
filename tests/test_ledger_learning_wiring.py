"""Testes do wiring caderneta -> motor de aprendizado no ciclo de producao.

O elo provado em test_recommendation_ledger.py (a linha da caderneta cabe no
`OutcomeLearningEngine.process_trade`) precisa estar VIVO no ciclo, nao so em
teste. As provas do circuito completo:

- o ciclo do fechador (`close_positions(ledger=...)`) roda, rotula o
  contrafactual e alimenta o motor com o desfecho REAL -- e SOMENTE o real,
  nunca o contrafactual;
- falha do motor nao derruba o fechamento (trilho de aprendizado, nao portao);
- re-passar a caderneta em ciclo novo nao duplica estatistica de expert;
- caderneta sem desfechos nao constroi motor e nao muda o relatorio;
- o estagio TRACK do heartbeat entrega a caderneta ao fechador.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from core.body import BodyEventBus, HeartbeatLoop
from core.body.heartbeat import HeartbeatCycle
from core.trading.outcome_learning import OutcomeLearningEngine
from core.trading.paper_journal import PaperJournal, PaperTrade
from core.trading.position_closer import close_positions
from core.trading.recommendation_ledger import Recommendation, RecommendationLedger

ENTRY_DATE = "2026-01-01T00:00:00Z"
SYMBOL = "XEQT.TO"

# Duas barras que tocam o alvo (45.0) na segunda: rotula contrafactual "win".
_BARS_ATE_O_ALVO = ((40, 41, 39.5, 40.5), (40.5, 46, 40.4, 45.8))


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


def _recommendation(**overrides) -> Recommendation:
    params = {
        "ticker": SYMBOL,
        "direction": "long",
        "entry_price": 40.0,
        "shares": 25.0,
        "stop_loss_price": 38.0,
        "take_profit_price": 45.0,
        "time_horizon_bars": 5,
        "expert_source": "momentum_technical",
        "created_at": ENTRY_DATE,
    }
    params.update(overrides)
    return Recommendation(**params)


def _journal_vazio(tmp_path: Path) -> PaperJournal:
    journal_path = tmp_path / "paper.jsonl"
    journal_path.write_text("", encoding="utf-8")
    return PaperJournal(journal_path)


def _executed_row(ledger: RecommendationLedger, **overrides) -> str:
    """Grava uma recomendacao com desfecho REAL (o dono executou e fechou)."""
    result = ledger.record(
        _recommendation(
            expert_predictions={"momentum_technical": {"direction": "UP", "confidence": 0.7}},
            **overrides,
        )
    )
    ledger.record_execution(result.recommendation_id, exit_price=43.0, exit_reason="manual")
    return result.recommendation_id


def _processed_trade_ids(engine: OutcomeLearningEngine) -> set[str]:
    with sqlite3.connect(engine.db_path) as connection:
        return {row[0] for row in connection.execute("SELECT trade_id FROM processed_outcomes")}


# ──────────────────────────────────────────────────────────────────────────────
# 1. O ciclo alimenta o motor
# ──────────────────────────────────────────────────────────────────────────────


def test_ciclo_do_fechador_alimenta_o_motor_com_desfecho_real_e_nao_contrafactual(tmp_path):
    """Ciclo roda -> motor recebeu o REAL; o contrafactual foi rotulado e NAO passado."""
    led = RecommendationLedger(tmp_path / "ledger.jsonl")
    real_id = _executed_row(led)

    # Uma segunda recomendacao que o MESMO ciclo vai rotular como contrafactual.
    shadow = led.record(_recommendation(created_at="2026-01-02T00:00:00Z"))
    hub = _FakeHub({SYMBOL: _bars(*_BARS_ATE_O_ALVO)})
    engine = OutcomeLearningEngine(db_path=tmp_path / "outcomes.sqlite3")

    report = close_positions(
        journal=_journal_vazio(tmp_path),
        data_hub=hub,
        dry_run=True,
        ledger=led,
        learning_engine=engine,
    )

    # O ciclo rotulou o contrafactual...
    assert report.counterfactual_report["labeled"] == 1
    # ...e alimentou o motor SO com o desfecho real.
    assert report.learning_report is not None
    assert report.learning_report["processed"], "motor nao recebeu o desfecho real"
    assert _processed_trade_ids(engine) == {real_id}
    assert shadow.recommendation_id not in _processed_trade_ids(engine)
    assert "momentum_technical" in engine.get_normalized_weights()


def test_repasse_em_ciclo_novo_nao_duplica_estatistica(tmp_path):
    """Todo ciclo re-passa a caderneta inteira; o motor registra cada desfecho UMA vez."""
    led = RecommendationLedger(tmp_path / "ledger.jsonl")
    _executed_row(led)
    engine = OutcomeLearningEngine(db_path=tmp_path / "outcomes.sqlite3")

    def _cycle():
        return close_positions(
            journal=_journal_vazio(tmp_path),
            data_hub=_FakeHub({SYMBOL: _bars(*_BARS_ATE_O_ALVO)}),
            dry_run=True,
            ledger=led,
            learning_engine=engine,
        )

    first = _cycle()
    second = _cycle()

    assert len(first.learning_report["processed"]) == 1
    assert second.learning_report["processed"] == []
    assert first.learning_report["processed"] == second.learning_report["replayed"]

    with sqlite3.connect(engine.db_path) as connection:
        calls = connection.execute("SELECT total_calls FROM expert_stats").fetchall()
    assert [row[0] for row in calls] == [1]


def test_caderneta_sem_desfechos_nao_constroi_motor(tmp_path, monkeypatch):
    """Caderneta vazia (ou sem desfecho) = comportamento inalterado, motor nem nasce."""
    import core.trading.outcome_learning as outcome_module

    class _NaoDeveSerConstruido:
        def __init__(self, *args, **kwargs):
            raise AssertionError("motor construido sem desfechos para aprender")

    monkeypatch.setattr(outcome_module, "OutcomeLearningEngine", _NaoDeveSerConstruido)

    led = RecommendationLedger(tmp_path / "ledger.jsonl")
    led.record(_recommendation())  # pendente: sem desfecho, nada para aprender

    report = close_positions(
        journal=_journal_vazio(tmp_path),
        data_hub=_FakeHub({}),
        dry_run=True,
        ledger=led,
    )

    assert report.learning_report is None
    # A passada pela caderneta aconteceu; so nao ha aprendizado.
    assert report.counterfactual_report["labeled"] == 0


# ──────────────────────────────────────────────────────────────────────────────
# 2. Robustez: aprender nunca derruba o fechamento
# ──────────────────────────────────────────────────────────────────────────────


def test_falha_no_motor_nao_derruba_o_fechamento(tmp_path):
    """O motor explode; o fechamento -- que mexe em dinheiro -- acontece igual."""
    journal_path = tmp_path / "paper.jsonl"
    journal_path.write_text("", encoding="utf-8")
    journal = PaperJournal(journal_path)
    journal.open_trade(
        PaperTrade(
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
        ),
        extra={"stop_loss_price": 38.0, "take_profit_price": 45.0, "time_horizon_bars": 5},
    )
    led = RecommendationLedger(tmp_path / "ledger.jsonl")
    _executed_row(led)
    hub = _FakeHub({SYMBOL: _bars(*_BARS_ATE_O_ALVO)})

    class _ExplodingEngine:
        def process_trade(self, trade):
            raise RuntimeError("sqlite indisponivel")

    report = close_positions(
        journal=journal,
        data_hub=hub,
        dry_run=False,
        ledger=led,
        learning_engine=_ExplodingEngine(),
    )

    assert report.closed == 1
    assert journal.get_trade("bob-teste-1")["exit_date"] is not None
    assert report.learning_report is None


# ──────────────────────────────────────────────────────────────────────────────
# 3. A ligacao de producao: heartbeat TRACK -> fechador -> caderneta -> motor
# ──────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_track_do_heartbeat_passa_a_caderneta_ao_fechador(tmp_path, monkeypatch):
    """Sem esta ligacao o elo inteiro fica morto em runtime, so prova em teste."""
    import core.trading.position_closer as closer_module
    import core.trading.recommendation_ledger as ledger_module

    calls: list[dict] = []

    def _fake_close_positions(journal=None, **kwargs):
        calls.append(kwargs)
        return closer_module.CloserReport(dry_run=kwargs.get("dry_run", True), evaluated=0)

    monkeypatch.setattr(closer_module, "close_positions", _fake_close_positions)
    sentinel = RecommendationLedger(tmp_path / "ledger.jsonl")
    monkeypatch.setattr(ledger_module, "get_recommendation_ledger", lambda: sentinel)
    monkeypatch.setenv("SUPEREZIO_POSITION_CLOSER_ENABLED", "1")
    monkeypatch.delenv("SUPEREZIO_POSITION_CLOSER_DRY_RUN", raising=False)

    bus = BodyEventBus(hub_type="memory")
    hb = HeartbeatLoop(event_bus=bus)
    await hb.beat(HeartbeatCycle.LIGHT)

    assert calls, "o estagio TRACK nao chamou o fechador"
    assert calls[0]["ledger"] is sentinel
