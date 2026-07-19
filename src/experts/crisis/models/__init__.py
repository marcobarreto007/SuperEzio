"""Crisis models — 12 financial systemic risk sensors (pure numpy/scipy).

BaseCrisisModel provides shared helpers to eliminate duplicated boilerplate
across all 12 sensors: insufficient-data and result-construction patterns.
"""

from ..contracts.schemas import CrisisInput, SensorResult


class BaseCrisisModel:
    """Shared base for all crisis sensors — eliminates 120+ duplicated lines.

    Each subclass only implements evaluate() with its unique algorithm.
    Boilerplate (insufficient_data and SensorResult
    construction) is handled here.
    """

    def evaluate(self, input_data: CrisisInput) -> SensorResult:
        raise NotImplementedError("Subclass must implement evaluate()")

    @staticmethod
    def _insufficient_data(
        sensor_name: str,
        explanation: str = "",
        *,
        horizon: str | None = None,
        sample_size: int = 0,
        as_of: str | None = None,
    ) -> SensorResult:
        """Factory for the repeated 'insufficient data' return pattern."""
        return SensorResult(
            sensor_name=sensor_name,
            score=0.0,
            confidence=0.0,
            status="insufficient_data",
            explanation=explanation or "Dados insuficientes para calculo do sensor.",
            method_kind="unavailable",
            horizon=horizon,
            sample_size=sample_size,
            as_of=as_of,
            calibration_status="unavailable",
        )

    @staticmethod
    def _result(
        sensor_name: str,
        score: float,
        confidence: float,
        explanation: str,
        details: dict | None = None,
        *,
        method_kind: str = "heuristic",
        horizon: str | None = None,
        sample_size: int = 0,
        as_of: str | None = None,
        calibration_status: str = "not_calibrated",
    ) -> SensorResult:
        """Factory for the repeated SensorResult return pattern with auto-classified status."""
        return SensorResult(
            sensor_name=sensor_name,
            score=round(score, 3),
            confidence=round(confidence, 3),
            status="ok",
            explanation=explanation,
            method_kind=method_kind,
            horizon=horizon,
            sample_size=sample_size,
            as_of=as_of,
            calibration_status=calibration_status,
            details=details or {},
        )
