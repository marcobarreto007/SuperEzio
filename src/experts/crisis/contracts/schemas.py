"""
Data contracts for CrisisMathExpert.
"""

from typing import Any, List, Optional
from pydantic import BaseModel, Field


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
    sensor_name: str
    score: float
    confidence: float
    status: str  # ok, insufficient_data, error
    explanation: str
    details: dict[str, Any] = Field(default_factory=dict)


class CrisisReport(BaseModel):
    systemic_risk_score: float
    bubble_risk_score: float
    liquidity_stress_score: float
    credit_fragility_score: float
    bank_fragility_score: Optional[float] = None
    contagion_risk_score: Optional[float] = None
    final_risk_score: float
    regime: str  # normal, overheating, stress, crisis
    alert_level: str  # green, yellow, red, black
    confidence: float
    sensor_results: List[SensorResult] = Field(default_factory=list)
    summary: str
    recommendations: List[str] = Field(default_factory=list)
    limitations: List[str] = Field(default_factory=list)
