"""Rolling equity z-score heuristic; not an IMF mispricing model."""

import numpy as np

from ..contracts.schemas import CrisisInput, SensorResult
from ..logic.normalization import zscore_to_risk
from . import BaseCrisisModel


class IMFMispricingModel:
    """Stable import name for the honestly named public heuristic result."""

    PUBLIC_NAME = "EquityRollingZScoreHeuristic"
    WINDOW = 24

    def evaluate(self, input_data: CrisisInput) -> SensorResult:
        values = np.asarray(
            [
                item.equity_index
                for item in input_data.observations
                if item.equity_index is not None
            ],
            dtype=float,
        )
        as_of = input_data.observations[-1].date if input_data.observations else None
        horizon = f"current {input_data.frequency} deviation"
        if len(values) < self.WINDOW + 2:
            return BaseCrisisModel._insufficient_data(
                self.PUBLIC_NAME,
                f"Rolling z-score requires at least {self.WINDOW + 2} equity observations.",
                horizon=horizon,
                sample_size=len(values),
                as_of=as_of,
            )

        residuals = []
        for index in range(self.WINDOW, len(values)):
            trailing_mean = float(np.mean(values[index - self.WINDOW : index]))
            if trailing_mean <= 0.0:
                continue
            residuals.append((float(values[index]) - trailing_mean) / trailing_mean)
        calibration = np.asarray(residuals[:-1])
        calibration_std = float(np.std(calibration))
        if len(residuals) < 3 or calibration_std <= 1e-12:
            return BaseCrisisModel._insufficient_data(
                self.PUBLIC_NAME,
                "Rolling z-score residual variance is not identifiable.",
                horizon=horizon,
                sample_size=len(values),
                as_of=as_of,
            )
        residual_array = np.asarray(residuals)
        z_score = float((residual_array[-1] - np.mean(calibration)) / calibration_std)
        score = zscore_to_risk(z_score) / 100.0
        return SensorResult(
            sensor_name=self.PUBLIC_NAME,
            score=float(score),
            confidence=0.45,
            status="ok",
            explanation=(
                f"Rolling 24-observation equity residual z-score is {z_score:.2f}; "
                "this is not an IMF structural valuation model."
            ),
            method_kind="heuristic",
            horizon=horizon,
            sample_size=len(values),
            as_of=as_of,
            calibration_status="not_calibrated",
            details={
                "z_score": z_score,
                "method_name": "rolling_mean_residual_zscore_heuristic",
                "not_imf_model": True,
            },
        )
