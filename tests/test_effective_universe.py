"""Universo negociável efetivo — `td_universe` e o filtro de candidatos.

Cobre o que foi exposto e ligado em 2026-09-14:

- `effective_universe_state` / `effective_symbols` / `effective_row` / `effective_cluster`
  (config/td_universe_effective.json, produzido por scripts/build_effective_universe.py);
- a REGRA que o filtro do collector usa: membro do universo com `eligible=False` é
  rejeitado com motivo `not_eligible_at_1000`; quem está FORA do universo não é tocado.

O último teste é de propósito: ele **fixa um limite conhecido** do dado, não uma
qualidade. VFV e VOO são o mesmo índice em moedas diferentes e o corte de 0,95 NÃO
os fundiu — quem usar só o cluster vai achar que são diversificação. Se um dia o
gerador passar a fundi-los, este teste quebra e obriga a decisão a ser consciente.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from core.trading.td_universe import (
    effective_cluster,
    effective_row,
    effective_symbols,
    effective_universe_state,
)


def test_estado_do_universo_e_fresh() -> None:
    st = effective_universe_state()
    assert st["state"] == "fresh", f"universo não está fresh: {st}"
    assert st["symbol_total"] == 108
    assert st["eligible_total"] < st["symbol_total"], "elegíveis == total: nenhum portão aplicado"


def test_elegiveis_e_um_subconjunto_nao_vazio() -> None:
    elegiveis = effective_symbols()
    assert elegiveis is not None, "universo fresh deveria devolver o conjunto"
    assert len(elegiveis) == effective_universe_state()["eligible_total"]
    assert "VFV" in elegiveis


def test_arkk_e_rejeitado_por_friccao() -> None:
    """ARKK é o caso âncora: membro do universo, excluído pelo portão de 0,5%."""
    row = effective_row("ARKK")
    assert row is not None, "ARKK está na lista dos 108"
    assert row["eligible"] is False
    assert row.get("correlation_cluster")


def test_fora_do_universo_devolve_none_e_nao_reprovacao() -> None:
    """`None` é 'fora do universo', não 'reprovado'.

    A distinção importa: candidato de fora (ação avulsa, penny) segue para os
    gates dele e não pode ser filtrado por engano.
    """
    for simbolo in ("AAPL", "PETR4.SA", "ZZZZ"):
        assert effective_row(simbolo) is None


def test_cluster_do_par_de_moeda_e_o_mesmo() -> None:
    """TDOC e TDOC.U são o mesmo fundo em duas moedas — o eixo de identidade os une."""
    assert effective_cluster("TDOC") == effective_cluster("TDOC.U") is not None


def test_limite_conhecido_vfv_e_voo_em_clusters_diferentes() -> None:
    """LIMITE DOCUMENTADO, não qualidade.

    Mesmo índice, moedas diferentes: o corte de 0,95 mede MOEDA e não funde.
    Quem consumir só o cluster vai tratar VFV + VOO como diversificação, e não é.
    Este teste existe para o dia em que isso mudar ser uma decisão, não um acidente.
    """
    vfv, voo = effective_cluster("VFV"), effective_cluster("VOO")
    assert vfv is not None and voo is not None
    assert vfv != voo, (
        "VFV e VOO passaram a cair no mesmo cluster — o gerador mudou. "
        "Confirme se a mudança é desejada antes de ajustar este teste."
    )
    # o controle: mesma moeda, mesmo índice ⇒ funde
    assert effective_cluster("VOO") == effective_cluster("SPY")
