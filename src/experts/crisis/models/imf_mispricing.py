"""
Mispricing sensor — naive z-score over equity series.

NOTE: not the IMF model. This is a simple residual-vs-rolling-mean z-score,
kept under the stable class name for ensemble weight stability. The honest
implementation label is exposed in ``details["implementation"]``.
"""

from ..contracts.schemas import CrisisInput, SensorResult
from . import BaseCrisisModel
from ..logic.normalization import zscore_to_risk


class IMFMispricingModel:
    """Equity z-score mispricing sensor (stable class name retained)."""

    def evaluate(self, input_data: CrisisInput) -> SensorResult:
        # Fallback simple mispricing (z-score against long moving average)
        equities = [o.equity_index for o in input_data.observations if o.equity_index is not None]

        if len(equities) < 24:
            return BaseCrisisModel._insufficient_data(self.__class__.__name__, "Dados de equity insuficientes para estimar mispricing.")

        # Simplified residual estimation: current price vs 24-period mean
        mean_24 = sum(equities[-24:]) / 24.0
        residual = (equities[-1] - mean_24) / mean_24

        # Naive historical standard deviation of this residual
        residuals = []
        for i in range(24, len(equities)):
            m = sum(equities[i - 24 : i]) / 24.0
            residuals.append((equities[i] - m) / m)

        if not residuals:
            residuals = [0.0]

        import math

        mean_res = sum(residuals) / len(residuals)
        std_res = (
            math.sqrt(sum((r - mean_res) ** 2 for r in residuals) / len(residuals))
            if len(residuals) > 1
            else 1.0
        )
        if std_res == 0:
            std_res = 1.0

        z_score = (residual - mean_res) / std_res

        score = zscore_to_risk(z_score)

        return SensorResult(
            sensor_name=self.__class__.__name__,
            score=score,
            confidence=60.0,  # Low confidence for naive model
            status="ok",
            explanation=f"Z-Score estimado de mispricing de ativos: {z_score:.2f}.",
            details={
                "z_score": z_score,
                "implementation": "naive_zscore_24m",
                "implementation_note": (
                    "Residual-vs-rolling-mean z-score over the last 24 "
                    "observations. Not the IMF mispricing model."
                ),
            },
        )
