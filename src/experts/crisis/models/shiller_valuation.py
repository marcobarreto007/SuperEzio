"""
Shiller Valuation Sensor.
"""

from ..contracts.schemas import CrisisInput, SensorResult
from . import BaseCrisisModel
from ..logic.normalization import percentile_rank


class ShillerValuationModel:
    def evaluate(self, input_data: CrisisInput) -> SensorResult:
        # We need house, rent, income to compute real ratios
        valid_obs = [
            o
            for o in input_data.observations
            if o.house_price_index and o.rent_index and o.income_index
        ]

        if len(valid_obs) < 12:
            return BaseCrisisModel._insufficient_data(
                self.__class__.__name__,
                "Faltam dados suficientes de House Price, Rent ou Income para cálculo Shiller.",
            )

        p_to_rent = [o.house_price_index / o.rent_index for o in valid_obs]
        p_to_inc = [o.house_price_index / o.income_index for o in valid_obs]

        # percentile_rank() returns 0-100 (see its docstring); avg_pct stays
        # on that scale for the threshold checks below (matches the model's
        # original intent), but score/confidence in SensorResult must be
        # 0-1 to match every other crisis model's contract (crisis.py's
        # aggregator averages r["score"]/r["confidence"] assuming 0-1, then
        # multiplies by 100 once — a 0-100 score here doubled the scale.
        # See docs/audit/phase9_parallel_fixes_and_critical_findings.md).
        pr_pct = percentile_rank(p_to_rent, p_to_rent[-1])
        pi_pct = percentile_rank(p_to_inc, p_to_inc[-1])

        avg_pct = (pr_pct + pi_pct) / 2.0

        if avg_pct > 90:
            exp = "Valuation imobiliário extremo vs. aluguéis e renda (bolha)."
            score = 1.0
        elif avg_pct > 75:
            exp = "Ativos caros em relação aos fundamentos clássicos."
            score = 0.75
        else:
            exp = "Valuation dentro da normalidade histórica."
            score = avg_pct / 100.0

        return SensorResult(
            sensor_name=self.__class__.__name__,
            score=score,
            confidence=0.80,
            status="ok",
            explanation=exp,
            details={"price_to_rent_pct": pr_pct, "price_to_income_pct": pi_pct},
        )
