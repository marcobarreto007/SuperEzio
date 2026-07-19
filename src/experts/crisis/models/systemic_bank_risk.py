"""Systemic bank-risk contract without synthetic SRISK/LRMES proxies."""

from ..contracts.schemas import CrisisInput, SensorResult
from . import BaseCrisisModel


class SystemicBankRiskModel:
    """Compatibility entrypoint awaiting real bank equity and balance-sheet panels."""

    def evaluate(self, input_data: CrisisInput) -> SensorResult:
        observations = input_data.observations
        return BaseCrisisModel._insufficient_data(
            self.__class__.__name__,
            "SRISK/LRMES unavailable: requires bank-level equity returns, market returns, "
            "market capitalization, liabilities, and a declared capital ratio. Aggregate "
            "macro series are not valid substitutes.",
            horizon="not estimable from current input contract",
            sample_size=len(observations),
            as_of=observations[-1].date if observations else None,
        )
