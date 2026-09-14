"""Tests for config/reference — deterministic BR tax and FGC lookups.

The point of these tests is twofold:
  1. The numbers are the ones the authoritative sources carry (Lei 11.033/2004,
     Decreto 6.306/2007 Anexo, FGC).
  2. When the data is not usable the lookup refuses (None) instead of
     estimating — degrading explicitly, never to "assume zero tax".
"""

from __future__ import annotations

import json

import pytest

from core.trading.reference_data import (
    BR_TAX_AND_FGC_PATH,
    fgc_limits,
    iof_rate_for_days,
    ir_rate_for_days,
    reference_state,
)


def _manifest() -> dict:
    return json.loads(BR_TAX_AND_FGC_PATH.read_text(encoding="utf-8"))


# ══════════════════════════════════════════════════════════════════════
# Estado do manifesto
# ══════════════════════════════════════════════════════════════════════


def test_shipped_manifest_is_fresh_and_complete():
    state = reference_state()
    assert state["state"] == "fresh"
    assert set(state["blocks"]) == {"ir_renda_fixa", "iof_renda_fixa", "fgc"}


def test_every_block_carries_its_own_source_and_verification():
    """Cada numero tem que poder citar de onde veio — sem fonte, sem dado."""
    data = _manifest()
    assert data["verified_at"] == "2026-09-13T00:00:00Z"
    for block in ("ir_renda_fixa", "iof_renda_fixa", "fgc"):
        assert data[block]["source_url"].startswith("https://")
        assert data[block]["verified_at"]


def test_state_is_missing_when_the_file_does_not_exist(tmp_path):
    assert reference_state(tmp_path / "nope.json")["state"] == "missing"
    assert ir_rate_for_days(180, tmp_path / "nope.json") is None
    assert iof_rate_for_days(1, tmp_path / "nope.json") is None
    assert fgc_limits(tmp_path / "nope.json") is None


def test_state_is_invalid_on_wrong_schema_version(tmp_path):
    path = tmp_path / "ref.json"
    path.write_text(json.dumps({"schema_version": 99}), encoding="utf-8")

    assert reference_state(path)["state"] == "invalid"
    assert ir_rate_for_days(180, path) is None
    assert iof_rate_for_days(1, path) is None
    assert fgc_limits(path) is None


def test_state_is_invalid_on_unreadable_json(tmp_path):
    path = tmp_path / "ref.json"
    path.write_text("{nao e json", encoding="utf-8")

    assert reference_state(path)["state"] == "invalid"


def test_state_is_stale_past_the_ttl_and_lookups_refuse(tmp_path):
    """Stale nao vira 'tudo liberado': o lookup recusa em vez de estimar."""
    data = _manifest()
    data["verified_at"] = "2020-01-01T00:00:00Z"
    path = tmp_path / "ref.json"
    path.write_text(json.dumps(data), encoding="utf-8")

    state = reference_state(path)
    assert state["state"] == "stale"
    assert state["age_days"] > state["ttl_days"]
    assert ir_rate_for_days(180, path) is None
    assert iof_rate_for_days(1, path) is None
    assert fgc_limits(path) is None


# ══════════════════════════════════════════════════════════════════════
# IR regressivo de renda fixa — Lei 11.033/2004, art. 1o
# ══════════════════════════════════════════════════════════════════════


@pytest.mark.parametrize(
    ("days", "expected"),
    [
        (1, 0.225),
        (180, 0.225),  # fronteira: "prazo de ate 180 dias"
        (181, 0.20),  # fronteira: "181 dias ate 360 dias"
        (360, 0.20),
        (361, 0.175),  # fronteira: "361 dias ate 720 dias"
        (720, 0.175),
        (721, 0.15),  # fronteira: "acima de 720 dias"
        (3650, 0.15),
    ],
)
def test_ir_rate_boundaries(days, expected):
    assert ir_rate_for_days(days) == pytest.approx(expected)


def test_ir_rate_refuses_invalid_day_counts():
    assert ir_rate_for_days(-1) is None
    assert ir_rate_for_days("180") is None
    assert ir_rate_for_days(None) is None
    assert ir_rate_for_days(180.0) == pytest.approx(0.225)  # numero continua numero


# ══════════════════════════════════════════════════════════════════════
# IOF regressivo — Decreto 6.306/2007, art. 32 e ANEXO
# ══════════════════════════════════════════════════════════════════════


@pytest.mark.parametrize(
    ("day", "expected"),
    [
        (1, 0.96),
        (2, 0.93),
        (15, 0.50),
        (28, 0.06),
        (29, 0.03),
        (30, 0.0),
    ],
)
def test_iof_rate_follows_the_annex(day, expected):
    assert iof_rate_for_days(day) == pytest.approx(expected)


def test_iof_is_zero_from_the_thirtieth_day_onward():
    """Dia 30 = 00 no Anexo: zero e um valor CONHECIDO, nao um chute."""
    assert iof_rate_for_days(30) == 0.0
    assert iof_rate_for_days(31) == 0.0
    assert iof_rate_for_days(400) == 0.0


def test_iof_rate_refuses_invalid_day_counts():
    assert iof_rate_for_days(0) is None
    assert iof_rate_for_days(-5) is None
    assert iof_rate_for_days("15") is None


def test_iof_annex_has_all_thirty_days_and_is_monotonic():
    tabela = _manifest()["iof_renda_fixa"]["tabela"]
    assert [row["dia"] for row in tabela] == list(range(1, 31))
    aliquotas = [row["aliquota_pct"] for row in tabela]
    assert aliquotas == sorted(aliquotas, reverse=True)
    assert aliquotas[0] == 96.0
    assert aliquotas[-1] == 0.0


# ══════════════════════════════════════════════════════════════════════
# FGC — cobertura
# ══════════════════════════════════════════════════════════════════════


def test_fgc_limits_are_the_published_ones():
    limits = fgc_limits()
    assert limits is not None
    assert limits["limite_por_cpf_por_instituicao"] == 250000.0
    assert limits["teto_global_por_periodo"] == 1000000.0
    assert limits["teto_global_periodo_anos"] == 4
    assert limits["source_url"].startswith("https://www.fgc.org.br")


def test_fgc_separates_covered_from_uncovered():
    limits = fgc_limits()
    assert limits is not None
    cobertos = " ".join(limits["cobertos"]).lower()
    nao_cobertos = " ".join(limits["nao_cobertos"]).lower()

    # Os instrumentos que um agente de renda fixa realmente usa.
    assert "poupanca" in cobertos
    assert "cdb" in cobertos or "depositos a prazo" in cobertos
    assert "lci" in cobertos
    assert "lca" in cobertos
    # O que NAO tem cobertura e igualmente importante.
    assert "acoes" in nao_cobertos
    assert "fundos" in nao_cobertos
