"""Network contagion contract without synthetic CoVaR or DebtRank proxies."""

from ..contracts.schemas import CrisisInput, SensorResult
from . import BaseCrisisModel


class NetworkContagionModel:
    """Compatibility entrypoint awaiting institution-level exposure data.

    A single asset series cannot identify CoVaR, and rolling transformations of
    that same series are not an interbank network. The current public input
    contract does not carry dated institution returns or bilateral exposures,
    so producing a score would be fabricated precision.
    """

    def evaluate(self, input_data: CrisisInput) -> SensorResult:
        market = input_data.market_series or []
        return BaseCrisisModel._insufficient_data(
            self.__class__.__name__,
            "CoVaR/DebtRank unavailable: requires dated institution-level returns, "
            "system returns, and a real bilateral exposure matrix with provenance.",
            horizon="not estimable from current input contract",
            sample_size=len(market),
            as_of=market[-1].date if market else None,
        )
