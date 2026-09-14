"""Tripwire do gancho da caderneta no `tool_executor`.

**O que este teste É:** um alarme de remoção acidental. O gancho que grava a
recomendação mora no `tool_executor` — e **não** no `auto_execute_paper` — porque
aquele nó só é alcançado quando o contrato libera `submit_paper_order`, que vem
desligado por default (`SUPEREZIO_ENABLE_PAPER_ORDER_SUBMIT=0`). Enquanto isso
foi assim, a caderneta nunca recebeu uma linha e o aprendizado seguiu faminto.

**O que este teste NÃO É:** prova de comportamento. Ele lê o fonte, não executa
a ordem. Se alguém trocar o gancho por outro caminho que não grava, este teste
passa e o defeito volta em silêncio. Cobertura de execução exige rodar o nó
`tool_executor` num caminho de ordem — que **ainda não está feito**, e é a
dívida declarada aqui.

A cobertura de execução que existe hoje é indireta: `test_recommendation_ledger.py`
(42 testes, a caderneta) e `test_ledger_learning_wiring.py` (5, fechador→motor).
"""

from __future__ import annotations

from pathlib import Path

sys_path_src = Path(__file__).resolve().parents[1] / "src"


def _fonte_do_tool_executor() -> str:
    return (sys_path_src / "core" / "pipeline" / "nodes" / "tool_executor.py").read_text(
        encoding="utf-8"
    )


def test_gancho_da_caderneta_esta_no_caminho_de_ordem() -> None:
    """O gancho existe e está ANTES dos gates — a recomendação é gravada mesmo bloqueada."""
    fonte = _fonte_do_tool_executor()
    assert "_record_recommendation" in fonte, (
        "O gancho da caderneta sumiu do tool_executor. Sem ele a recomendação "
        "volta a não ser registrada e o aprendizado fica sem corpus."
    )
    assert "recommendation_ledger_hook_failed" in fonte, (
        "O aviso de falha do gancho sumiu — uma falha de gravação voltaria a ser silenciosa."
    )


def test_gancho_roda_antes_do_gate_de_sobrevivencia() -> None:
    """Ordem importa: gravar ANTES do gate registra também o que foi BLOQUEADO.

    O que o dono quer registrar é o que o SISTEMA recomendou — não só o que
    passou. Se o gancho escorregar para depois do gate, a caderneta perde
    justamente as recomendações que os portões recusaram.
    """
    fonte = _fonte_do_tool_executor()
    pos_gancho = fonte.find("_record_recommendation")
    # A âncora do gate é o CALL SITE, não a primeira menção ao nome: o arquivo
    # importa a função no topo, e `find` sozinho media o import (bug do próprio
    # teste na primeira versão — o tripwire disparou em falso).
    pos_gate = fonte.find("survival_block = micro_capital_survival_block_reason")
    assert pos_gancho != -1, "gancho ausente"
    assert pos_gate != -1, "gate de sobrevivência ausente — o arquivo mudou de forma"
    assert pos_gancho < pos_gate, (
        "O gancho passou para DEPOIS do gate de sobrevivência: a caderneta "
        "deixou de registrar as recomendações bloqueadas."
    )


def test_a_caderneta_nao_e_um_portao() -> None:
    """Gravar é melhor-esforço: falhar no trilho não pode derrubar a execução."""
    fonte = _fonte_do_tool_executor()
    trecho = fonte[fonte.find("_record_recommendation") :][:900]
    assert "except Exception" in trecho or "except ImportError" in trecho, (
        "O gancho perdeu a fronteira de melhor esforço — uma falha de gravação "
        "passaria a derrubar a execução."
    )
