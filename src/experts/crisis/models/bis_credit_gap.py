"""
BIS Credit-to-GDP Gap Sensor.
"""

from ..contracts.schemas import CrisisInput, SensorResult
from . import BaseCrisisModel


class BISCreditGapModel:
    def evaluate(self, input_data: CrisisInput) -> SensorResult:
        obs = [o.credit_to_gdp for o in input_data.observations if o.credit_to_gdp is not None]

        # Require minimum history (e.g. 12 periods)
        if len(obs) < 12:
            return BaseCrisisModel._insufficient_data(
                self.__class__.__name__, "Não há dados suficientes de credit_to_gdp (mínimo 12)."
            )

        # BIS uses HP filter (lambda=400000 for quarterly). When statsmodels is
        # unavailable we fall back to a 12-period moving average — much weaker
        # signal, so we mark the result as ``degraded=True`` and lower confidence
        # so the consumer can flag this as a simplified estimate.
        degraded = False
        try:
            from statsmodels.tsa.filters.hp_filter import hpfilter
            import numpy as np

            cycle, trend = hpfilter(np.array(obs), lamb=400000)
            gap = obs[-1] - trend[-1]
            implementation = "hp_filter_lambda_400000"
        except ImportError:
            trend = sum(obs[-12:]) / 12.0
            gap = obs[-1] - trend
            degraded = True
            implementation = "moving_average_12_fallback"

        if gap <= 0:
            raw_score = 0.0
            explanation = "Credit-to-GDP abaixo da tendência. Baixo risco sistêmico."
        elif gap <= 2.0:
            raw_score = 25.0
            explanation = "Credit-to-GDP com gap positivo leve."
        elif gap <= 10.0:
            raw_score = 50.0 + ((gap - 2.0) / 8.0) * 25.0
            explanation = "Credit-to-GDP crescendo significativamente acima da tendência."
        else:
            raw_score = 75.0 + min(((gap - 10.0) / 10.0) * 25.0, 25.0)
            explanation = "Credit-to-GDP com gap extremo (>10%), histórico de alerta máximo (BIS)."

        if degraded:
            explanation = f"[modelo simplificado — média móvel 12 períodos no lugar do HP filter] {explanation}"

        return SensorResult(
            sensor_name=self.__class__.__name__,
            score=raw_score,
            confidence=60.0 if degraded else 80.0,
            status="ok",
            explanation=explanation,
            details={
                "current_gap": gap,
                "current_ratio": obs[-1],
                "implementation": implementation,
                "degraded": degraded,
            },
        )
