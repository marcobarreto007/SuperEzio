"""Housing price-to-rent/income percentile heuristic; not Shiller CAPE."""

from ..contracts.schemas import CrisisInput, SensorResult
from ..logic.normalization import percentile_rank
from . import BaseCrisisModel


class ShillerValuationModel:
    """Stable import name for an honestly named housing-percentile result."""

    PUBLIC_NAME = "HousingValuationPercentileHeuristic"

    def evaluate(self, input_data: CrisisInput) -> SensorResult:
        valid = [
            item
            for item in input_data.observations
            if item.house_price_index is not None
            and item.rent_index is not None
            and item.income_index is not None
            and item.rent_index > 0.0
            and item.income_index > 0.0
        ]
        as_of = valid[-1].date if valid else None
        horizon = f"current {input_data.frequency} valuation percentile"
        if len(valid) < 12:
            return BaseCrisisModel._insufficient_data(
                self.PUBLIC_NAME,
                "Housing valuation percentiles require 12 complete price/rent/income observations.",
                horizon=horizon,
                sample_size=len(valid),
                as_of=as_of,
            )

        price_to_rent = [item.house_price_index / item.rent_index for item in valid]
        price_to_income = [item.house_price_index / item.income_index for item in valid]
        rent_percentile = percentile_rank(price_to_rent, price_to_rent[-1])
        income_percentile = percentile_rank(price_to_income, price_to_income[-1])
        average_percentile = (rent_percentile + income_percentile) / 2.0
        if average_percentile > 90.0:
            score = 1.0
        elif average_percentile > 75.0:
            score = 0.75
        else:
            score = average_percentile / 100.0
        return SensorResult(
            sensor_name=self.PUBLIC_NAME,
            score=float(score),
            confidence=0.55,
            status="ok",
            explanation=(
                f"Housing price-to-rent/income historical percentile is "
                f"{average_percentile:.1f}; this is not Shiller CAPE."
            ),
            method_kind="heuristic",
            horizon=horizon,
            sample_size=len(valid),
            as_of=as_of,
            calibration_status="not_calibrated",
            details={
                "price_to_rent_pct": rent_percentile,
                "price_to_income_pct": income_percentile,
                "method_name": "housing_ratio_historical_percentile_heuristic",
                "not_shiller_cape": True,
            },
        )
