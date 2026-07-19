"""
Data contracts for CrisisMathExpert.
"""

from typing import Any, List, Literal, Optional
from pydantic import BaseModel, ConfigDict, Field, computed_field


class MacroObservation(BaseModel):
    date: str
    credit_to_gdp: Optional[float] = None
    credit_growth_yoy: Optional[float] = None
    gdp_growth_yoy: Optional[float] = None
    debt_service_ratio: Optional[float] = None
    house_price_index: Optional[float] = None
    rent_index: Optional[float] = None
    income_index: Optional[float] = None
    equity_index: Optional[float] = None
    policy_rate: Optional[float] = None
    unemployment_rate: Optional[float] = None
    inflation_yoy: Optional[float] = None


class MarketObservation(BaseModel):
    date: str
    close: float
    volume: Optional[float] = None
    realized_volatility: Optional[float] = None
    credit_spread: Optional[float] = None
    vix_like_index: Optional[float] = None


class CrisisInput(BaseModel):
    country: Optional[str] = None
    asset_symbol: Optional[str] = None
    frequency: str = "monthly"
    observations: List[MacroObservation] = Field(default_factory=list)
    market_series: Optional[List[MarketObservation]] = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class SensorResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sensor_name: str
    score: float = Field(ge=0.0, le=1.0, strict=True, description="Risk score on the unit interval")
    confidence: float = Field(
        ge=0.0, le=1.0, strict=True, description="Sensor confidence on the unit interval"
    )
    status: Literal["ok", "insufficient_data", "error"]
    explanation: str
    details: dict[str, Any] = Field(default_factory=dict)

    @computed_field
    @property
    def severity(self) -> Literal["normal", "warning", "stress", "crisis"]:
        """Severity is a pure projection of score, never a second source of truth."""
        if self.score > 0.75:
            return "crisis"
        if self.score > 0.50:
            return "stress"
        if self.score > 0.25:
            return "warning"
        return "normal"


class CrisisReport(BaseModel):
    systemic_risk_score: float = Field(ge=0.0, le=1.0, strict=True)
    bubble_risk_score: float = Field(ge=0.0, le=1.0, strict=True)
    liquidity_stress_score: float = Field(ge=0.0, le=1.0, strict=True)
    credit_fragility_score: float = Field(ge=0.0, le=1.0, strict=True)
    bank_fragility_score: Optional[float] = Field(default=None, ge=0.0, le=1.0, strict=True)
    contagion_risk_score: Optional[float] = Field(default=None, ge=0.0, le=1.0, strict=True)
    final_risk_score: float = Field(ge=0.0, le=1.0, strict=True)
    regime: Literal["normal", "overheating", "stress", "crisis"]
    alert_level: Literal["green", "yellow", "red", "black"]
    confidence: float = Field(ge=0.0, le=1.0, strict=True)
    sensor_results: List[SensorResult] = Field(default_factory=list)
    summary: str
    recommendations: List[str] = Field(default_factory=list)
    limitations: List[str] = Field(default_factory=list)
