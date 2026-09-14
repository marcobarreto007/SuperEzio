"""Testes do fechador de posicao (position_closer.py).

Cobrem os requisitos: gap de abertura, empate stop/alvo, vencimento por prazo,
idempotencia, dry-run que nao fecha, mercado fechado e persistencia das barreiras na
abertura.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from core.body import BodyEventBus, HeartbeatLoop
from core.body.heartbeat import HeartbeatCycle, HeartbeatStage
from core.trading.paper_journal import PaperJournal, PaperTrade
from core.trading.position_closer import (
    SKIP_ALREADY_CLOSED,
    SKIP_HORIZON_PENDING,
    SKIP_MISSING_BARRIERS,
    SKIP_NO_BAR_AFTER_ENTRY,
    SKIP_NO_MARKET_DATA,
    SKIP_SUSPECTED_SPLIT,
    STATUS_SKIPPED,
    STATUS_WOULD_CLOSE,
    close_positions,
    detect_split_factor,
    dry_run_from_env,
)

ENTRY_DATE = "2026-01-01T00:00:00Z"


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
def journal():
    with tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False, mode="w") as f:
        f.write("")
        path = Path(f.name)
    yield PaperJournal(path)
    try:
        path.unlink()
    except OSError:
        pass


def _open_trade(
    journal: PaperJournal,
    *,
    trade_id: str = "t-1",
    ticker: str = "XEQT",
    entry_price: float = 100.0,
    direction: str = "long",
    entry_date: str = ENTRY_DATE,
    stop: float | None = 95.0,
    target: float | None = 105.0,
    horizon: int | None = 5,
) -> None:
    """Abre um trade com as barreiras persistidas, igual a producao faz."""
    extra = {}
    if stop is not None:
        extra["stop_loss_price"] = stop
    if target is not None:
        extra["take_profit_price"] = target
    if horizon is not None:
        extra["time_horizon_bars"] = horizon
    trade = PaperTrade(
        trade_id=trade_id,
        ticker=ticker,
        thesis="teste",
        direction=direction,
        entry_date=entry_date,
        entry_price=entry_price,
        shares=10,
        entry_reasoning="teste",
        verdict_at_entry="auto",
        risk_assessment="moderada",
        expected_holding_period="swing",
    )
    journal.open_trade(trade, extra=extra)


# ---------------------------------------------------------------------------
# Persistencia das barreiras na abertura
# ---------------------------------------------------------------------------


def test_open_trade_persists_barriers_without_schema_migration(journal):
    """As barreiras viajam em chave extra e sobrevivem ao close_trade."""
    _open_trade(journal, stop=95.0, target=105.0, horizon=7)
    row = journal.list_open()[0]
    assert row["stop_loss_price"] == 95.0
    assert row["take_profit_price"] == 105.0
    assert row["time_horizon_bars"] == 7

    journal.close_trade("t-1", exit_price=105.0, exit_reason="take_profit")
    closed = journal.list_closed()[0]
    assert closed["stop_loss_price"] == 95.0
    assert closed["exit_reason"] == "take_profit"


# ---------------------------------------------------------------------------
# Gap de abertura
# ---------------------------------------------------------------------------


def test_closer_books_gap_stop_at_the_open_price(journal):
    """Barra inteira abaixo do stop: fecha pelo open, nao pelo nivel."""
    _open_trade(journal, stop=95.0, target=105.0, horizon=5)
    hub = _FakeHub({"XEQT": _bars((92.0, 93.0, 90.0, 91.0))})

    report = close_positions(journal, data_hub=hub, dry_run=False)

    assert report.evaluated == 1
    assert report.closed == 1
    closed = journal.list_closed()[0]
    assert closed["exit_reason"] == "stop_loss"
    assert closed["exit_price"] == 92.0  # o open, nao 95.0
    assert closed["outcome"] == "loss"


# ---------------------------------------------------------------------------
# Empate stop/alvo
# ---------------------------------------------------------------------------


def test_closer_resolves_dual_touch_as_stop_loss(journal):
    """Uma barra que toca os dois lados fecha como stop (pessimista)."""
    _open_trade(journal, stop=95.0, target=105.0, horizon=5)
    hub = _FakeHub({"XEQT": _bars((100.0, 106.0, 94.0, 100.0))})

    report = close_positions(journal, data_hub=hub, dry_run=False)

    assert report.closed == 1
    closed = journal.list_closed()[0]
    assert closed["exit_reason"] == "stop_loss"
    assert closed["exit_price"] == 95.0


# ---------------------------------------------------------------------------
# Vencimento por prazo
# ---------------------------------------------------------------------------


def test_closer_closes_on_vertical_barrier(journal):
    """Sem toque horizontal, o prazo fecha no close da ultima barra do horizonte."""
    _open_trade(journal, stop=90.0, target=120.0, horizon=3)
    hub = _FakeHub(
        {
            "XEQT": _bars(
                (100.0, 104.0, 98.0, 100.0),
                (100.0, 105.0, 99.0, 101.0),
                (101.0, 106.0, 99.0, 102.0),
            )
        }
    )

    report = close_positions(journal, data_hub=hub, dry_run=False)

    assert report.closed == 1
    closed = journal.list_closed()[0]
    assert closed["exit_reason"] == "time_exit"
    assert closed["exit_price"] == 102.0
    assert closed["exit_date"] == "2026-01-04T00:00:00Z"


def test_closer_leaves_trade_open_while_horizon_is_pending(journal):
    _open_trade(journal, stop=90.0, target=120.0, horizon=10)
    hub = _FakeHub({"XEQT": _bars((100.0, 104.0, 98.0, 100.0))})

    report = close_positions(journal, data_hub=hub, dry_run=False)

    assert report.would_close == 0
    assert report.skipped == 1
    assert report.decisions[0].reason == SKIP_HORIZON_PENDING
    assert journal.list_open()  # continua aberto


# ---------------------------------------------------------------------------
# Idempotencia
# ---------------------------------------------------------------------------


def test_running_twice_closes_only_once(journal):
    """Reler o journal a cada ciclo nao pode fechar duas vezes."""
    _open_trade(journal, stop=95.0, target=105.0, horizon=5)
    hub = _FakeHub({"XEQT": _bars((100.0, 101.0, 94.0, 95.0))})

    first = close_positions(journal, data_hub=hub, dry_run=False)
    second = close_positions(journal, data_hub=hub, dry_run=False)

    assert first.closed == 1
    # Segundo ciclo: a linha ja tem exit_date, entao nem entra em list_open().
    assert second.evaluated == 0
    assert second.closed == 0
    assert len(journal.list_closed()) == 1
    assert journal.list_open() == []


def test_already_closed_by_another_process_is_refused(journal, monkeypatch):
    """Corrida entre processos: a revalidacao antes de fechar recusa o segundo."""
    _open_trade(journal, stop=95.0, target=105.0, horizon=5)

    import core.trading.position_closer as closer_module

    real_get_trade = journal.get_trade

    def _fake_get_trade(trade_id):
        # Simula o outro processo fechando a linha entre a leitura e a escrita.
        return {**real_get_trade(trade_id), "exit_date": "2026-01-03T00:00:00Z"}

    monkeypatch.setattr(journal, "get_trade", _fake_get_trade)
    report = closer_module._apply_close(
        journal,
        closer_module.CloseDecision(
            trade_id="t-1",
            ticker="XEQT",
            status=STATUS_WOULD_CLOSE,
            reason="stop_loss",
            exit_reason="stop_loss",
            exit_price=95.0,
        ),
    )

    assert report.status == STATUS_SKIPPED
    assert report.reason == SKIP_ALREADY_CLOSED
    assert [t for t in journal.list_open() if t["trade_id"] == "t-1"]


# ---------------------------------------------------------------------------
# Dry-run
# ---------------------------------------------------------------------------


def test_dry_run_does_not_close_but_reports_what_would_close(journal):
    """dry-run e o default: loga o desfecho e nao escreve no journal."""
    _open_trade(journal, stop=95.0, target=105.0, horizon=5)
    hub = _FakeHub({"XEQT": _bars((100.0, 101.0, 94.0, 95.0))})

    report = close_positions(journal, data_hub=hub)  # dry_run default

    assert report.dry_run is True
    assert report.would_close == 1
    assert report.closed == 0
    decision = report.decisions[0]
    assert decision.status == STATUS_WOULD_CLOSE
    assert decision.exit_reason == "stop_loss"
    assert decision.exit_price == 95.0
    # Nada foi escrito: o trade segue aberto e sem resultado.
    row = journal.list_open()[0]
    assert row["exit_date"] is None
    assert row["exit_reason"] is None
    assert journal.list_closed() == []


def test_dry_run_is_the_default_from_env(monkeypatch):
    monkeypatch.delenv("SUPEREZIO_POSITION_CLOSER_DRY_RUN", raising=False)
    assert dry_run_from_env() is True
    for value in ("1", "true", "yes", "qualquer"):
        monkeypatch.setenv("SUPEREZIO_POSITION_CLOSER_DRY_RUN", value)
        assert dry_run_from_env() is True
    for value in ("0", "false", "no", "off"):
        monkeypatch.setenv("SUPEREZIO_POSITION_CLOSER_DRY_RUN", value)
        assert dry_run_from_env() is False


# ---------------------------------------------------------------------------
# Mercado fechado e dado faltando
# ---------------------------------------------------------------------------


def test_no_bar_after_entry_is_not_an_error(journal):
    """Mercado fechado: sem barra posterior a entrada, o trade so fica pendente."""
    _open_trade(journal, entry_date="2026-06-01T00:00:00Z")
    hub = _FakeHub({"XEQT": _bars((100.0, 101.0, 94.0, 95.0))})  # barras de janeiro

    report = close_positions(journal, data_hub=hub, dry_run=False)

    assert report.skipped == 1
    assert report.decisions[0].reason == SKIP_NO_BAR_AFTER_ENTRY
    assert journal.list_open()


def test_missing_barriers_are_reported_not_guessed(journal):
    """Linha antiga sem barreira: pula com motivo, nao inventa nivel."""
    _open_trade(journal, stop=None, target=None, horizon=None)
    hub = _FakeHub({"XEQT": _bars((100.0, 101.0, 94.0, 95.0))})

    report = close_positions(journal, data_hub=hub, dry_run=False)

    assert report.skipped == 1
    assert report.decisions[0].reason == SKIP_MISSING_BARRIERS
    assert journal.list_open()


def test_missing_market_data_is_reported(journal):
    _open_trade(journal)
    hub = _FakeHub({})

    report = close_positions(journal, data_hub=hub, dry_run=False)

    assert report.skipped == 1
    assert report.decisions[0].reason == SKIP_NO_MARKET_DATA


def test_horizon_falls_back_to_the_holding_period_map(journal):
    """Sem time_horizon_bars persistido, o horizonte vem do mapa de produto."""
    _open_trade(journal, stop=90.0, target=120.0, horizon=None)  # swing -> 5 barras
    hub = _FakeHub(
        {
            "XEQT": _bars(
                (100.0, 104.0, 98.0, 100.0),
                (100.0, 105.0, 99.0, 101.0),
                (101.0, 106.0, 99.0, 102.0),
                (102.0, 107.0, 100.0, 103.0),
                (103.0, 108.0, 101.0, 104.0),
            )
        }
    )

    report = close_positions(journal, data_hub=hub, dry_run=False)

    assert report.closed == 1
    assert journal.list_closed()[0]["exit_reason"] == "time_exit"
    assert journal.list_closed()[0]["exit_price"] == 104.0


# ---------------------------------------------------------------------------
# Split
# ---------------------------------------------------------------------------


def test_split_is_detected_and_the_trade_is_skipped(journal):
    """Degrau de preco compativel com split: pula em vez de fechar errado."""
    _open_trade(journal, stop=95.0, target=105.0, horizon=5)
    # Fecha a 100 e abre a 50: split 2:1. As barreiras persistidas (95/105) estao na
    # escala ANTIGA; avalia-las agora fecharia por um preco que nao existe mais.
    hub = _FakeHub(
        {
            "XEQT": _bars(
                (100.0, 101.0, 99.0, 100.0),
                (50.0, 51.0, 49.0, 50.5),
            )
        }
    )

    report = close_positions(journal, data_hub=hub, dry_run=False)

    assert report.skipped == 1
    assert report.decisions[0].reason == SKIP_SUSPECTED_SPLIT
    assert "split 2:1" in report.decisions[0].detail
    assert journal.list_open()


def test_detect_split_factor_covers_both_directions():
    bars = [
        {"open": 100.0, "high": 100.0, "low": 100.0, "close": 100.0},
        {"open": 25.0, "high": 25.0, "low": 25.0, "close": 25.0},
    ]
    assert detect_split_factor(bars, start_index=1) == 4.0
    # Grupamento (reverse split) devolve o fator negativo.
    assert detect_split_factor(list(reversed(bars)), start_index=1) == -4.0


def test_detect_split_ignores_ordinary_moves():
    bars = [
        {"open": 100.0, "high": 100.0, "low": 100.0, "close": 100.0},
        {"open": 96.0, "high": 96.0, "low": 96.0, "close": 96.0},  # -4%
        {"open": 55.0, "high": 55.0, "low": 55.0, "close": 55.0},  # -42%: nao e fator conhecido
    ]
    assert detect_split_factor(bars, start_index=1) is None


# ---------------------------------------------------------------------------
# Ligacao no heartbeat (estagio TRACK)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_track_stage_runs_the_closer(monkeypatch):
    """TRACK tem corpo: o fechador roda ligado ao loop de batimento."""
    calls: list[dict] = []

    import core.trading.position_closer as closer_module

    def _fake_close_positions(journal=None, **kwargs):
        calls.append(kwargs)
        return closer_module.CloserReport(dry_run=kwargs.get("dry_run", True), evaluated=0)

    monkeypatch.setattr(closer_module, "close_positions", _fake_close_positions)
    monkeypatch.setenv("SUPEREZIO_POSITION_CLOSER_ENABLED", "1")
    monkeypatch.delenv("SUPEREZIO_POSITION_CLOSER_DRY_RUN", raising=False)

    bus = BodyEventBus(hub_type="memory")
    hb = HeartbeatLoop(event_bus=bus)
    await hb.beat(HeartbeatCycle.LIGHT)

    assert calls, "o estagio TRACK nao chamou o fechador"
    assert calls[0]["dry_run"] is True  # primeiro ciclo em producao e simulacao


@pytest.mark.asyncio
async def test_track_stage_respects_the_throttle(monkeypatch):
    """O throttle protege o provider: o segundo batimento nao refaz o ciclo."""
    calls: list[int] = []

    import core.trading.position_closer as closer_module

    def _fake_close_positions(journal=None, **kwargs):
        calls.append(1)
        return closer_module.CloserReport(dry_run=True, evaluated=0)

    monkeypatch.setattr(closer_module, "close_positions", _fake_close_positions)
    monkeypatch.setenv("SUPEREZIO_POSITION_CLOSER_ENABLED", "1")

    bus = BodyEventBus(hub_type="memory")
    hb = HeartbeatLoop(event_bus=bus)
    await hb.beat(HeartbeatCycle.LIGHT)
    await hb.beat(HeartbeatCycle.LIGHT)

    assert len(calls) == 1


@pytest.mark.asyncio
async def test_track_stage_can_be_disabled(monkeypatch):
    import core.trading.position_closer as closer_module

    def _explode(*args, **kwargs):  # pragma: no cover - nao pode ser chamado
        raise AssertionError("fechador rodou com a flag desligada")

    monkeypatch.setattr(closer_module, "close_positions", _explode)
    monkeypatch.setenv("SUPEREZIO_POSITION_CLOSER_ENABLED", "0")

    bus = BodyEventBus(hub_type="memory")
    hb = HeartbeatLoop(event_bus=bus)
    result = await hb.beat(HeartbeatCycle.LIGHT)

    assert result["errors"] == []


def test_track_stage_is_wired_in_the_stage_dispatch():
    """Guarda de regressao: TRACK precisa continuar em LIGHT e FULL."""
    from core.body.heartbeat import FULL_STAGES, LIGHT_STAGES

    assert HeartbeatStage.TRACK in LIGHT_STAGES
    assert HeartbeatStage.TRACK in FULL_STAGES
