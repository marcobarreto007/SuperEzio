"""
WhalePrintExpert — escala 0-1, usa mathcore.
=============================================================
Combina: float baixo + spike de volume + tamanho de mercado.
Uma baleia entra devagar, sobe o preço, distribui para varejo e sai.

Este expert identifica a "impressão digital" desse padrão.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..mathcore_adapter import _clamp
from ..schemas import SignalInput


@dataclass
class WhalePrintResult:
    score: float  # 0-1
    label: str
    evidence: list[str] = field(default_factory=list)
    confidence: float = 0.0


class WhalePrintExpert:
    """
    Detecta padrão de baleia: micro-float + volume spike + preço baixo.
    Não executa ordens. Apenas classifica e alerta.
    """

    def evaluate(self, signal: SignalInput) -> WhalePrintResult:
        evidence: list[str] = []
        components: list[float] = []
        available = 0

        # Float (peso 40%)
        if signal.shares_float is not None:
            available += 1
            if signal.shares_float < 5_000_000:
                score = 0.90
                evidence.append(f"float={signal.shares_float:,} (MICRO)")
            elif signal.shares_float < 20_000_000:
                score = 0.60
                evidence.append(f"float={signal.shares_float:,} (BAIXO)")
            else:
                score = 0.10
                evidence.append(f"float={signal.shares_float:,} (OK)")
            components.append(score * 0.40)
        else:
            evidence.append("float: indisponível")

        # Volume spike (peso 40%)
        if signal.volume is not None and signal.avg_volume_10d and signal.avg_volume_10d > 0:
            available += 1
            ratio = signal.volume / signal.avg_volume_10d
            if ratio >= 10:
                score = 0.90
            elif ratio >= 5:
                score = 0.65
            elif ratio >= 2:
                score = 0.30
            else:
                score = 0.05
            evidence.append(f"volume ratio={ratio:.1f}x")
            components.append(score * 0.40)
        else:
            evidence.append("volume spike: dados insuficientes")

        # Preço (peso 20%)
        if signal.price is not None:
            available += 1
            if signal.price < 1.0:
                score = 0.80
                evidence.append(f"price=${signal.price:.4f} (sub-penny)")
            elif signal.price < 5.0:
                score = 0.50
                evidence.append(f"price=${signal.price:.2f} (penny)")
            else:
                score = 0.10
                evidence.append(f"price=${signal.price:.2f} (não penny)")
            components.append(score * 0.20)
        else:
            evidence.append("price: indisponível")

        if not components:
            return WhalePrintResult(0.0, "INDISPONÍVEL", evidence, 0.0)

        total = _clamp(sum(components))
        confidence = available / 3

        if total >= 0.70:
            label = "FORTE"
        elif total >= 0.50:
            label = "PROVÁVEL"
        elif total >= 0.30:
            label = "POSSÍVEL"
        else:
            label = "IMPROVÁVEL"

        if label in ("FORTE", "PROVÁVEL"):
            evidence.append("⚠ Padrão de baleia detectado")

        return WhalePrintResult(round(total, 3), label, evidence, round(confidence, 2))
