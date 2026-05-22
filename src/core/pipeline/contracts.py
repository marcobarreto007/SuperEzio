"""Pipeline v4 contracts — typed state + Pydantic models for node I/O."""

from __future__ import annotations

from typing import Annotated, Any, TypedDict

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Fan-in reducer for expert_results (LangGraph Send fan-out)
# ---------------------------------------------------------------------------


def _expert_results_reducer(
    left: list[dict[str, Any]] | None,
    right: list[dict[str, Any]] | None,
) -> list[dict[str, Any]]:
    return (left or []) + (right or [])


# ---------------------------------------------------------------------------
# PipelineState (TypedDict — LangGraph native)
# ---------------------------------------------------------------------------


class PipelineState(TypedDict, total=False):
    """Unified state flowing through every LangGraph node.

    TypedDict is the native LangGraph state format. Pydantic models below
    are used for validation at node boundaries.
    """

    # Identity
    run_id: str
    session_id: str
    memory_mode: str
    rigor: str

    # User input
    message: str
    context: str

    # Orchestrator output
    route: str
    intent: str
    action: str
    intent_confidence: float
    intent_reasons: list[str]
    intent_source: str
    intent_fallback_error: str
    required_slots: list[str]
    entities: dict[str, Any]
    ticker: str
    filters: dict[str, Any]
    time_horizon: str
    trade_order_context: dict[str, Any]
    diary: bool
    pennylab: bool
    orchestrator_plan: str
    orchestrator_model_status: str

    # Data collection
    data: dict[str, Any]
    data_context: str
    scan: dict[str, Any]

    # PennyLab
    pennylab_result: dict[str, Any]

    # Experts (fan-out via Send — reducer applied by LangGraph)
    expert_results: Annotated[list[dict[str, Any]], _expert_results_reducer]
    expert_summary: str

    # F51 Verdict
    f51_verdict: dict[str, Any]

    # RAG
    rag_context: str

    # SDCA-Lite risk firewall
    sdca_firewall: dict[str, Any]
    sdca_blocked: bool
    sdca_review_required: bool

    # CEO
    final: str

    # Explanation
    explanation: str

    # Agent Loop
    agent_tool_call: dict[str, Any]
    agent_iterations: int

    # Errors
    errors: list[str]


# ---------------------------------------------------------------------------
# Pydantic models for node I/O validation
# ---------------------------------------------------------------------------


class IntentResult(BaseModel):
    """Orchestrator output: intent classification."""

    route: str = "general"
    intent: str = "general_question"
    action: str = "answer"
    ticker: str = ""
    filters: dict[str, str | None] = Field(default_factory=dict)
    confidence: float = 0.0
    required_slots: list[str] = Field(default_factory=list)
    reasons: list[str] = Field(default_factory=list)
    entities: dict[str, Any] = Field(default_factory=dict)
    diary: bool = False
    pennylab: bool = False
    source: str = "deterministic"


class CEORequest(BaseModel):
    """What the CEO node needs to generate a response."""

    task: str
    ticker: str = ""
    intent: str = "general_question"
    route: str = "general"
    data_context: str = ""
    pennylab_context: str = ""
    expert_summary: str = ""
    rag_context: str = ""
    f51_verdict: dict[str, Any] = Field(default_factory=dict)
    chart_context: str = ""
    mandamentos: str = ""
    model_family: str = "local"


class ExpertCall(BaseModel):
    """Single expert invocation via gateway."""

    role: str
    ticker: str
    context: str = ""
    provider_name: str = ""
    timeout: float = 60.0
