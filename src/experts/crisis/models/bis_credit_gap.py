"""BIS-style credit-to-GDP gap using the declared-frequency HP filter."""

import numpy as np
from scipy.sparse import diags, eye
from scipy.sparse.linalg import spsolve

from ..contracts.schemas import CrisisInput, SensorResult
from . import BaseCrisisModel


class BISCreditGapModel:
    MIN_OBSERVATIONS = 12
    HP_LAMBDA = {"annual": 1600.0, "quarterly": 400_000.0, "monthly": 32_400_000.0}

    def evaluate(self, input_data: CrisisInput) -> SensorResult:
        valid = [item for item in input_data.observations if item.credit_to_gdp is not None]
        values = np.asarray([item.credit_to_gdp for item in valid], dtype=float)
        as_of = valid[-1].date if valid else None
        horizon = f"current {input_data.frequency} credit gap"
        if len(values) < self.MIN_OBSERVATIONS:
            return BaseCrisisModel._insufficient_data(
                self.__class__.__name__,
                f"Credit gap requires {self.MIN_OBSERVATIONS} credit-to-GDP observations.",
                horizon=horizon,
                sample_size=len(values),
                as_of=as_of,
            )
        smoothing = self.HP_LAMBDA.get(input_data.frequency)
        if smoothing is None:
            return BaseCrisisModel._insufficient_data(
                self.__class__.__name__,
                "BIS credit gap supports annual, quarterly, or monthly macro frequency only.",
                horizon=horizon,
                sample_size=len(values),
                as_of=as_of,
            )
        # Exact Hodrick-Prescott penalized least-squares solution:
        # argmin_tau ||y-tau||^2 + lambda ||D2 tau||^2.
        second_difference = diags(
            [np.ones(len(values) - 2), -2.0 * np.ones(len(values) - 2), np.ones(len(values) - 2)],
            [0, 1, 2],
            shape=(len(values) - 2, len(values)),
            format="csc",
        )
        system = eye(len(values), format="csc") + smoothing * (
            second_difference.T @ second_difference
        )
        trend = spsolve(system, values)
        gap = float(values[-1] - trend[-1])
        if gap <= 0.0:
            score = 0.0
        elif gap <= 2.0:
            score = 0.25
        elif gap <= 10.0:
            score = 0.50 + ((gap - 2.0) / 8.0) * 0.25
        else:
            score = 0.75 + min(((gap - 10.0) / 10.0) * 0.25, 0.25)

        return SensorResult(
            sensor_name=self.__class__.__name__,
            score=float(score),
            confidence=0.80,
            status="ok",
            explanation=f"BIS-style HP-filter credit-to-GDP gap is {gap:.2f} percentage points.",
            method_kind="econometric_model",
            horizon=horizon,
            sample_size=len(values),
            as_of=as_of,
            calibration_status="not_applicable",
            details={
                "current_gap": gap,
                "current_ratio": float(values[-1]),
                "hp_lambda": smoothing,
                "implementation": "two_sided_hp_filter",
                "degraded": False,
            },
        )
