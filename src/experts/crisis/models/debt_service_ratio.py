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

        # percentile_rank() returns 0-100 (see its docstring); pct/thresholds
        # stay on that scale, but score/confidence in SensorResult must be
        # 0-1 to match every other crisis model's contract (crisis.py's
        # aggregator assumes 0-1 then multiplies by 100 once — a 0-100 score
        # here doubled the scale. See
        # docs/audit/phase9_parallel_fixes_and_critical_findings.md).
        current = obs[-1]
        pct = percentile_rank(obs, current)

        if pct < 50:
            score = 0.20
            exp = "DSR está abaixo da mediana histórica. Fardo da dívida controlável."
        elif pct < 75:
            score = 0.50
            exp = "DSR moderado a alto contra histórico."
        elif pct < 90:
            score = 0.80
            exp = "DSR no quartil superior histórico. Oneração de caixa relevante."
        else:
            score = 1.0
            exp = "DSR em nível extremo (percentil 90+). Alta probabilidade de default em massa."

        return SensorResult(
            sensor_name=self.__class__.__name__,
            score=score,
            confidence=0.80,
            status="ok",
            explanation=exp,
            details={"current_dsr": current, "percentile": pct},
        )
