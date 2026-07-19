"""
MathcoreAdapter — Bridge para módulos matemáticos existentes
=============================================================
Reutiliza classify_alert_level do crisis sem duplicar lógica.
Se o módulo não estiver disponível, degrada graciosamente.

Escala unificada: 0-1.
"""

from __future__ import annotations

from typing import Dict

from core.math.utils import clamp as _clamp  # noqa: F401 (re-export)
from core.math.risk import simple_return as _simple_return  # noqa: F401 (re-export)

from .schemas import PennylabScores

# Tenta importar o scoring do crisis — sem crashar se ausente
try:
    from experts.crisis.logic.scoring import (
        classify_alert_level as _classify_alert,
    )

    _CRISIS_AVAILABLE = True
except ImportError:
    _CRISIS_AVAILABLE = False

    def _classify_alert(score: float) -> str:  # type: ignore[misc]
        """Score em escala 0-1."""
        if score < 0.25:
            return "green"
        elif score < 0.50:
            return "yellow"
        elif score < 0.75:
            return "red"
        return "black"


def score_to_alert(score: float) -> str:
    """Converte score 0-1 → green / yellow / red / black usando crisis."""
    if _CRISIS_AVAILABLE:
        return _classify_alert(score)
    return _classify_alert(score)


def build_mathcore_verdict(scores: PennylabScores) -> str:
    """
    Gera um veredicto textual baseado nos scores usando a mesma escala
    do crisis. Puramente determinístico — sem LLM aqui.
    """
    max_score = max(
        scores.whale_suspicion,
        scores.pump_probability,
        scores.trap_risk,
        scores.liquidity_risk,
    )
    alert = score_to_alert(max_score)

    components: Dict[str, str] = {
        "whale": score_to_alert(scores.whale_suspicion),
        "pump": score_to_alert(scores.pump_probability),
        "trap": score_to_alert(scores.trap_risk),
        "liquidity": score_to_alert(scores.liquidity_risk),
    }

    dominant = max(
        components,
        key=lambda k: getattr(
            scores,
            {
                "whale": "whale_suspicion",
                "pump": "pump_probability",
                "trap": "trap_risk",
                "liquidity": "liquidity_risk",
            }[k],
        ),
    )

    source_tag = "crisis" if _CRISIS_AVAILABLE else "builtin"
    return (
        f"[mathcore/{source_tag}] alert={alert} "
        f"dominant_risk={dominant} "
        f"whale={components['whale']} pump={components['pump']} "
        f"trap={components['trap']} liquidity={components['liquidity']}"
    )
