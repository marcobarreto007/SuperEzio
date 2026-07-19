"""Explicit fixed-weight heuristic for concurrent credit and asset growth."""

from ..contracts.schemas import CrisisInput, SensorResult
from ..logic.normalization import clamp, percentile_rank
from . import BaseCrisisModel


class CreditAssetGrowthModel:
    """Stable import name; public result name states that this is a heuristic."""

    PUBLIC_NAME = "CreditAssetPercentileHeuristic"

    def evaluate(self, input_data: CrisisInput) -> SensorResult:
        credits = [
            item.credit_growth_yoy
            for item in input_data.observations
            if item.credit_growth_yoy is not None
        ]
        houses = [
            item.house_price_index
            for item in input_data.observations
            if item.house_price_index is not None
        ]
        equities = [
            item.equity_index for item in input_data.observations if item.equity_index is not None
        ]
        sample_size = min(len(credits), len(houses))
        as_of = input_data.observations[-1].date if input_data.observations else None
        horizon = f"current {input_data.frequency} percentile"
        if sample_size < 12:
            return BaseCrisisModel._insufficient_data(
                self.PUBLIC_NAME,
                "Credit/asset heuristic requires at least 12 credit and housing observations.",
                horizon=horizon,
                sample_size=sample_size,
                as_of=as_of,
            )

        credit_percentile = percentile_rank(credits, credits[-1])
        house_yoy = ((houses[-1] / houses[-12]) - 1.0) * 100.0 if houses[-12] > 0.0 else 0.0
        house_history = [
            ((houses[index] / houses[index - 12]) - 1.0) * 100.0
            for index in range(12, len(houses))
            if houses[index - 12] > 0.0
        ]
        house_percentile = percentile_rank(house_history, house_yoy) if house_history else 50.0
        equity_percentile = 0.0
        if len(equities) >= 12:
            equity_yoy = (
                ((equities[-1] / equities[-12]) - 1.0) * 100.0 if equities[-12] > 0.0 else 0.0
            )
            equity_history = [
                ((equities[index] / equities[index - 12]) - 1.0) * 100.0
                for index in range(12, len(equities))
                if equities[index - 12] > 0.0
            ]
            equity_percentile = (
                percentile_rank(equity_history, equity_yoy) if equity_history else 50.0
            )

        fixed_weight_score = (
            0.45 * credit_percentile + 0.35 * house_percentile + 0.20 * equity_percentile
        )
        if credit_percentile >= 90.0 and house_percentile >= 90.0:
            interaction = 30.0 if equity_percentile >= 90.0 else 20.0
        elif credit_percentile >= 75.0 and house_percentile >= 75.0:
            interaction = 10.0
        else:
            interaction = 0.0
        score = clamp(fixed_weight_score + interaction) / 100.0

        return SensorResult(
            sensor_name=self.PUBLIC_NAME,
            score=float(score),
            confidence=0.55,
            status="ok",
            explanation=(
                "Fixed-weight historical percentiles summarize concurrent credit and asset growth."
            ),
            method_kind="heuristic",
            horizon=horizon,
            sample_size=sample_size,
            as_of=as_of,
            calibration_status="not_calibrated",
            details={
                "credit_growth_percentile": credit_percentile,
                "house_growth_percentile": house_percentile,
                "equity_growth_percentile": equity_percentile,
                "interaction_bonus": interaction,
                "method_name": "fixed_weight_percentile_interaction_heuristic",
            },
        )
