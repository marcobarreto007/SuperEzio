"""Explicit historical-percentile heuristic for debt-service burden."""

from ..contracts.schemas import CrisisInput, SensorResult
from ..logic.normalization import percentile_rank
from . import BaseCrisisModel


class DebtServiceRatioModel:
    PUBLIC_NAME = "DebtServicePercentileHeuristic"

    def evaluate(self, input_data: CrisisInput) -> SensorResult:
        values = [
            item.debt_service_ratio
            for item in input_data.observations
            if item.debt_service_ratio is not None
        ]
        as_of = input_data.observations[-1].date if input_data.observations else None
        horizon = f"current {input_data.frequency} percentile"
        if len(values) < 12:
            return BaseCrisisModel._insufficient_data(
                self.PUBLIC_NAME,
                "Debt-service percentile requires at least 12 observations.",
                horizon=horizon,
                sample_size=len(values),
                as_of=as_of,
            )

        current = values[-1]
        percentile = percentile_rank(values, current)
        if percentile < 50.0:
            score = 0.20
        elif percentile < 75.0:
            score = 0.50
        elif percentile < 90.0:
            score = 0.80
        else:
            score = 1.0
        return SensorResult(
            sensor_name=self.PUBLIC_NAME,
            score=score,
            confidence=0.55,
            status="ok",
            explanation=(
                f"Debt-service ratio is at historical percentile {percentile:.1f}; "
                "risk buckets are fixed heuristic thresholds."
            ),
            method_kind="heuristic",
            horizon=horizon,
            sample_size=len(values),
            as_of=as_of,
            calibration_status="not_calibrated",
            details={
                "current_dsr": current,
                "percentile": percentile,
                "method_name": "historical_percentile_threshold_heuristic",
            },
        )
