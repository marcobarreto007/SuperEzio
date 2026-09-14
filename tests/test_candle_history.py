"""O histórico longo tem de CHEGAR ao expert pelo caminho de produção.

Medido em 2026-09-14: o pipeline pedia ``timeframe="6M"``, que devolve 127
barras diárias, e o expert recusa tudo abaixo de ``MIN_LABELLED_SAMPLES + 21``
= 161.  Toda execução real terminava em ``insufficient_data`` com
``model_id: null``.  Estes testes fixam o encanamento que corrige isso e, ao
mesmo tempo, fixam os limites do que NÃO foi corrigido.
"""

from __future__ import annotations

import asyncio
import csv
import math
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

import core.pipeline.nodes.neural_decision as neural_node
from core.data_collector import candle_history
from core.data_collector.candle_history import (
    load_candle_history,
    read_reference_candles,
    reference_csv_path,
    splice_history,
)
from core.data_collector.professional import ProfessionalCollector
from experts.technical_neural.expert import TechnicalNeuralExpert

_REFERENCE_TICKER = "AAPL"

# Abaixo disto o expert nem chega a rotular uma amostra: é o primeiro portão.
_EXPERT_FLOOR = TechnicalNeuralExpert.MIN_LABELLED_SAMPLES + 21

# Medido contra o provider real: "6M" mapeia para Yahoo "6mo" e rende ~127
# barras.  O stub reproduz esse número para o teste não depender de rede.
_MEASURED_PROVIDER_BARS = 127


def _synthetic_candles(
    count: int,
    *,
    start: datetime,
    price: float = 100.0,
    drift: float = 0.0004,
    amplitude: float = 0.012,
    period: int = 11,
) -> list[dict[str, object]]:
    """Barras diárias válidas com tendência e sazonalidade, sem aleatoriedade."""
    candles: list[dict[str, object]] = []
    close = price
    for index in range(count):
        open_price = close
        close = price * math.exp(drift * index + amplitude * math.sin(index / period))
        candles.append(
            {
                "datetime": (start + timedelta(days=index)).isoformat(),
                "open": open_price,
                "high": max(open_price, close) * 1.004,
                "low": min(open_price, close) * 0.996,
                "close": close,
                "volume": 1_000_000 + (index % 7) * 90_000,
            }
        )
    return candles


def _write_reference_csv(root: Path, ticker: str, candles: list[dict[str, object]]) -> Path:
    """Escreve o CSV no formato exato do cache de referência (CC0)."""
    path = root / ticker[0] / f"{ticker}.csv"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["open", "volume", "high", "close", "low", "timestamp"])
        for candle in candles:
            stamp = datetime.fromisoformat(str(candle["datetime"])).timestamp()
            writer.writerow(
                [
                    candle["open"],
                    candle["volume"],
                    candle["high"],
                    candle["close"],
                    candle["low"],
                    stamp,
                ]
            )
    return path


# ── Leitura do cache de referência ───────────────────────────────────────────


def test_reference_cache_parses_into_hub_shaped_candles(tmp_path: Path) -> None:
    start = datetime(2024, 1, 1, tzinfo=UTC)
    _write_reference_csv(tmp_path, "TEST", _synthetic_candles(30, start=start))

    candles = read_reference_candles("TEST", tmp_path)

    assert len(candles) == 30
    assert set(candles[0]) >= {"datetime", "open", "high", "low", "close", "volume"}
    # Ordenado e sem duplicata: o expert exige uma série temporal inequívoca.
    stamps = [candle["datetime"] for candle in candles]
    assert stamps == sorted(stamps)
    assert len(set(stamps)) == len(stamps)


def test_reference_cache_drops_blank_and_impossible_rows(tmp_path: Path) -> None:
    """Linha corrompida vira barra ausente, nunca barra inventada."""
    path = tmp_path / "T" / "TEST.csv"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "open,volume,high,close,low,timestamp\n"
        "10,100,11,10.5,9.5,1704067200\n"
        ",,,,,\n"  # linha em branco, como no dataset original
        "10,100,9,10.5,9.5,1704153600\n"  # high < close: impossível
        "10,100,11,-3,9.5,1704240000\n"  # preço negativo
        "10,100,12,12,9.5,1704326400\n"
        "9,100,12,12,9.5,1704326400\n"  # mesmo instante, outro preço
        "10,100,11,10.5,9.5,1704412800\n",
        encoding="utf-8",
    )

    candles = read_reference_candles("TEST", tmp_path)

    # A primeira barra de cada instante vence: o expert rejeita série ambígua.
    assert [candle["close"] for candle in candles] == [10.5, 12.0, 10.5]


# ── Emenda cache|provider ────────────────────────────────────────────────────


def test_splice_rebases_the_older_segment_onto_the_provider_level() -> None:
    """Concatenar direto injetaria um retorno falso; a emenda não pode ter degrau.

    Medido contra o provider real em 2026-09-14: cache e yfinance batem no
    centavo na barra mais recente mas divergem até 4.2% cinco anos atrás,
    porque cada série é reajustada a partir de um histórico de dividendos
    diferente.
    """
    start = datetime(2020, 1, 1, tzinfo=UTC)
    cache = _synthetic_candles(200, start=start, price=100.0)
    # Provider no mesmo período final, mas 4% acima: nível de ajuste diferente.
    provider = [
        {
            **candle,
            "open": candle["open"] * 1.04,
            "high": candle["high"] * 1.04,
            "low": candle["low"] * 1.04,
            "close": candle["close"] * 1.04,
        }
        for candle in _synthetic_candles(40, start=start + timedelta(days=160), price=100.0)
    ]

    merged = splice_history(cache, provider)

    seam = len(merged) - len(provider)
    assert seam > 0
    before = float(merged[seam - 1]["close"])
    after = float(merged[seam]["close"])
    assert before == pytest.approx(after, rel=1e-9)

    naive = cache[: len(cache) - len(provider)] + provider
    naive_jump = abs(float(naive[seam]["close"]) / float(naive[seam - 1]["close"]) - 1.0)
    assert naive_jump > 0.01  # o degrau que a emenda existe para evitar


def test_splice_never_duplicates_a_timestamp() -> None:
    start = datetime(2020, 1, 1, tzinfo=UTC)
    cache = _synthetic_candles(200, start=start)
    provider = _synthetic_candles(60, start=start + timedelta(days=140))

    merged = splice_history(cache, provider)

    stamps = [candle["datetime"] for candle in merged]
    assert len(set(stamps)) == len(stamps)
    assert stamps == sorted(stamps)
    # A fonte fresca é dona de todo instante que cobre.
    assert merged[-1]["datetime"] == provider[-1]["datetime"]


def test_provider_failure_falls_back_to_reference_cache(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    start = datetime(2024, 1, 1, tzinfo=UTC)
    _write_reference_csv(tmp_path, "TEST", _synthetic_candles(300, start=start))
    monkeypatch.setattr(candle_history, "_provider_candles", lambda ticker, timeframe: [])

    history = load_candle_history("TEST", reference_root=tmp_path)

    assert history["sources"] == ["reference_cache"]
    assert history["bars"] == 300
    assert "error" not in history


def test_reference_miss_falls_back_to_provider(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    start = datetime(2024, 1, 1, tzinfo=UTC)
    provider = _synthetic_candles(250, start=start)
    monkeypatch.setattr(candle_history, "_provider_candles", lambda ticker, timeframe: provider)

    history = load_candle_history("SEMCACHE", reference_root=tmp_path)

    assert history["sources"] == ["provider"]
    assert history["bars"] == 250
    assert "error" not in history


def test_total_source_failure_is_an_error_not_an_empty_series(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Sem dado nenhum, o expert tem de poder recusar — não receber lista vazia."""
    monkeypatch.setattr(candle_history, "_provider_candles", lambda ticker, timeframe: [])

    history = load_candle_history("SEMFONTE", reference_root=tmp_path)

    assert history["error"] == "no_candle_history"
    assert "candles" not in history


# ── Caminho de produção ──────────────────────────────────────────────────────


def test_production_path_reaches_the_expert_sample_floor(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """O expert recebe >= 161 barras e o status deixa de ser ``insufficient_data``."""
    now = datetime.now(UTC).replace(microsecond=0)
    reference_root = tmp_path / "reference"
    _write_reference_csv(
        reference_root, _REFERENCE_TICKER, _synthetic_candles(420, start=now - timedelta(days=419))
    )
    measured = _synthetic_candles(
        _MEASURED_PROVIDER_BARS, start=now - timedelta(days=_MEASURED_PROVIDER_BARS - 1)
    )
    monkeypatch.setattr(candle_history, "_provider_candles", lambda ticker, timeframe: measured)
    monkeypatch.setattr(candle_history, "DEFAULT_REFERENCE_ROOT", reference_root)

    from data.data_hub import hub

    monkeypatch.setattr(
        hub,
        "get_candles",
        lambda symbol, timeframe="6M": {
            "symbol": symbol,
            "timeframe": timeframe,
            "candles": measured,
            "provider": "stub",
        },
    )

    monkeypatch.chdir(tmp_path)  # artefato do expert fica contido em tmp
    collector = ProfessionalCollector(cache_dir=str(tmp_path / "cache"))
    data = asyncio.run(
        collector.collect(
            _REFERENCE_TICKER,
            include_price=False,
            include_fundamentals=False,
            include_news=False,
            include_social=False,
            include_macro=False,
            include_technicals=False,
        )
    )

    assert data["candle_sources"] == ["reference_cache", "provider"]
    assert len(data["candles"]) >= _EXPERT_FLOOR
    # A janela curta que MathHub, gráfico e pacote de evidência já consumiam
    # continua exatamente do mesmo tamanho.
    assert len(data["ohlcv"]) == _MEASURED_PROVIDER_BARS

    events: list[dict[str, object]] = []
    monkeypatch.setattr(neural_node, "get_stream_writer", lambda: events.append)
    result = asyncio.run(
        neural_node.node_neural_decision(
            {"run_id": f"floor-{uuid.uuid4()}", "ticker": _REFERENCE_TICKER, "data": data}
        )
    )["neural_decision"]

    assert result["status"] != "insufficient_data"
    assert "TOO_FEW_LABELLED_SAMPLES" not in result["reason_codes"]
    assert result["reason_codes"] != ["NO_CANDLES"]
    # O node leu a série longa, não a janela curta.
    assert neural_node._extract_candles(data) == data["candles"]


def test_short_window_alone_still_trips_the_sample_floor(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Contraprova: sem o histórico longo, o comportamento antigo persiste."""
    now = datetime.now(UTC).replace(microsecond=0)
    measured = _synthetic_candles(
        _MEASURED_PROVIDER_BARS, start=now - timedelta(days=_MEASURED_PROVIDER_BARS - 1)
    )

    monkeypatch.chdir(tmp_path)
    events: list[dict[str, object]] = []
    monkeypatch.setattr(neural_node, "get_stream_writer", lambda: events.append)
    result = asyncio.run(
        neural_node.node_neural_decision(
            {
                "run_id": f"short-{uuid.uuid4()}",
                "ticker": _REFERENCE_TICKER,
                "data": {"ohlcv": measured, "candles": measured},
            }
        )
    )["neural_decision"]

    assert result["status"] == "insufficient_data"
    assert result["reason_codes"] == ["TOO_FEW_LABELLED_SAMPLES"]
    assert _MEASURED_PROVIDER_BARS < _EXPERT_FLOOR


# ── Contra o cache real deste disco (gitignored; pula se ausente) ────────────


@pytest.mark.skipif(
    reference_csv_path(_REFERENCE_TICKER) is None,
    reason="data/reference/ é gitignored — cache ausente nesta árvore",
)
def test_real_reference_cache_carries_the_expert_past_the_sample_floor(
    tmp_path: Path,
) -> None:
    candles = read_reference_candles(_REFERENCE_TICKER)

    assert len(candles) >= _EXPERT_FLOOR
    result = TechnicalNeuralExpert(artifact_dir=tmp_path / "models").evaluate(
        _REFERENCE_TICKER, candles, now=datetime.now(UTC)
    )
    assert "TOO_FEW_LABELLED_SAMPLES" not in result["reason_codes"]
    assert result["status"] != "insufficient_data"
