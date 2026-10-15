"""O cache OHLCV tem de ser alimentado, e por fontes com fallback.

Medido em 2026-10-13: ``data/historical_cache.db`` tinha 0 linhas e cinco
consumidores (``math_hub``, ``collector``, ``observation_builder``,
``batch_expert_runner``, ``bob_consciousness/body``). O alimentador existia e
nunca era chamado — e falava com a yfinance direto, por baixo do ``data_hub``,
sem cadeia de fallback. Estes testes fixam a cascata de fontes e a gravação.
"""

from __future__ import annotations

import importlib.util
import sqlite3
from pathlib import Path

import pytest

from core.trading import historical_cache

_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "fill_historical_cache.py"


def _script_mod():
    spec = importlib.util.spec_from_file_location("fill_historical_cache", _SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _linha(dia: str, preco: float = 10.0) -> historical_cache.CandleRow:
    return (dia, preco, preco + 1, preco - 1, preco, 1000.0)


def test_yahoo_symbol_traduz_os_tres_formatos_do_td() -> None:
    """Medido 2026-10-13: sem a tradução, os 83 canadenses davam 'possibly delisted'."""
    mod = _script_mod()
    assert mod.yahoo_symbol("FCID", "CAN") == "FCID.TO"  # código sem sufixo
    assert mod.yahoo_symbol("TGED-U", "CAN") == "TGED-U.TO"  # série em USD
    assert mod.yahoo_symbol("BTCX.B", "CAN") == "BTCX-B.TO"  # classe com ponto
    assert mod.yahoo_symbol("RY.TO", "CAN") == "RY.TO"  # já é Yahoo: não mexe
    assert mod.yahoo_symbol("SPY", "US") == "SPY"  # americano fica como está
    assert mod.yahoo_symbol("BRK.B", "USA") == "BRK-B"  # classe americana


def test_csv_stems_cobre_listagem_canadense_e_cambio() -> None:
    # BTCX.B é a listagem; o ficheiro do Yahoo é BTCX-B.TO.csv.
    assert "BTCX-B.TO" in historical_cache._csv_stems("BTCX.B")
    # CAD=X vira CAD_X.csv no arquivo do Coração.
    assert "CAD_X" in historical_cache._csv_stems("CAD=X")
    # RY.TO fica como está.
    assert historical_cache._csv_stems("RY.TO")[0] == "RY.TO"


def test_rows_from_candles_normaliza_e_ignora_malformado() -> None:
    candles = [
        {
            "observed_at": "2026-10-09T00:00:00Z",
            "open": 1,
            "high": 2,
            "low": 0.5,
            "close": 1.5,
            "volume": 10,
        },
        {"datetime": "2026-10-08", "open": 1, "high": 2, "low": 0.5, "close": 1.4, "volume": None},
        {"observed_at": "2026-10-07", "open": 1},  # sem close -> descartado
        {"open": 1, "high": 2, "low": 0.5, "close": 1.3},  # sem data -> descartado
    ]
    rows = historical_cache._rows_from_candles(candles)
    assert [r[0] for r in rows] == ["2026-10-09", "2026-10-08"]
    assert rows[1][5] == 0.0  # volume None vira 0, não derruba a linha


def test_cascata_prefere_o_yahoo_direto(monkeypatch: pytest.MonkeyPatch) -> None:
    """O caminho primário é a API do Yahoo por httpx — sem yfinance."""
    monkeypatch.setattr(
        historical_cache, "_rows_from_yahoo_chart", lambda t: [_linha("2026-10-09")]
    )
    monkeypatch.setattr(
        historical_cache, "_rows_from_mesh", lambda t: pytest.fail("não devia cair na malha")
    )
    rows, fonte = historical_cache._load_candle_rows("RY.TO")
    assert fonte == "yahoo_chart"
    assert len(rows) == 1


def test_cascata_cai_na_malha_quando_o_direto_falha(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(historical_cache, "_rows_from_yahoo_chart", lambda t: [])
    monkeypatch.setattr(historical_cache, "_rows_from_mesh", lambda t: [_linha("2026-10-09")])
    monkeypatch.setattr(
        historical_cache, "_rows_from_heart_csv", lambda t: pytest.fail("não devia cair no CSV")
    )
    rows, fonte = historical_cache._load_candle_rows("RY.TO")
    assert fonte == "mesh"
    assert len(rows) == 1


def test_cascata_cai_no_csv_local_por_ultimo(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(historical_cache, "_rows_from_yahoo_chart", lambda t: [])
    monkeypatch.setattr(historical_cache, "_rows_from_mesh", lambda t: [])
    monkeypatch.setattr(historical_cache, "_rows_from_heart_csv", lambda t: [_linha("2026-10-08")])
    rows, fonte = historical_cache._load_candle_rows("RY.TO")
    assert fonte == "heart_csv"
    assert len(rows) == 1


def test_cascata_sem_fonte_devolve_none(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(historical_cache, "_rows_from_yahoo_chart", lambda t: [])
    monkeypatch.setattr(historical_cache, "_rows_from_mesh", lambda t: [])
    monkeypatch.setattr(historical_cache, "_rows_from_heart_csv", lambda t: [])
    rows, fonte = historical_cache._load_candle_rows("NAOEXISTE")
    assert rows == []
    assert fonte == "none"


def test_parse_do_chart_prefere_adjclose() -> None:
    """Um split não pode virar salto: o valor usado é o ajustado."""
    payload = {
        "chart": {
            "result": [
                {
                    "timestamp": [1700000000, 1700086400],
                    "indicators": {
                        "quote": [
                            {
                                "open": [100.0, 50.0],
                                "high": [101.0, 51.0],
                                "low": [99.0, 49.0],
                                "close": [100.0, 50.0],
                                "volume": [1000, 2000],
                            }
                        ],
                        "adjclose": [{"adjclose": [100.0, 100.0]}],
                    },
                }
            ]
        }
    }
    rows = historical_cache._rows_from_chart_payload(payload)
    assert len(rows) == 2
    # O close cru caiu 50% (split); o ajustado fica plano — é o ajustado que entra.
    assert rows[0][4] == 100.0
    assert rows[1][4] == 100.0
    # quando o adjclose falta, o close cru é o fallback honesto
    payload["chart"]["result"][0]["indicators"].pop("adjclose")
    rows_cru = historical_cache._rows_from_chart_payload(payload)
    assert rows_cru[1][4] == 50.0


def test_yahoo_user_agent_usa_env_quando_existe(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SUPEREZIO_HEART_USER_AGENT", "SuperEzioHeart/1.0")
    assert historical_cache._yahoo_user_agent() == "SuperEzioHeart/1.0"
    monkeypatch.delenv("SUPEREZIO_HEART_USER_AGENT", raising=False)
    assert "Mozilla/5.0" in historical_cache._yahoo_user_agent()


def test_fetch_grava_e_le_de_volta(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    db = tmp_path / "cache.db"
    monkeypatch.setattr(historical_cache, "DB_PATH", db)
    monkeypatch.setattr(
        historical_cache,
        "_rows_from_yahoo_chart",
        lambda t: [_linha("2026-10-08", 10.0), _linha("2026-10-09", 11.0)],
    )

    gravados = historical_cache.fetch_and_cache_ticker("RY.TO")
    assert gravados == 2

    lidos = historical_cache.get_cached_ohlcv("RY.TO")
    assert [b["date"] for b in lidos] == ["2026-10-08", "2026-10-09"]
    assert lidos[-1]["close"] == 11.0

    # Idempotência: segunda chamada não refaz o trabalho (já há candles).
    with sqlite3.connect(db) as conn:
        assert conn.execute("SELECT COUNT(*) FROM ohlcv_cache").fetchone()[0] == 2


def test_fetch_sem_fonte_devolve_zero(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(historical_cache, "DB_PATH", tmp_path / "cache.db")
    monkeypatch.setattr(historical_cache, "_rows_from_yahoo_chart", lambda t: [])
    monkeypatch.setattr(historical_cache, "_rows_from_mesh", lambda t: [])
    monkeypatch.setattr(historical_cache, "_rows_from_heart_csv", lambda t: [])
    assert historical_cache.fetch_and_cache_ticker("NAOEXISTE") == 0
    assert historical_cache.get_cache_stats()["total_candles"] == 0
