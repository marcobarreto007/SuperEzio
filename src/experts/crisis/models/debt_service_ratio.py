"""
Debt Service Ratio Sensor.
"""

from ..contracts.schemas import CrisisInput, SensorResult
from . import BaseCrisisModel
from ..logic.normalization import percentile_rank


class DebtServiceRatioModel:
    def evaluate(self, input_data: CrisisInput) -> SensorResult:
        obs = [
            o.debt_service_ratio
            for o in input_data.observations
            if o.debt_service_ratio is not None
        ]

        if len(obs) < 12:
            return BaseCrisisModel._insufficient_data(
                self.__class__.__name__, "Não há histórico suficiente de debt_service_ratio."
            )

        current = obs[-1]
        pct = percentile_rank(obs, current)

        if pct < 50:
            score = 20.0
            exp = "DSR está abaixo da mediana histórica. Fardo da dívida controlável."
        elif pct < 75:
            score = 50.0
            exp = "DSR moderado a alto contra histórico."
        elif pct < 90:
            score = 80.0
            exp = "DSR no quartil superior histórico. Oneração de caixa relevante."
        else:
            score = 100.0
            exp = "DSR em nível extremo (percentil 90+). Alta probabilidade de default em massa."

        return SensorResult(
            sensor_name=self.__class__.__name__,
            score=score,
            confidence=80.0,
            status="ok",
            explanation=exp,
            details={"current_dsr": current, "percentile": pct},
        )
