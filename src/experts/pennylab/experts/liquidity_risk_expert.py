"""
LiquidityRiskExpert — escala 0-1, usa mathcore.
====================================================================
Penny stocks podem ter liquidez zero em segundos.
Este expert avalia: spread, volume, float e market cap
para estimar a dificuldade de saída em cenário adverso.

Princípio: se você não consegue sair, a entrada está errada.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List

from ..schemas import SignalInput
from ..mathcore_adapter import _clamp


@dataclass
class LiquidityRiskResult:
    score: float  # 0-1
    label: str
    exit_difficulty: str
    evidence: List[str] = field(default_factory=list)
    confidence: float = 0.0


class LiquidityRiskExpert:
    """
    Sensor de liquidez para penny stocks.
    Sem dado real → retorna risk=0 e confidence=0, não fabrica nada.
    """

    def evaluate(self, signal: SignalInput) -> LiquidityRiskResult:
        evidence: List[str] = []
        components: List[float] = []
        available = 0

        # Spread (peso 50%)
        if signal.bid is not None and signal.ask is not None and signal.bid > 0:
            available += 1
            spread_pct = (signal.ask - signal.bid) / signal.bid * 100
            if spread_pct >= 10:
                spread_score = 0.95
                evidence.append(f"spread={spread_pct:.1f}% (IMPOSSÍVEL sair)")
            elif spread_pct >= 5:
                spread_score = 0.75
                evidence.append(f"spread={spread_pct:.1f}% (ALTO)")
            elif spread_pct >= 2:
                spread_score = 0.40
                evidence.append(f"spread={spread_pct:.1f}% (MODERADO)")
            else:
                spread_score = 0.10
                evidence.append(f"spread={spread_pct:.1f}% (ACEITÁVEL)")
            components.append(spread_score * 0.50)
        else:
            evidence.append("spread: bid/ask indisponível")

        # Volume (peso 30%)
        if signal.volume is not None:
            available += 1
            if signal.volume < 100_000:
                vol_score = 0.90
                evidence.append(f"volume={signal.volume:,} (CRÍTICO)")
            elif signal.volume < 500_000:
                vol_score = 0.60
                evidence.append(f"volume={signal.volume:,} (BAIXO)")
            elif signal.volume < 2_000_000:
                vol_score = 0.25
                evidence.append(f"volume={signal.volume:,} (MODERADO)")
            else:
                vol_score = 0.05
                evidence.append(f"volume={signal.volume:,} (ADEQUADO)")
            components.append(vol_score * 0.30)
        else:
            evidence.append("volume: indisponível")

        # Float (peso 20%)
        if signal.shares_float is not None:
            available += 1
            if signal.shares_float < 5_000_000:
                float_score = 0.80
                evidence.append(f"float={signal.shares_float:,} (MICRO)")
            elif signal.shares_float < 20_000_000:
                float_score = 0.50
                evidence.append(f"float={signal.shares_float:,} (BAIXO)")
            else:
                float_score = 0.10
                evidence.append(f"float={signal.shares_float:,} (OK)")
            components.append(float_score * 0.20)
        else:
            evidence.append("float: indisponível")

        if not components:
            return LiquidityRiskResult(0.0, "INDISPONÍVEL", "INDISPONÍVEL", evidence, 0.0)

        total = _clamp(sum(components))
        confidence = round(available / 3, 2)
        label, exit_diff = self._classify(total)

        if total >= 0.75:
            evidence.append("⚠ RISCO DE LIQUIDEZ CRÍTICO")

        return LiquidityRiskResult(round(total, 3), label, exit_diff, evidence, confidence)

    def _classify(self, score: float):
        if score >= 0.80:
            return "CRÍTICO", "IMPOSSÍVEL"
        if score >= 0.60:
            return "ALTO", "DIFÍCIL"
        if score >= 0.35:
            return "MODERADO", "MODERADA"
        return "BAIXO", "FÁCIL"
