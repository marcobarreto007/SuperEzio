"""Stable contracts for SDCA-Lite risk firewall decisions."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class DecisionCandidate(BaseModel):
    """Candidate decision submitted to the defensive firewall."""

    model_config = ConfigDict(extra="allow")

    id: str
    source: str
    asset: str | None = None
    action: str
    thesis: str
    amount_cad: float | None = None
    risk_context: dict[str, Any] = Field(default_factory=dict)
    raw_signals: dict[str, Any] = Field(default_factory=dict)
    timestamp: str | None = None

    @field_validator("amount_cad")
    @classmethod
    def _non_negative_amount(cls, value: float | None) -> float | None:
        if value is not None and value < 0:
            raise ValueError("amount_cad must be non-negative")
        return value


class GhostTokenReport(BaseModel):
    """Structured latent-risk tokens from one specialist."""

    expert_name: str
    ghost_tokens: list[str] = Field(default_factory=list)
    uncertainty: float = Field(ge=0.0, le=1.0)
    evidence: dict[str, Any] = Field(default_factory=dict)
    reasoning_text_allowed: Literal[False] = False


class ExperienceEpisode(BaseModel):
    """Historical or curated SDCA memory episode."""

    id: str
    vector_text: str
    root_cause: str
    consequence: str
    learned_rule: str
    delta_r: float
    tags: list[str] = Field(default_factory=list)
    regime: str | None = None


class ExperienceMatch(BaseModel):
    """Retrieved experience with deterministic scoring."""

    episode_id: str
    similarity: float = Field(ge=0.0, le=1.0)
    delta_r: float
    weighted_score: float = Field(ge=0.0)
    learned_rule: str
    consequence: str


class RuminationState(BaseModel):
    """One bounded rumination cycle."""

    cycle: int = Field(ge=1)
    uncertainty: float = Field(ge=0.0, le=1.0)
    delta_u: float | None = None
    status: str


class ConsequenceScore(BaseModel):
    """Business and operational consequence utility scores."""

    delivery_7d: float = Field(ge=0.0, le=1.0)
    revenue_risk: float = Field(ge=0.0, le=1.0)
    chaos_reduction: float = Field(ge=0.0, le=1.0)
    truthfulness: float = Field(ge=0.0, le=1.0)
    cost_risk: float = Field(ge=0.0, le=1.0)
    utility: float = Field(ge=0.0, le=1.0)


class RiskFirewallDecision(BaseModel):
    """Auditable defensive decision."""

    decision: Literal["ALLOW", "BLOCK", "REVIEW"]
    confidence: float = Field(ge=0.0, le=1.0)
    uncertainty: float = Field(ge=0.0, le=1.0)
    ghost_tokens: list[str] = Field(default_factory=list)
    matched_experiences: list[ExperienceMatch] = Field(default_factory=list)
    rumination_trace: list[RuminationState] = Field(default_factory=list)
    consequence_score: ConsequenceScore
    human_summary: str
    audit_log: dict[str, Any] = Field(default_factory=dict)
