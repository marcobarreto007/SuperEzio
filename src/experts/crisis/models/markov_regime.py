"""
Regime classifier — threshold-based heuristic.

NOTE: this is NOT a Markov regime-switching model in the Hamilton (1989) /
hmmlearn sense. It is a deterministic threshold over realized volatility
and credit spreads, kept under the stable class name for ensemble weight
stability. The honest implementation label is exposed in
``details["implementation"]`` so consumers do not assume HMM semantics.
"""

from ..contracts.schemas import CrisisInput, SensorResult
from . import BaseCrisisModel


class MarkovRegimeModel:
    """Threshold-based regime classifier (stable class name retained)."""

    def evaluate(self, input_data: CrisisInput) -> SensorResult:
        if not input_data.market_series or len(input_data.market_series) < 5:
            return BaseCrisisModel._insufficient_data(
                self.__class__.__name__,
                "Necessário market_series com volatilidade e spreads para classificar regime.",
            )

        recent = input_data.market_series[-1]

        vol = recent.realized_volatility or 0.0
        spread = recent.credit_spread or 0.0

        # score/confidence are 0-1 to match every other crisis model's
        # contract (crisis.py's aggregator assumes 0-1, multiplies by 100
        # once — a 0-100 score here doubled the scale. See
        # docs/audit/phase9_parallel_fixes_and_critical_findings.md).
        score = 0.0
        exp = "Regime Normal"

        if vol > 0.30 and spread > 5.0:
            score = 1.0
            exp = "Regime de CRISE: Volatilidade e spreads de crédito explodiram."
        elif vol > 0.20 or spread > 3.0:
            score = 0.70
            exp = "Regime de STRESS: Mercado sinaliza prêmios de risco altos."
        elif vol < 0.12 and spread < 1.5:
            score = 0.20
            exp = "Regime NORMAL / Complacente."
        else:
            score = 0.40
            exp = "Regime de transição."

        return SensorResult(
            sensor_name=self.__class__.__name__,
            score=score,
            confidence=0.70,
            status="ok",
            explanation=exp,
            details={
                "volatility": vol,
                "spread": spread,
                "implementation": "threshold_heuristic",
                "implementation_note": (
                    "Deterministic thresholds over volatility and credit "
                    "spreads. Not a Markov-switching model."
                ),
            },
        )
