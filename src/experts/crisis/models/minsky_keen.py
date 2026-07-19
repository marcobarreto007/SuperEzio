"""
Minsky-Keen Private Debt Fragility Sensor.
"""

from ..contracts.schemas import CrisisInput, SensorResult
from . import BaseCrisisModel
from ..logic.normalization import clamp, percentile_rank


class MinskyKeenModel:
    def evaluate(self, input_data: CrisisInput) -> SensorResult:
        valid_obs = [
            o
            for o in input_data.observations
            if o.credit_to_gdp and o.gdp_growth_yoy and o.policy_rate
        ]

        if len(valid_obs) < 4:
            return BaseCrisisModel._insufficient_data(
                self.__class__.__name__,
                "Minsky fragility requer credit_to_gdp, gdp_growth_yoy e policy_rate.",
            )

        last = valid_obs[-1]

        # All three components and the final fragility score are computed on
        # a 0-1 scale to match every other crisis model's SensorResult
        # contract (crisis.py's aggregator averages r["score"]/r["confidence"]
        # across all 12 models assuming 0-1, then multiplies by 100 once —
        # this model previously computed everything on 0-100 internally,
        # which doubled the scale for both score and confidence and could
        # push the aggregate crisis score above 1000 when this model
        # dominated. Confirmed live via /task/submit — see
        # docs/audit/phase9_parallel_fixes_and_critical_findings.md).
        # percentile_rank() returns 0-100 (see its own docstring) — divide to
        # bring it onto the same 0-1 scale as the other two components below.
        all_debt = [o.credit_to_gdp for o in valid_obs]
        debt_score = percentile_rank(all_debt, last.credit_to_gdp) / 100.0

        # 2. Rate pressure (0-1)
        rate_score = 1.0 if last.policy_rate > 5.0 else last.policy_rate / 5.0

        # 3. Growth slowdown (0-1)
        growth_score = (
            1.0 if last.gdp_growth_yoy < 0 else max(0.0, 1.0 - (last.gdp_growth_yoy * 0.20))
        )

        # clamp() defaults to max_value=100.0 (its own 0-100 convention) — pass
        # max_value=1.0 explicitly since this model's fragility is 0-1.
        fragility = clamp(
            0.40 * debt_score + 0.30 * rate_score + 0.30 * growth_score, max_value=1.0
        )

        if fragility > 0.80:
            exp = "Padrão Ponzi-like: Dívida extrema, juros pesando e crescimento anêmico."
        elif fragility > 0.50:
            exp = "Padrão Especulativo: Fragilidade de dívida privada em elevação."
        else:
            exp = "Padrão Hedge-like: Financiamento saudável."

        return SensorResult(
            sensor_name=self.__class__.__name__,
            score=fragility,
            confidence=0.75,
            status="ok",
            explanation=exp,
            details={
                "minsky_state": (
                    "Ponzi" if fragility > 0.80 else "Speculative" if fragility > 0.50 else "Hedge"
                )
            },
        )
