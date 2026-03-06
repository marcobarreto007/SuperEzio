"""
Tool Adapters for CrisisMathExpert.
Bridges the crisis sensors to the Orchestrator's ToolRegistry.
"""

import asyncio
from typing import Dict, Any, Optional
from ..expert.crisis_expert import CrisisMathExpert
from ..contracts.schemas import CrisisInput, MacroObservation, MarketObservation


async def tool_analyze_systemic_risk(
    country: Optional[str] = None,
    asset_symbol: Optional[str] = None,
    macro_data: Optional[list] = None,
    market_data: Optional[list] = None,
) -> Dict[str, Any]:
    """
    Expert Tool: Calculates systemic risk, bubble risk, and financial stress
    using institutional mathematical models (BIS, IMF, Shiller, Minsky).

    This tool acts as a high-precision 'scientific calculator' for financial fragility.

    Args:
        country: Country to analyze (e.g., Brazil, USA).
        asset_symbol: Optional ticker.
        macro_data: List of macro observations (date, credit_to_gdp, policy_rate, etc.).
        market_data: List of market observations (date, realized_volatility, spread, etc.).
    """
    try:
        # Convert raw lists to Pydantic models
        observations = []
        if macro_data:
            for d in macro_data:
                observations.append(MacroObservation(**d))

        market_series = []
        if market_data:
            for d in market_data:
                market_series.append(MarketObservation(**d))

        input_data = CrisisInput(
            country=country,
            asset_symbol=asset_symbol,
            observations=observations,
            market_series=market_series,
        )

        expert = CrisisMathExpert()
        # Execution is math-heavy, run in thread to keep pipeline responsive
        report = await asyncio.to_thread(expert.analyze, input_data)

        return report.model_dump(mode="json")

    except Exception as e:
        return {"error": f"CrisisMathExpert calculation failed: {str(e)}"}


__all__ = ["tool_analyze_systemic_risk"]
