"""
PennyLab Scoring — Motor de Decisão (orquestra experts, não recalcula)
======================================================================
100% determinístico. Sem LLM. Sem dados fabricados.
Se dados ausentes → scores permanecem em 0.0 → confidence baixa → WATCH_ONLY.

Escala unificada: 0-1.
Princípio: Python calcula. LLM orquestra. Marco decide.
"""

from __future__ import annotations

from typing import List, Tuple

from .schemas import Decision, PennylabScores, PennylabReport, SignalInput, DataQuality
from .config import THRESHOLDS, MAX_PRICE_PENNY
from .mathcore_adapter import _clamp, build_mathcore_verdict

from .experts import (
    VolumeSpikeExpert,
    WhalePrintExpert,
    PumpDumpExpert,
    LiquidityRiskExpert,
)

# Instâncias singleton dos experts
_volume_expert = VolumeSpikeExpert()
_whale_expert = WhalePrintExpert()
_pump_expert = PumpDumpExpert()
_liquidity_expert = LiquidityRiskExpert()


# ---------------------------------------------------------------------------
# Motor de scores consolidado (orquestra experts)
# ---------------------------------------------------------------------------


def compute_scores(signal: SignalInput) -> Tuple[PennylabScores, List[str]]:
    """
    Orquestra os 4 experts e combina scores.
    Retorna (scores 0-1, evidências).
    Nunca fabrica dados — scores ficam em 0.0 se dado ausente.
    """
    evidence: List[str] = []

    vol = _volume_expert.evaluate(signal)
    whale = _whale_expert.evaluate(signal)
    pump = _pump_expert.evaluate(signal)
    liq = _liquidity_expert.evaluate(signal)

    evidence.extend(vol.evidence)
    evidence.extend(whale.evidence)
    evidence.extend(pump.evidence)
    evidence.extend(liq.evidence)

    # Combinados (evitando dupla contagem)
    # whale_suspicion = baleia + volume spike (evita contar volume 2x)
    whale_suspicion = _clamp(whale.score * 0.6 + vol.score * 0.4)

    # pump_probability = pump-and-dump (já incorpora volume e price action)
    pump_probability = pump.score

    # trap_risk = pump + liquidez (se pumpa mas não consegue sair = armadilha)
    trap_risk = _clamp(pump.score * 0.5 + liq.score * 0.5)

    # liquidity_risk = liquidez pura
    liquidity_risk = liq.score

    # expected_loss = armadilha + liquidez
    expected_loss = _clamp(trap_risk * 0.4 + liquidity_risk * 0.6)

    scores = PennylabScores(
        whale_suspicion=round(whale_suspicion, 3),
        pump_probability=round(pump_probability, 3),
        trap_risk=round(trap_risk, 3),
        liquidity_risk=round(liquidity_risk, 3),
        expected_loss=round(expected_loss, 3),
    )
    return scores, evidence


# ---------------------------------------------------------------------------
# Motor de decisão
# ---------------------------------------------------------------------------


def compute_confidence(signal: SignalInput, scores: PennylabScores) -> float:
    """Confiança proporcional à quantidade de dados disponíveis."""
    fields = [
        signal.price,
        signal.volume,
        signal.avg_volume_10d,
        signal.bid,
        signal.ask,
        signal.shares_float,
        signal.prev_close,
    ]
    available = sum(1 for f in fields if f is not None)
    base = available / len(fields)
    if signal.data_quality == DataQuality.MANUAL:
        base *= 0.85
    return round(_clamp(base), 3)


def make_decision(
    scores: PennylabScores,
    confidence: float,
    veracity_passed: bool,
    signal: SignalInput,
) -> Tuple[Decision, List[str], List[str], List[str]]:
    """
    Aplica as regras de decisão centrais — hierarquia de 7 níveis.
    Retorna (Decision, risks, entry_conditions, exit_conditions).

    Ordem de avaliação (a primeira que disparar vence):
      1. VeracityGate falhou          → NO_TRADE
      2. Dados insuficientes          → WATCH_ONLY
      3. Liquidez crítica             → NO_TRADE
      4. Armadilha confirmada         → NO_TRADE
      5. Baleia + risco controlado    → PAPER_TRADE / MICRO_ENTRY
      6. Setup limpo (BULLISH)        → BULLISH
      7. Risco elevado (BEARISH)      → BEARISH
      8. Default                      → WATCH_ONLY
    """
    risks: List[str] = []
    entry: List[str] = []
    exits: List[str] = []
    t = THRESHOLDS

    # ── Regra 0: VeracityGate ──
    if not veracity_passed:
        risks.append("VeracityGate: dados inconsistentes")
        return Decision.NO_TRADE, risks, entry, exits

    # ── Regra 1: dados insuficientes ──
    if confidence < t.MIN_REPORT_CONFIDENCE:
        risks.append(f"Confiança insuficiente ({confidence:.0%})")
        return Decision.WATCH_ONLY, risks, entry, exits

    # ── Regra 2: liquidez crítica → NÃO ENTRA ──
    if scores.liquidity_risk >= t.LIQUIDITY_NO_TRADE:
        risks.append(f"Liquidez crítica ({scores.liquidity_risk:.0%})")
        return Decision.NO_TRADE, risks, entry, exits

    # ── Regra 3: pump + trap combinados → ARMADILHA ──
    if scores.trap_risk >= t.TRAP_NO_TRADE and scores.pump_probability >= t.PUMP_NO_TRADE:
        risks.append(f"Armadilha: pump={scores.pump_probability:.0%} + trap={scores.trap_risk:.0%}")
        return Decision.NO_TRADE, risks, entry, exits

    # ── Regra 4: baleia suspeita com risco controlado → SEGUIR ──
    if (
        scores.whale_suspicion >= t.WHALE_PAPER
        and scores.trap_risk < t.TRAP_SAFE
        and scores.liquidity_risk < t.LIQUIDITY_SAFE
    ):
        entry.append("Apenas PAPER ou MICRO (< $50 USD)")
        entry.append("Stop-loss obrigatório")
        exits.append("Sair se preço recuar > 8%")
        exits.append("Sair se volume colapsar > 50% em 5min")
        risks.append(f"Baleia detectada ({scores.whale_suspicion:.0%}) — cautela")
        if signal.price is not None and signal.price <= MAX_PRICE_PENNY:
            return Decision.MICRO_ENTRY, risks, entry, exits
        return Decision.PAPER_TRADE, risks, entry, exits

    # ── Regra 5: Setup limpo → BULLISH ──
    is_clean = (
        scores.whale_suspicion <= t.BULLISH_MAX_WHALE
        and scores.pump_probability <= t.BULLISH_MAX_PUMP
        and scores.trap_risk <= t.BULLISH_MAX_TRAP
        and scores.liquidity_risk <= t.BULLISH_MAX_LIQUIDITY
        and scores.expected_loss <= t.BULLISH_MAX_EXPECTED_LOSS
        and confidence >= t.BULLISH_MIN_CONFIDENCE
    )
    if is_clean:
        entry.append("Setup limpo — scores baixos")
        entry.append("Definir stop-loss antes de entrar")
        exits.append("Stop sugerido: -8%")
        if signal.data_quality == DataQuality.REAL:
            risks.append(f"Dados reais. Confiança {confidence:.0%}.")
        else:
            risks.append("Verificar com fonte independente antes de agir.")
        return Decision.BULLISH, risks, entry, exits

    # ── Regra 6: Risco elevado → BEARISH ──
    if (
        scores.trap_risk >= t.BEARISH_MIN_TRAP
        or scores.expected_loss >= t.BEARISH_MIN_EXPECTED_LOSS
    ):
        risks.append(
            f"Risco elevado: trap={scores.trap_risk:.0%}, expected_loss={scores.expected_loss:.0%}"
        )
        return Decision.BEARISH, risks, entry, exits

    # ── Regra 7: Default → observar ──
    risks.append("Perfil misto — monitorar antes de decidir.")
    return Decision.WATCH_ONLY, risks, entry, exits


# ---------------------------------------------------------------------------
# Ponto de entrada principal do scoring
# ---------------------------------------------------------------------------


def analyze(signal: SignalInput, veracity_passed: bool = True) -> PennylabReport:
    """
    Análise completa de um SignalInput.
    Orquestra experts → combina scores → aplica decisão.
    """
    scores, evidence = compute_scores(signal)
    confidence = compute_confidence(signal, scores)
    decision, risks, entry, exits = make_decision(scores, confidence, veracity_passed, signal)
    mathcore_verdict = build_mathcore_verdict(scores)

    return PennylabReport(
        ticker=signal.ticker,
        decision=decision,
        scores=scores,
        mathcore_verdict=mathcore_verdict,
        evidence=evidence,
        risks=risks,
        entry_conditions=entry,
        exit_conditions=exits,
        confidence=confidence,
        data_quality=signal.data_quality,
        veracity_passed=veracity_passed,
    )
