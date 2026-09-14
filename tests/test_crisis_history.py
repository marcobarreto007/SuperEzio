"""O histórico longo tem de CHEGAR aos sensores de crise.

Medido em 2026-09-14: o caminho de produção (``core.rag.macro_dataset``)
devolvia **zero** observações para os EUA e levantava ``ImportError`` (pyarrow
ausente) para o Canadá.  Os 12 sensores fechavam por ``insufficient_data`` e o
relatório saía ``unavailable``.  Estes testes fixam o encanamento do cache de
referência e os limites do que ainda não foi destravado.
"""

from __future__ import annotations

import asyncio
from collections import Counter
from pathlib import Path

import pytest

from core.data_collector import crisis_history
from core.data_collector.crisis_history import (
    build_crisis_history,
    build_crisis_input,
    read_bis_credit_to_gdp,
    read_fred_series,
    read_ofr_fsi,
    reference_available,
)
from experts.crisis.expert.crisis_expert import CrisisMathExpert

_BIS_HEADER = (
    "STRUCTURE,STRUCTURE_ID,ACTION,FREQ:Frequency,BORROWERS_CTY:Borrowers' country,"
    "TC_BORROWERS:Borrowing sector,TC_LENDERS:Lending sector,"
    "CG_DTYPE:Credit gap data type,TIME_PERIOD:Time period or range,"
    "OBS_VALUE:Observation Value,COLLECTION:Collection Indicator,DECIMALS:Decimals,"
    "UNIT_MEASURE:Unit of measure,UNIT_MULT:Unit Multiplier,TIME_FORMAT:Time Format,"
    "TITLE_TS:Title (tseries level),OBS_STATUS:Observation Status,"
    "OBS_CONF:Observation confidentiality,OBS_PRE_BREAK:Pre-Break Observation"
)


def _bis_row(country: str, gap_type: str, period: str, value: float) -> str:
    return (
        f"dataflow,BIS:WS_CREDIT_GAP(1.0),I,Q:{period},{country},P,A,{gap_type},"
        f"{period},{value},E,1,770,0,,,,A,F,"
    )


def _write_bis(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    lines = [_BIS_HEADER]
    for period, value in (("2000-Q1", 100.0), ("2000-Q2", 110.0), ("2000-Q3", 120.0)):
        lines.append(
            _bis_row("US: United States", "A: Credit-to-GDP ratios (actual data)", period, value)
        )
        lines.append(
            _bis_row("CA: Canada", "A: Credit-to-GDP ratios (actual data)", period, value + 50.0)
        )
        # Trend e gap não podem ser confundidos com a razão observada.
        lines.append(
            _bis_row("US: United States", "B: Credit-to-GDP trend (HP filter)", period, 999.0)
        )
        lines.append(
            _bis_row("US: United States", "C: Credit-to-GDP gaps (actual-trend)", period, -999.0)
        )
    (root / "WS_CREDIT_GAP_csv_flat.csv").write_text("\n".join(lines) + "\n", encoding="utf-8")


# ── BIS ──────────────────────────────────────────────────────────────────────


def test_bis_credit_to_gdp_is_read_per_country(tmp_path: Path) -> None:
    _write_bis(tmp_path)

    united_states = read_bis_credit_to_gdp("United States", tmp_path)
    canada = read_bis_credit_to_gdp("Canada", tmp_path)

    assert united_states["2000-01"] == 100.0
    assert canada["2000-01"] == 150.0
    # Um trimestre vira os três meses que ele cobre, com o mesmo valor.
    assert united_states["2000-02"] == 100.0
    assert united_states["2000-03"] == 100.0
    assert united_states["2000-06"] == 110.0


def test_bis_reader_ignores_trend_and_gap_rows(tmp_path: Path) -> None:
    _write_bis(tmp_path)

    united_states = read_bis_credit_to_gdp("United States", tmp_path)

    assert 999.0 not in united_states.values()
    assert -999.0 not in united_states.values()


def test_bis_reader_returns_nothing_for_an_unknown_country(tmp_path: Path) -> None:
    _write_bis(tmp_path)

    assert read_bis_credit_to_gdp("Atlantis", tmp_path) == {}


def test_missing_bis_file_yields_nothing_not_an_error(tmp_path: Path) -> None:
    assert read_bis_credit_to_gdp("United States", tmp_path) == {}


# ── FRED e OFR ───────────────────────────────────────────────────────────────


def test_fred_series_is_read_by_observation_date(tmp_path: Path) -> None:
    (tmp_path / "FRED_TEST.csv").write_text(
        "observation_date,TEST\n2024-01-02,3.5\n2024-01-03,\n2024-01-04,4.25\n",
        encoding="utf-8",
    )

    values = read_fred_series("FRED_TEST", tmp_path)

    assert values == {"2024-01-02": 3.5, "2024-01-04": 4.25}


def test_ofr_fsi_is_read_and_rejects_a_foreign_layout(tmp_path: Path) -> None:
    (tmp_path / "OFR_fsi.csv").write_text(
        "Date,OFR FSI,Credit\n2000-01-03,2.14,0.54\n2000-01-04,2.421,0.604\n",
        encoding="utf-8",
    )
    assert read_ofr_fsi(tmp_path) == {"2000-01-03": 2.14, "2000-01-04": 2.421}

    (tmp_path / "outra").mkdir()
    (tmp_path / "outra" / "OFR_fsi.csv").write_text("Quando,Valor\nx,1\n", encoding="utf-8")
    assert read_ofr_fsi(tmp_path / "outra") == {}


# ── A célula de data do Shiller ──────────────────────────────────────────────


@pytest.mark.parametrize(
    ("cell", "expected"),
    [
        ("1871.01", "1871-01"),
        ("2026.09", "2026-09"),
        # pandas devolve a coluna como float: 1871.1 é OUTUBRO, e a forma com
        # duas casas é a única que preserva a diferença para 1871.01.
        (1871.01, "1871-01"),
        (1871.1, "1871-10"),
        ("1871.13", None),
        ("sem-data", None),
        (float("nan"), None),
        (None, None),
    ],
)
def test_month_cell_normalisation(cell: object, expected: str | None) -> None:
    assert crisis_history._normalize_month_cell(cell) == expected


# ── Montagem do CrisisInput ──────────────────────────────────────────────────


def test_crisis_history_is_chronological_and_non_duplicated() -> None:
    if not reference_available():
        pytest.skip("cache de referência de crise ausente (data/reference é gitignored)")

    history = build_crisis_history("United States")

    dates = [observation.date for observation in history["observations"]]
    assert dates == sorted(dates)
    assert len(set(dates)) == len(dates)
    assert history["bars"] == len(history["observations"])


def test_crisis_input_accepts_the_assembled_history() -> None:
    if not reference_available():
        pytest.skip("cache de referência de crise ausente (data/reference é gitignored)")

    crisis_input = build_crisis_input("United States", asset_symbol="SPY")

    assert crisis_input is not None
    # Os portões nomeados pelos próprios sensores.
    assert len(crisis_input.observations) >= 61
    assert len(crisis_input.market_series or []) >= 61
    assert all(observation.close > 0 for observation in crisis_input.market_series or [])


def test_empty_cache_yields_no_input(tmp_path: Path) -> None:
    assert build_crisis_input("United States", reference_root=tmp_path) is None


# ── O caminho do coletor ─────────────────────────────────────────────────────


def test_collector_prefers_reference_cache_and_falls_back(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from core.data_collector.collector import DataCollector

    if not reference_available():
        pytest.skip("cache de referência de crise ausente (data/reference é gitignored)")

    crisis_input, source = DataCollector._crisis_input_for("United States", "SPY")
    assert source == "ReferenceCache"
    assert crisis_input is not None

    monkeypatch.setattr(crisis_history, "build_crisis_input", lambda *a, **k: None)

    class _EmptyMacro:
        @staticmethod
        def query_context(country: str, top_n: int = 24) -> list[dict]:
            return []

    monkeypatch.setattr("core.rag.macro_dataset.macro_engine", _EmptyMacro(), raising=False)
    assert DataCollector._crisis_input_for("United States", "SPY") == (None, None)


def test_crisis_expert_is_no_longer_unavailable() -> None:
    """Contra o cache real: o relatório sai de 'unavailable' e há sensor vivo."""
    if not reference_available():
        pytest.skip("cache de referência de crise ausente (data/reference é gitignored)")

    crisis_input = build_crisis_input("United States", asset_symbol="SPY")
    assert crisis_input is not None
    report = CrisisMathExpert().analyze(crisis_input)

    statuses = Counter(result.status for result in report.sensor_results)
    assert report.status != "unavailable"
    assert statuses["ok"] >= 1
    # Ainda há sensores sem dado: o cache não cobre retornos bancários
    # individuais (SRISK/LRMES) nem o serviço da dívida.
    assert statuses["insufficient_data"] < len(report.sensor_results)


def test_collector_crisis_analysis_reports_its_source() -> None:
    if not reference_available():
        pytest.skip("cache de referência de crise ausente (data/reference é gitignored)")

    from core.data_collector.collector import DataCollector

    result = asyncio.run(DataCollector()._get_crisis_analysis("SPY"))

    assert "error" not in result
    assert result["data_source"] == "ReferenceCache"
    assert result["observations"] >= 61
    assert result["report"]["status"] != "unavailable"
