"""Crisis models — 12 financial systemic risk sensors (pure numpy/scipy).

BaseCrisisModel provides shared helpers to eliminate duplicated boilerplate
across all 12 sensors: insufficient_data pattern + status classification.
"""

from ..contracts.schemas import CrisisInput, SensorResult


class BaseCrisisModel:
    """Shared base for all crisis sensors — eliminates 120+ duplicated lines.

    Each subclass only implements evaluate() with its unique algorithm.
    Boilerplate (insufficient_data, status classification, SensorResult
    construction) is handled here.
    """

    def evaluate(self, input_data: CrisisInput) -> SensorResult:
        raise NotImplementedError("Subclass must implement evaluate()")

    @staticmethod
    def _insufficient_data(sensor_name: str, explanation: str = "") -> SensorResult:
        """Factory for the repeated 'insufficient data' return pattern."""
        return SensorResult(
            sensor_name=sensor_name,
            score=0.0,
            confidence=0.0,
            status="insufficient_data",
            explanation=explanation or "Dados insuficientes para calculo do sensor.",
        )

    @staticmethod
    def _classify_status(score: float) -> str:
        """Shared score-to-status mapping used by 4+ models.

        Normalized 0-1 scores:
          > 0.75 → crisis
          > 0.50 → stress
          > 0.25 → warning
          else   → ok
        """
        if score > 0.75:
            return "crisis"
        elif score > 0.50:
            return "stress"
        elif score > 0.25:
            return "warning"
        return "ok"

    @staticmethod
    def _result(
        sensor_name: str,
        score: float,
        confidence: float,
        explanation: str,
        details: dict | None = None,
    ) -> SensorResult:
        """Factory for the repeated SensorResult return pattern with auto-classified status."""
        return SensorResult(
            sensor_name=sensor_name,
            score=round(score, 3),
            confidence=round(confidence, 3),
            status=BaseCrisisModel._classify_status(score),
            explanation=explanation,
            details=details or {},
        )

