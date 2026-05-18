"""
PumpDumpExpert — escala 0-1, usa mathcore.
==========================================
Analisa padrão clássico de P&D:
  - Preço sobe X% em curto espaço (sem notícia fundamentada)
  - Volume explode acima da média
  - RSI extremamente sobrecomprado
  - Sinais externos de "hype" (newsletters, fóruns)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List

from ..schemas import SignalInput
from ..mathcore_adapter import _clamp, _simple_return


@dataclass
class PumpDumpResult:
    score: float  # 0-1
    phase: str
    evidence: List[str] = field(default_factory=list)
    confidence: float = 0.0


class PumpDumpExpert:
    """
    Classifica a fase de pump-and-dump de um ativo.
    NÃO decide entrada/saída — apenas informa a fase estimada.
    """

    def evaluate(self, signal: SignalInput) -> PumpDumpResult:
        evidence: List[str] = []
        score = 0.0
        available = 0

        # Price action (peso 50%)
        if signal.price is not None and signal.prev_close is not None and signal.prev_close > 0:
            available += 1
            change = _simple_return(signal.price, signal.prev_close) * 100
            if change >= 100:
                score += 0.50
                evidence.append(f"price_change=+{change:.0f}% (PUMP EXTREMO)")
            elif change >= 50:
                score += 0.35
                evidence.append(f"price_change=+{change:.0f}% (PUMP FORTE)")
            elif change >= 20:
                score += 0.20
                evidence.append(f"price_change=+{change:.0f}% (movimento suspeito)")
            elif change <= -30:
                score += 0.10
                evidence.append(f"price_change={change:.0f}% (possível DUMP)")
            else:
                evidence.append(f"price_change={change:.1f}% (normal)")
        else:
            evidence.append("price_change: dados insuficientes")

        # Volume (peso 30%)
        if signal.volume is not None and signal.avg_volume_10d and signal.avg_volume_10d > 0:
            available += 1
            ratio = signal.volume / signal.avg_volume_10d
            if ratio >= 10:
                score += 0.30
                evidence.append(f"volume_ratio={ratio:.1f}x (EXPLOSÃO)")
            elif ratio >= 5:
                score += 0.20
                evidence.append(f"volume_ratio={ratio:.1f}x (ALTO)")
            elif ratio >= 2:
                score += 0.08
                evidence.append(f"volume_ratio={ratio:.1f}x (moderado)")
            else:
                evidence.append(f"volume_ratio={ratio:.1f}x (normal)")
        else:
            evidence.append("volume: dados insuficientes")

        # RSI (peso 20%)
        if signal.rsi_14 is not None:
            available += 1
            if signal.rsi_14 >= 85:
                score += 0.20
                evidence.append(f"RSI={signal.rsi_14:.0f} (sobrecomprado extremo)")
            elif signal.rsi_14 >= 70:
                score += 0.10
                evidence.append(f"RSI={signal.rsi_14:.0f} (sobrecomprado)")
            else:
                evidence.append(f"RSI={signal.rsi_14:.0f} (normal)")
        else:
            evidence.append("RSI: indisponível")

        # Sinais externos (peso 15%)
        if signal.external_signals:
            available += 1
            score += min(0.15, len(signal.external_signals) * 0.05)
            evidence.append(f"{len(signal.external_signals)} sinal(is) externo(s)")

        score = _clamp(score)
        confidence = min(1.0, available / 3)
        phase = self._classify_phase(score, signal)

        if score >= 0.60:
            evidence.append("⚠ Alta probabilidade de pump-and-dump")

        return PumpDumpResult(round(score, 3), phase, evidence, round(confidence, 2))

    def _classify_phase(self, score: float, signal: SignalInput) -> str:
        if score < 0.20:
            return "INCERTO"
        if signal.price is not None and signal.prev_close is not None and signal.prev_close > 0:
            change = _simple_return(signal.price, signal.prev_close) * 100
            if change >= 50 and score >= 0.60:
                return "PUMP"
            if change <= -20 and score >= 0.40:
                return "DUMP"
            if 10 <= change < 50 and score >= 0.30:
                return "ACUMULAÇÃO"
        return "INCERTO"
