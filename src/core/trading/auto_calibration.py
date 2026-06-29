"""Auto-Calibration - Calibração automática de parâmetros baseado em performance.

Bob ajusta seus parâmetros de trading automaticamente baseado em:
- Win rate recente
- Drawdown atual
- Volatilidade do mercado
- Tamanho de posição ideal

Parâmetros calibrados:
- BUY_CONFIDENCE_THRESHOLD
- MAX_POSITION_PCT
- STOP_LOSS_PCT
- TAKE_PROFIT_RATIO
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

DEFAULT_CALIBRATION_LOG_PATH = (
    Path(__file__).resolve().parent.parent.parent.parent / "data" / "calibration_log.jsonl"
)


class CalibrationAction(Enum):
    """Tipos de ação de calibração."""

    INCREASE = "increase"
    DECREASE = "decrease"
    HOLD = "hold"
    UPGRADE = "upgrade"  # Mudança significativa


@dataclass
class ParameterRange:
    """Range permitido para um parâmetro."""

    param_name: str
    min_value: float
    max_value: float
    current_value: float
    default_value: float
    unit: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "param_name": self.param_name,
            "min_value": self.min_value,
            "max_value": self.max_value,
            "current_value": self.current_value,
            "default_value": self.default_value,
            "unit": self.unit,
        }


@dataclass
class CalibrationEvent:
    """Um evento de calibração."""

    event_id: str
    timestamp: str
    param_name: str
    old_value: float
    new_value: float
    action: CalibrationAction
    reason: str
    context: dict[str, Any] = field(default_factory=dict)
    applied: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "timestamp": self.timestamp,
            "param_name": self.param_name,
            "old_value": self.old_value,
            "new_value": self.new_value,
            "action": self.action.value,
            "reason": self.reason,
            "context": self.context,
            "applied": self.applied,
        }


@dataclass
class CalibrationReport:
    """Relatório de calibração."""

    timestamp: str
    parameters: dict[str, ParameterRange]
    recommended_changes: list[CalibrationEvent]
    performance_metrics: dict[str, Any]
    overall_health: str  # "healthy" | "caution" | "danger"

    def to_dict(self) -> dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "parameters": {k: v.to_dict() for k, v in self.parameters.items()},
            "recommended_changes": [c.to_dict() for c in self.recommended_changes],
            "performance_metrics": self.performance_metrics,
            "overall_health": self.overall_health,
        }


class AutoCalibrator:
    """Calibrador automático de parâmetros do Bob."""

    def __init__(
        self,
        log_path: Path | None = None,
        auto_apply: bool = False,  # Se True, aplica mudanças automaticamente
    ):
        self._log_path = log_path or DEFAULT_CALIBRATION_LOG_PATH
        self._log_path.parent.mkdir(parents=True, exist_ok=True)

        self._auto_apply = auto_apply
        self._history: list[CalibrationEvent] = []

        # Parâmetros configuráveis (vals padrão)
        self._parameters: dict[str, ParameterRange] = {
            # Thresholds
            "BUY_CONFIDENCE_THRESHOLD": ParameterRange(
                param_name="BUY_CONFIDENCE_THRESHOLD",
                min_value=50.0,
                max_value=85.0,
                current_value=float(os.getenv("SUPEREZIO_BUY_CONFIDENCE_THRESHOLD", "65")),
                default_value=65.0,
                unit="%",
            ),
            "STRONG_CONFIDENCE_THRESHOLD": ParameterRange(
                param_name="STRONG_CONFIDENCE_THRESHOLD",
                min_value=70.0,
                max_value=95.0,
                current_value=float(os.getenv("SUPEREZIO_STRONG_CONFIDENCE_THRESHOLD", "80")),
                default_value=80.0,
                unit="%",
            ),
            # Position sizing
            "MAX_POSITION_PCT": ParameterRange(
                param_name="MAX_POSITION_PCT",
                min_value=1.0,
                max_value=25.0,
                current_value=float(os.getenv("SUPEREZIO_MAX_POSITION_PCT", "10")),
                default_value=10.0,
                unit="%",
            ),
            "MAX_RISK_PER_TRADE_PCT": ParameterRange(
                param_name="MAX_RISK_PER_TRADE_PCT",
                min_value=0.5,
                max_value=5.0,
                current_value=float(os.getenv("SUPEREZIO_MAX_RISK_PER_TRADE_PCT", "2")),
                default_value=2.0,
                unit="%",
            ),
            # Risk management
            "DEFAULT_STOP_LOSS_PCT": ParameterRange(
                param_name="DEFAULT_STOP_LOSS_PCT",
                min_value=1.0,
                max_value=10.0,
                current_value=float(os.getenv("SUPEREZIO_DEFAULT_STOP_LOSS_PCT", "3")),
                default_value=3.0,
                unit="%",
            ),
            "DEFAULT_TAKE_PROFIT_RATIO": ParameterRange(
                param_name="DEFAULT_TAKE_PROFIT_RATIO",
                min_value=1.0,
                max_value=5.0,
                current_value=float(os.getenv("SUPEREZIO_DEFAULT_TAKE_PROFIT_RATIO", "2")),
                default_value=2.0,
                unit="x",
            ),
        }

    def _generate_event_id(self) -> str:
        """Gera ID único para evento."""
        return f"cal_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}_{len(self._history)}"

    def _save_event(self, event: CalibrationEvent) -> None:
        """Salva evento no disco (append-only)."""
        with open(self._log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(event.to_dict(), ensure_ascii=False) + "\n")

    def get_parameter(self, name: str) -> ParameterRange | None:
        """Retorna parâmetro por nome."""
        return self._parameters.get(name)

    def update_parameter(self, name: str, new_value: float) -> bool:
        """Atualiza valor de um parâmetro (sem persistir em env).

        Returns:
            True se atualizado, False se inválido
        """
        param = self._parameters.get(name)
        if not param:
            logger.warning("Parameter not found: %s", name)
            return False

        if not (param.min_value <= new_value <= param.max_value):
            logger.warning(
                "Value %.2f out of range [%.1f, %.1f] for %s",
                new_value,
                param.min_value,
                param.max_value,
                name,
            )
            return False

        param.current_value = new_value
        logger.info("Parameter %s updated to %.2f", name, new_value)
        return True

    def _calibrate_confidence_threshold(
        self,
        win_rate: float,
        avg_confidence: float,
        calibration_gap: float,
    ) -> CalibrationEvent | None:
        """Calibra BUY_CONFIDENCE_THRESHOLD baseado em win rate.

        Lógica:
        - Se win_rate muito menor que avg_confidence → Bob está overconfident → aumentar threshold
        - Se win_rate muito maior que avg_confidence → Bob está underconfident → diminuir threshold
        """
        param = self._parameters["BUY_CONFIDENCE_THRESHOLD"]
        old_value = param.current_value

        # Gap entre confiança declarada e real
        if calibration_gap >= 0.20:  # Overconfident
            # Aumentar threshold em 5%
            new_value = min(param.max_value, old_value + 5)
            action = CalibrationAction.INCREASE
            reason = (
                f"Bob is overconfident: avg_confidence={avg_confidence:.1%} vs "
                f"win_rate={win_rate:.1%}. Increasing BUY_CONFIDENCE_THRESHOLD "
                f"from {old_value:.1f}% to {new_value:.1f}%."
            )
        elif calibration_gap <= -0.20:  # Underconfident
            # Diminuir threshold em 3%
            new_value = max(param.min_value, old_value - 3)
            action = CalibrationAction.DECREASE
            reason = (
                f"Bob is underconfident: avg_confidence={avg_confidence:.1%} vs "
                f"win_rate={win_rate:.1%}. Decreasing BUY_CONFIDENCE_THRESHOLD "
                f"from {old_value:.1f}% to {new_value:.1f}%."
            )
        else:  # Calibrado
            return None

        if abs(new_value - old_value) < 0.1:  # Mudança muito pequena
            return None

        event = CalibrationEvent(
            event_id=self._generate_event_id(),
            timestamp=datetime.now(timezone.utc).isoformat(),
            param_name="BUY_CONFIDENCE_THRESHOLD",
            old_value=old_value,
            new_value=new_value,
            action=action,
            reason=reason,
            context={
                "win_rate": win_rate,
                "avg_confidence": avg_confidence,
                "calibration_gap": calibration_gap,
            },
        )

        return event

    def _calibrate_position_sizing(
        self,
        drawdown_pct: float,
        recent_loss_streak: int,
    ) -> CalibrationEvent | None:
        """Calibra MAX_POSITION_PCT baseado em drawdown.

        Lógica:
        - Drawdown > 10% → reduzir position size
        - Drawdown > 20% → reduzir significativamente
        - Loss streak → reduzir temporariamente
        """
        param = self._parameters["MAX_POSITION_PCT"]
        old_value = param.current_value

        new_value = old_value
        action = CalibrationAction.HOLD

        if drawdown_pct > 20.0:
            # Reduzir drasticamente
            new_value = max(param.min_value, old_value * 0.5)
            action = CalibrationAction.DECREASE
            reason = f"Severe drawdown ({drawdown_pct:.1f}%). Halving position size."
        elif drawdown_pct > 10.0:
            # Reduzir moderadamente
            new_value = max(param.min_value, old_value * 0.8)
            action = CalibrationAction.DECREASE
            reason = f"High drawdown ({drawdown_pct:.1f}%). Reducing position size by 20%."
        elif recent_loss_streak >= 3:
            # Reduzir temporariamente
            new_value = max(param.min_value, old_value * 0.7)
            action = CalibrationAction.DECREASE
            reason = f"Loss streak of {recent_loss_streak}. Reducing position size temporarily."
        elif drawdown_pct < -5.0:  # Novo high
            # Aumentar modestamente
            new_value = min(param.max_value, old_value * 1.1)
            action = CalibrationAction.INCREASE
            reason = "New equity high. Increasing position size modestly (+10%)."

        if abs(new_value - old_value) < 0.1:
            return None

        event = CalibrationEvent(
            event_id=self._generate_event_id(),
            timestamp=datetime.now(timezone.utc).isoformat(),
            param_name="MAX_POSITION_PCT",
            old_value=old_value,
            new_value=new_value,
            action=action,
            reason=reason,
            context={
                "drawdown_pct": drawdown_pct,
                "loss_streak": recent_loss_streak,
            },
        )

        return event

    def _calibrate_stop_loss(
        self,
        avg_stop_hit_rate: float,  # % de trades que hitaram stop
        recent_volatility: float,  # Volatilidade recente
    ) -> CalibrationEvent | None:
        """Calibra DEFAULT_STOP_LOSS_PCT baseado em stop hit rate e volatilidade.

        Lógica:
        - Stop hit rate muito alto (> 60%) → stop muito apertado → aumentar
        - Stop hit rate muito baixo (< 20%) → stop muito largo → diminuir
        - Volatilidade alta → aumentar stop
        """
        param = self._parameters["DEFAULT_STOP_LOSS_PCT"]
        old_value = param.current_value

        new_value = old_value
        action = CalibrationAction.HOLD

        if avg_stop_hit_rate > 0.60:  # Stops sendo muito acionados
            # Aumentar stop
            new_value = min(param.max_value, old_value + 0.5)
            action = CalibrationAction.INCREASE
            reason = f"Stop hit rate {avg_stop_hit_rate:.1%} too high. Widening stops."
        elif avg_stop_hit_rate < 0.20 and recent_volatility < 0.02:
            # Stop muito largo em mercado calmo
            new_value = max(param.min_value, old_value - 0.5)
            action = CalibrationAction.DECREASE
            reason = f"Stop hit rate {avg_stop_hit_rate:.1%} low in calm market. Tightening stops."
        elif recent_volatility > 0.03:  # Mercado volátil
            # Aumentar stop temporariamente
            new_value = min(param.max_value, old_value + 0.5)
            action = CalibrationAction.INCREASE
            reason = f"High volatility ({recent_volatility:.2%}). Widening stops temporarily."

        if abs(new_value - old_value) < 0.1:
            return None

        event = CalibrationEvent(
            event_id=self._generate_event_id(),
            timestamp=datetime.now(timezone.utc).isoformat(),
            param_name="DEFAULT_STOP_LOSS_PCT",
            old_value=old_value,
            new_value=new_value,
            action=action,
            reason=reason,
            context={
                "stop_hit_rate": avg_stop_hit_rate,
                "volatility": recent_volatility,
            },
        )

        return event

    def run_calibration(
        self,
        performance_metrics: dict[str, Any],
        apply: bool | None = None,
    ) -> CalibrationReport:
        """Executa ciclo completo de calibração.

        Args:
            performance_metrics: Métricas de performance recentes
            apply: Se None, usa self._auto_apply

        Returns:
            Relatório de calibração com mudanças recomendadas/aplicadas
        """
        should_apply = apply if apply is not None else self._auto_apply

        recommended_changes: list[CalibrationEvent] = []

        # Extrair métricas
        win_rate = performance_metrics.get("win_rate", 0.5)
        avg_confidence = performance_metrics.get("avg_confidence", 0.65)
        calibration_gap = performance_metrics.get("calibration_gap", 0.0)
        drawdown_pct = performance_metrics.get("drawdown_pct", 0.0)
        recent_loss_streak = performance_metrics.get("recent_loss_streak", 0)
        avg_stop_hit_rate = performance_metrics.get("stop_hit_rate", 0.4)
        recent_volatility = performance_metrics.get("volatility", 0.02)

        # Calibrar cada parâmetro
        event = self._calibrate_confidence_threshold(win_rate, avg_confidence, calibration_gap)
        if event:
            recommended_changes.append(event)

        event = self._calibrate_position_sizing(drawdown_pct, recent_loss_streak)
        if event:
            recommended_changes.append(event)

        event = self._calibrate_stop_loss(avg_stop_hit_rate, recent_volatility)
        if event:
            recommended_changes.append(event)

        # Aplicar mudanças se solicitado
        for event in recommended_changes:
            event.applied = False
            if should_apply:
                if self.update_parameter(event.param_name, event.new_value):
                    event.applied = True
                    self._history.append(event)
                    self._save_event(event)

        # Calcular health score
        if drawdown_pct > 20.0 or recent_loss_streak >= 5:
            overall_health = "danger"
        elif drawdown_pct > 10.0 or recent_loss_streak >= 3:
            overall_health = "caution"
        else:
            overall_health = "healthy"

        report = CalibrationReport(
            timestamp=datetime.now(timezone.utc).isoformat(),
            parameters=self._parameters,
            recommended_changes=recommended_changes,
            performance_metrics=performance_metrics,
            overall_health=overall_health,
        )

        logger.info(
            "Calibration complete: %d changes, health=%s",
            len(recommended_changes),
            overall_health,
        )

        return report

    def get_current_config(self) -> dict[str, float]:
        """Retorna configuração atual dos parâmetros."""
        return {name: param.current_value for name, param in self._parameters.items()}

    def render_for_bob(self, max_chars: int = 800) -> str:
        """Renderiza configuração atual para o prompt do Bob."""
        lines = [
            "\n=== CALIBRAÇÃO ATUAL ===",
        ]

        for param_name, param in self._parameters.items():
            unit = param.unit if param.unit else ""
            lines.append(
                f"- {param_name}: {param.current_value:.1f}{unit} "
                f"(range: {param.min_value:.1f}-{param.max_value:.1f})"
            )

        # Últimas calibrações
        if self._history:
            lines.append("\nÚltimas calibrações:")
            for event in list(reversed(self._history))[:3]:
                lines.append(
                    f"- {event.param_name}: {event.action.value} {event.old_value:.1f} → {event.new_value:.1f}"
                )

        lines.append("=== FIM DA CALIBRAÇÃO ===\n")

        result = "\n".join(lines)
        if len(result) > max_chars:
            result = result[:max_chars] + "\n..."

        return result

    def reset_to_defaults(self) -> dict[str, float]:
        """Reseta todos os parâmetros para valores padrão."""
        reset = {}
        for name, param in self._parameters.items():
            param.current_value = param.default_value
            reset[name] = param.default_value

        logger.info("All parameters reset to defaults")
        return reset


# Singleton
_auto_calibrator: AutoCalibrator | None = None


def get_auto_calibrator() -> AutoCalibrator:
    """Retorna singleton de AutoCalibrator."""
    global _auto_calibrator
    if _auto_calibrator is None:
        _auto_calibrator = AutoCalibrator()
        logger.info("AutoCalibrator initialized")
    return _auto_calibrator


if __name__ == "__main__":
    # Test mode
    calibrator = get_auto_calibrator()

    # Simular métricas de performance
    metrics = {
        "win_rate": 0.45,
        "avg_confidence": 0.70,
        "calibration_gap": 0.25,
        "drawdown_pct": 8.0,
        "recent_loss_streak": 2,
        "stop_hit_rate": 0.55,
        "volatility": 0.025,
    }

    report = calibrator.run_calibration(metrics)

    print("Calibration Report:")
    print(f"Health: {report.overall_health}")
    print(f"Changes: {len(report.recommended_changes)}")

    for change in report.recommended_changes:
        print(f"\n{change.param_name}:")
        print(f"  {change.old_value:.1f} → {change.new_value:.1f}")
        print(f"  {change.reason}")

    print(f"\n{calibrator.render_for_bob()}")
