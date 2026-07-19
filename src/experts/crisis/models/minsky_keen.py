"""Explicit fixed-weight private-debt fragility heuristic."""

from ..contracts.schemas import CrisisInput, SensorResult
from ..logic.normalization import clamp, percentile_rank
from . import BaseCrisisModel


class MinskyKeenModel:
    """Stable import name; no claim of estimating a Minsky/Keen dynamical model."""

    PUBLIC_NAME = "PrivateDebtFragilityHeuristic"

    def evaluate(self, input_data: CrisisInput) -> SensorResult:
        valid = [
            item
            for item in input_data.observations
            if item.credit_to_gdp is not None
            and item.gdp_growth_yoy is not None
            and item.policy_rate is not None
        ]
        as_of = valid[-1].date if valid else None
        horizon = f"current {input_data.frequency} fragility bucket"
        if len(valid) < 4:
            return BaseCrisisModel._insufficient_data(
                self.PUBLIC_NAME,
                "Debt fragility heuristic requires credit, GDP growth, and policy rate.",
                horizon=horizon,
                sample_size=len(valid),
                as_of=as_of,
            )

        latest = valid[-1]
        debt_values = [item.credit_to_gdp for item in valid]
        debt_score = percentile_rank(debt_values, latest.credit_to_gdp) / 100.0
        rate_score = min(1.0, max(0.0, latest.policy_rate / 5.0))
        growth_score = (
            1.0
            if latest.gdp_growth_yoy < 0.0
            else max(0.0, 1.0 - latest.gdp_growth_yoy * 0.20)
        )
        fragility = clamp(
            0.40 * debt_score + 0.30 * rate_score + 0.30 * growth_score,
            max_value=1.0,
        )
        state = "Ponzi-like" if fragility > 0.80 else "Speculative-like" if fragility > 0.50 else "Hedge-like"
        return SensorResult(
            sensor_name=self.PUBLIC_NAME,
            score=float(fragility),
            confidence=0.50,
            status="ok",
            explanation=(
                f"Fixed-weight debt/rate/growth fragility bucket is {state}; "
                "this is not a calibrated Minsky-Keen dynamical model."
            ),
            method_kind="heuristic",
            horizon=horizon,
            sample_size=len(valid),
            as_of=as_of,
            calibration_status="not_calibrated",
            details={
                "minsky_state": state,
                "components": {
                    "debt_percentile": debt_score,
                    "rate_pressure": rate_score,
                    "growth_slowdown": growth_score,
                },
                "method_name": "fixed_weight_private_debt_fragility_heuristic",
                "not_minsky_keen_dynamics": True,
            },
        )
