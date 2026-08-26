"""
PennyLab Pipeline Hook — Integração com UniversalPipeline
==========================================================
Fornece funções assíncronas para o pipeline principal chamar o PennyLab.

- run_pennylab_analysis: análise completa de um ticker (substitui WATCH_ONLY genérico)
- run_postmortem_llm: análise postmortem com LLM via ModelGateway
"""

from __future__ import annotations

import json
import logging
from typing import Any

logger = logging.getLogger(__name__)


def analyze_ticker_sync(ticker: str) -> dict[str, Any]:
    """
    Análise completa síncrona de um ticker via PennyLab.
    Chamada pelo pipeline quando a rota é 'pennylab'.
    Retorna dicionário pronto para serialização.
    """
    from .data_provider import fetch_signal
    from .experts.veracity_gate import PennylabVeracityGate
    from .rag_hooks import enrich_with_rag
    from .scoring import analyze

    signal = fetch_signal(ticker)
    gate = PennylabVeracityGate()
    gate_result = gate.check(signal)

    if not gate_result.passed:
        return {
            "ticker": ticker,
            "decision": "NO_TRADE",
            "veracity_violations": gate_result.violations,
            "message": "VeracityGate bloqueou — dados inconsistentes",
            "source": "pennylab",
        }

    report = analyze(signal, veracity_passed=gate_result.passed)
    report.evidence = enrich_with_rag(ticker, report.evidence)

    if gate_result.warnings:
        report.risks = gate_result.warnings + report.risks

    return {
        "ticker": ticker,
        "decision": str(report.decision),
        "scores": report.scores.model_dump(),
        "evidence": report.evidence[:5],
        "risks": report.risks,
        "entry_conditions": report.entry_conditions,
        "exit_conditions": report.exit_conditions,
        "confidence": report.confidence,
        "data_quality": str(report.data_quality),
        "source": "pennylab",
        "mathcore_verdict": report.mathcore_verdict,
    }


async def run_pennylab_analysis(ticker: str) -> dict[str, Any]:
    """Wrapper assíncrono para pipeline."""
    import asyncio

    return await asyncio.to_thread(analyze_ticker_sync, ticker)


# ---------------------------------------------------------------------------
# Postmortem com LLM
# ---------------------------------------------------------------------------

POSTMORTEM_SYSTEM_PROMPT = """\
Voce e um analista forense de trades no laboratorio PennyLab.

Analise o historico de trades abaixo e produza um postmortem em portugues brasileiro.
Seja tecnico, direto e baseado nos dados. Nao invente nada.

Formato de saida:
1. **Resumo**: total de trades, P&L total, win rate
2. **Padroes identificados**: o que funcionou, o que nao funcionou
3. **Licoes**: o que fazer diferente nos proximos trades
4. **Nota do analista** (0-10): qualidade das decisoes registradas

Maximo 300 palavras.
"""


def _build_postmortem_prompt(ticker: str, trades: list) -> str:
    trades_json = json.dumps(trades, indent=2, ensure_ascii=False, default=str)
    return (
        f"Ticker: {ticker}\n\n"
        f"Historico de trades ({len(trades)} registros):\n"
        f"{trades_json[:4000]}\n\n"
        f"Produza o postmortem conforme o formato especificado."
    )


async def run_postmortem_llm(
    ticker: str,
    gateway=None,
) -> dict[str, Any]:
    """
    Postmortem com análise LLM para um ticker.
    Se gateway não for fornecido, retorna apenas dados estatísticos.
    """
    from .lab_journal import journal

    trades = journal.postmortem(ticker)
    if not trades or trades.get("total_trades", 0) == 0:
        return {
            "ticker": ticker,
            "error": "Nenhum trade registrado para este ticker.",
            "total_trades": 0,
        }

    base = {
        "ticker": ticker,
        "total_trades": trades.get("total_trades", 0),
        "total_pnl_pct": trades.get("total_pnl_pct", 0),
        "win_rate": trades.get("win_rate", 0),
        "entries": trades.get("entries", []),
    }

    if gateway is None:
        base["llm_analysis"] = None
        base["note"] = "ModelGateway nao fornecido — apenas dados estatisticos."
        return base

    try:
        prompt = _build_postmortem_prompt(ticker, trades.get("entries", []))
        response = await gateway.chat_completion(
            messages=[
                {"role": "system", "content": POSTMORTEM_SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            temperature=0.3,
            max_tokens=500,
        )
        base["llm_analysis"] = response
    except Exception as e:  # noqa: BLE001 — falha do gateway de LLM não pode derrubar o postmortem; cai para stats-only
        logger.warning(f"Postmortem LLM falhou para {ticker}: {e}")
        base["llm_analysis"] = None
        base["llm_error"] = str(e)

    return base
