"""
VolumeSpikeExpert — escala 0-1, usa mathcore.
================================================================
Detecta spikes anômalos de volume. Indica acúmulo oculto de posição,
atividade de baleia ou distribuição (venda) disfarçada.

Saída: enriquece evidências do SignalInput, não modifica dados brutos.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..schemas import SignalInput


@dataclass
class VolumeSpikeResult:
    score: float  # 0-1
    ratio: float
    label: str
    evidence: list[str]
    confidence: float


class VolumeSpikeExpert:
    def evaluate(self, signal: SignalInput) -> VolumeSpikeResult:
        if signal.volume is None or signal.avg_volume_10d is None:
            return VolumeSpikeResult(
                0.0, 0.0, "INDISPONÍVEL", ["volume ou avg_volume_10d ausente"], 0.0
            )
        if signal.avg_volume_10d == 0:
            return VolumeSpikeResult(0.0, 0.0, "INDISPONÍVEL", ["avg_volume_10d=0"], 0.3)

        ratio = signal.volume / signal.avg_volume_10d
        label, score = self._classify(ratio)

        evidence = [
            f"volume={signal.volume:,} avg10d={signal.avg_volume_10d:,} ratio={ratio:.2f}x → {label}"
        ]
        if label in ("ALTO", "EXTREMO"):
            evidence.append("⚠ Volume anômalo — possível acúmulo ou distribuição")

        return VolumeSpikeResult(score, ratio, label, evidence, 1.0)

    def _classify(self, ratio: float) -> tuple[str, float]:
        if ratio >= 10.0:
            return "EXTREMO", 0.90
        if ratio >= 5.0:
            return "ALTO", 0.70
        if ratio >= 2.0:
            return "MODERADO", 0.40
        return "NORMAL", 0.10
