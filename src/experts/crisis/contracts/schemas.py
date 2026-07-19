"""Validated, audit-friendly data contracts for CrisisMathExpert."""

from datetime import datetime
import re
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, computed_field, field_validator, model_validator


_MONTH_RE = re.compile(r"^\d{4}-\d{2}$")


def _validate_observation_date(value: str) -> str:
    """Accept ISO-8601 dates/timestamps and explicit ``YYYY-MM`` periods only."""
    value = value.strip()
    if not value:
        raise ValueError("date must not be empty")
    try:
        if _MONTH_RE.fullmatch(value):
            datetime.strptime(value, "%Y-%m")
        else:
            datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("date must be ISO-8601 or YYYY-MM") from exc
    return value


class MacroObservation(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False)

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

    _valid_date = field_validator("date")(_validate_observation_date)


class MarketObservation(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False)

    date: str
    close: float = Field(gt=0.0)
    volume: Optional[float] = None
    realized_volatility: Optional[float] = None
    credit_spread: Optional[float] = None
    vix_like_index: Optional[float] = None

    _valid_date = field_validator("date")(_validate_observation_date)


class CrisisInput(BaseModel):
    country: Optional[str] = None
    asset_symbol: Optional[str] = None
    frequency: Literal["daily", "weekly", "monthly", "quarterly", "annual"] = "monthly"
    observations: list[MacroObservation] = Field(default_factory=list)
    market_series: Optional[list[MarketObservation]] = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_chronology(self) -> "CrisisInput":
        """Time-series inputs must be strictly increasing and non-duplicated."""
        for field_name, values in (
            ("observations", self.observations),
            ("market_series", self.market_series or []),
        ):
            dates = [item.date for item in values]
            if dates != sorted(dates) or len(dates) != len(set(dates)):
                raise ValueError(f"{field_name} dates must be unique and strictly increasing")
        return self


class SensorResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sensor_name: str
    score: float = Field(ge=0.0, le=1.0, strict=True, description="Risk score on the unit interval")
    confidence: float = Field(
        ge=0.0, le=1.0, strict=True, description="Sensor confidence on the unit interval"
    )
    status: Literal["ok", "insufficient_data", "error"]
    explanation: str
    method_kind: Literal[
        "statistical_model", "econometric_model", "deterministic", "heuristic", "unavailable"
    ] = "heuristic"
    horizon: Optional[str] = None
    sample_size: int = Field(default=0, ge=0)
    as_of: Optional[str] = None
    calibration_status: Literal[
        "not_applicable",
        "not_calibrated",
        "in_sample_mle",
        "rolling_validated",
        "multi_window_filtered",
        "unavailable",
        "failed",
    ] = "not_calibrated"
    details: dict[str, Any] = Field(default_factory=dict)

    @field_validator("as_of")
    @classmethod
    def validate_as_of(cls, value: Optional[str]) -> Optional[str]:
        return _validate_observation_date(value) if value is not None else None

    @model_validator(mode="after")
    def unavailable_metadata_is_explicit(self) -> "SensorResult":
        if self.status != "ok":
            self.method_kind = "unavailable"
            self.calibration_status = "failed" if self.status == "error" else "unavailable"
        return self

    @computed_field
    @property
    def severity(self) -> Literal["normal", "warning", "stress", "crisis", "unavailable"]:
        """Severity is a pure projection of score, never a second source of truth."""
        if self.status != "ok":
            return "unavailable"
        if self.score > 0.75:
            return "crisis"
        if self.score > 0.50:
            return "stress"
        if self.score > 0.25:
            return "warning"
        return "normal"


class CrisisReport(BaseModel):
    status: Literal["ok", "partial", "unavailable"] = "ok"
    systemic_risk_score: float = Field(ge=0.0, le=1.0, strict=True)
    bubble_risk_score: float = Field(ge=0.0, le=1.0, strict=True)
    liquidity_stress_score: float = Field(ge=0.0, le=1.0, strict=True)
    credit_fragility_score: float = Field(ge=0.0, le=1.0, strict=True)
    bank_fragility_score: Optional[float] = Field(default=None, ge=0.0, le=1.0, strict=True)
    contagion_risk_score: Optional[float] = Field(default=None, ge=0.0, le=1.0, strict=True)
    final_risk_score: float = Field(ge=0.0, le=1.0, strict=True)
    regime: Literal["normal", "overheating", "stress", "crisis", "unavailable"]
    alert_level: Literal["green", "yellow", "red", "black", "unavailable"]
    confidence: float = Field(ge=0.0, le=1.0, strict=True)
    sensor_results: list[SensorResult] = Field(default_factory=list)
    summary: str
    recommendations: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
