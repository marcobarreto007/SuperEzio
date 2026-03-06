"""
Minsky-Keen Private Debt Fragility Sensor.
"""

from ..contracts.schemas import CrisisInput, SensorResult
from ..logic.normalization import clamp, percentile_rank


class MinskyKeenModel:
    def evaluate(self, input_data: CrisisInput) -> SensorResult:
        valid_obs = [
            o
            for o in input_data.observations
            if o.credit_to_gdp and o.gdp_growth_yoy and o.policy_rate
        ]

        if len(valid_obs) < 4:
            return SensorResult(
                sensor_name=self.__class__.__name__,
                score=0.0,
                confidence=0.0,
                status="insufficient_data",
                explanation="Minsky fragility requer credit_to_gdp, gdp_growth_yoy e policy_rate.",
            )

        last = valid_obs[-1]

        # 1. Debt level
        all_debt = [o.credit_to_gdp for o in valid_obs]
        debt_score = percentile_rank(all_debt, last.credit_to_gdp)

        # 2. Rate pressure
        rate_score = (
            100.0 if last.policy_rate > 5.0 else (last.policy_rate / 5.0) * 100.0
        )

        # 3. Growth slowdown
        growth_score = (
            100.0
            if last.gdp_growth_yoy < 0
            else max(0, 100 - (last.gdp_growth_yoy * 20))
        )

        fragility = clamp(0.40 * debt_score + 0.30 * rate_score + 0.30 * growth_score)

        if fragility > 80:
            exp = "Padrão Ponzi-like: Dívida extrema, juros pesando e crescimento anêmico."
        elif fragility > 50:
            exp = "Padrão Especulativo: Fragilidade de dívida privada em elevação."
        else:
            exp = "Padrão Hedge-like: Financiamento saudável."

        return SensorResult(
            sensor_name=self.__class__.__name__,
            score=fragility,
            confidence=75.0,
            status="ok",
            explanation=exp,
            details={
                "minsky_state": (
                    "Ponzi"
                    if fragility > 80
                    else "Speculative"
                    if fragility > 50
                    else "Hedge"
                )
            },
        )
