"""
Credit x Asset Growth Sensor.
"""

from ..contracts.schemas import CrisisInput, SensorResult
from ..logic.normalization import clamp, percentile_rank


class CreditAssetGrowthModel:
    def evaluate(self, input_data: CrisisInput) -> SensorResult:
        credits = [
            o.credit_growth_yoy for o in input_data.observations if o.credit_growth_yoy is not None
        ]
        houses = [
            o.house_price_index for o in input_data.observations if o.house_price_index is not None
        ]
        equities = [o.equity_index for o in input_data.observations if o.equity_index is not None]

        if len(credits) < 12 or len(houses) < 12:
            return SensorResult(
                sensor_name=self.__class__.__name__,
                score=0.0,
                confidence=0.0,
                status="insufficient_data",
                explanation="Faltam dados de crédito ou imóveis para avaliar o ciclo cruzado.",
            )

        cred_pct = percentile_rank(credits, credits[-1])

        # Calculate YoY for house
        h_yoy = ((houses[-1] / houses[-12]) - 1.0) * 100 if houses[-12] > 0 else 0.0
        # Pseudo history for percentiles
        h_yoys = []
        for i in range(12, len(houses)):
            if houses[i - 12] > 0:
                h_yoys.append(((houses[i] / houses[i - 12]) - 1.0) * 100)
        h_pct = percentile_rank(h_yoys, h_yoy) if h_yoys else 50.0

        e_pct = 0.0
        if len(equities) >= 12:
            e_yoy = ((equities[-1] / equities[-12]) - 1.0) * 100 if equities[-12] > 0 else 0.0
            e_yoys = [
                ((equities[i] / equities[i - 12]) - 1.0) * 100
                for i in range(12, len(equities))
                if equities[i - 12] > 0
            ]
            e_pct = percentile_rank(e_yoys, e_yoy) if e_yoys else 50.0

        base_score = 0.45 * cred_pct + 0.35 * h_pct + 0.20 * e_pct

        # Interaction bonuses
        bonus = 0.0
        if cred_pct >= 90 and h_pct >= 90 and e_pct >= 90:
            bonus = 30.0
        elif cred_pct >= 90 and h_pct >= 90:
            bonus = 20.0
        elif cred_pct >= 75 and h_pct >= 75:
            bonus = 10.0

        final_score = clamp(base_score + bonus)

        if final_score > 80:
            exp = (
                "Sinais fortes de duplo boom: expansão extrema de crédito e valorização de ativos."
            )
        elif final_score > 60:
            exp = "Crescimento combinado de crédito e ativos acima da média."
        else:
            exp = "Não há boom simultâneo alarmante de crédito e ativos no momento."

        return SensorResult(
            sensor_name=self.__class__.__name__,
            score=final_score,
            confidence=85.0,
            status="ok",
            explanation=exp,
            details={
                "credit_growth_pct": cred_pct,
                "house_growth_pct": h_pct,
                "equity_growth_pct": e_pct,
            },
        )
