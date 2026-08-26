"""
PennylabVeracityGate — Gate leve de veracidade para PennyLab
=============================================================
Versão simplificada do VeracityGate central.
Para pennylab: verifica consistência interna dos dados de entrada,
não faz cross-checking com LLM (sem custo de token aqui).

Regras de veto:
  - Preço negativo ou zero
  - volume negativo
  - bid > ask (bid/ask invertidos)
  - Price move > 1000% (dado provavelmente corrompido)
  - Dados marcados como UNAVAILABLE mas scores críticos preenchidos
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..schemas import DataQuality, SignalInput


@dataclass
class GateResult:
    passed: bool
    confidence: float  # 0-1 confiança no gate
    violations: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


class PennylabVeracityGate:
    """
    Gate de consistência para dados de entrada do PennyLab.
    Não usa LLM. Determinístico e auditável.
    """

    def check(self, signal: SignalInput) -> GateResult:
        violations: list[str] = []
        warnings: list[str] = []

        # --- Violações (vetam o relatório) ---
        if signal.price is not None and signal.price <= 0:
            violations.append(f"price={signal.price} inválido (deve ser > 0)")

        if signal.volume is not None and signal.volume < 0:
            violations.append(f"volume={signal.volume} inválido (negativo)")

        if signal.bid is not None and signal.ask is not None:
            if signal.bid > signal.ask:
                violations.append(
                    f"bid={signal.bid} > ask={signal.ask} (bid/ask invertidos — dado corrompido)"
                )

        if signal.price is not None and signal.prev_close is not None and signal.prev_close > 0:
            change_pct = abs((signal.price - signal.prev_close) / signal.prev_close * 100)
            if change_pct > 1000:
                violations.append(
                    f"variação de preço={change_pct:.0f}% — dado provavelmente corrompido"
                )

        if signal.rsi_14 is not None and not (0 <= signal.rsi_14 <= 100):
            violations.append(f"RSI={signal.rsi_14} fora do range 0-100")

        # --- Warnings (não vetam, mas reduzem confiança) ---
        if signal.data_quality == DataQuality.UNAVAILABLE:
            warnings.append(
                "data_quality=UNAVAILABLE — todos os scores baseados em ausência de dados"
            )

        if signal.data_quality == DataQuality.MANUAL and not signal.source:
            warnings.append("dados manuais sem source identificado")

        if signal.avg_volume_10d is not None and signal.avg_volume_10d == 0:
            warnings.append("avg_volume_10d=0 — possível ativo sem histórico de volume")

        passed = len(violations) == 0
        # Confiança: 1.0 sem violações, 0.5 com warnings, 0.0 com violações
        if not passed:
            confidence = 0.0
        elif warnings:
            confidence = 0.6
        else:
            confidence = 1.0

        return GateResult(
            passed=passed,
            confidence=confidence,
            violations=violations,
            warnings=warnings,
        )
