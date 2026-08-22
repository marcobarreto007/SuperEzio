"""Pipeline v4 contracts — typed state + Pydantic models for node I/O."""

from __future__ import annotations

from typing import Annotated, Any, Literal, TypedDict

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
    cognitive_mode: str
    information_need: str
    allowed_tools: list[str]
    market_context_allowed: bool
    scanner_allowed: bool
    ticker_allowed: bool
    ticket_allowed: bool
    answer_contract: str
    time_horizon: str
    trade_order_context: dict[str, Any]
    diary: bool
    pennylab: bool
    orchestrator_plan: str
    orchestrator_model_status: str

    # ── IBKR Portfolio Snapshot ──
    portfolio_snapshot: str  # injected by auto_full_analysis → agent SYSTEM STATUS
    portfolio_context: str  # legacy alias, populated by graph.py IBKR probe

    # ── Bob Sovereign Mode (SUPEREZIO_BOB_SOVEREIGN=1) ──
    bob_intent: str  # intenção classificada (não é rota!)
    risk_tolerance: str  # "conservadora" | "moderada" | "alta" | "especulativa"
    bob_thesis: str  # tese que Bob formou ANTES de chamar tools
    bob_reasoning_trace: list[str]  # passos de raciocínio do Bob
    current_datetime: str  # injetado a cada execução (datetime.now())

    # Data collection
    data: dict[str, Any]
    data_context: str
    scan: dict[str, Any]

    # Unified math/guardrail stage
    math_report: dict[str, Any]
    math_prompt: str
    sentiment_prompt: str
    guardrail_hub: dict[str, Any]
    decision_trace: dict[str, Any]

    # Trinity deliberation
    trinity_report: str
    trinity_structured: dict[str, Any]
    trinity_blocked: bool

    # PennyLab
    pennylab_result: dict[str, Any]

    # Mangala Engine
    mangala_opportunities: list[dict[str, Any]]
    mangala_has_high_conviction: bool
    mangala_prompt: str

    # Experts (fan-out via Send — reducer applied by LangGraph)
    expert_results: Annotated[list[dict[str, Any]], _expert_results_reducer]
    expert_summary: str
    expert_raw: str
    expert_structured: dict[str, Any]
    expert_weights: dict[str, float]
    expert_consensus: dict[str, Any]

    # F51 Verdict
    f51_verdict: dict[str, Any]

    # RAG
    rag_context: str

    # SDCA-Lite risk firewall
    sdca_firewall: dict[str, Any]
    sdca_blocked: bool
    sdca_review_required: bool

    # Agent node
    final: str

    # Explanation
    explanation: str

    # Agent Loop
    agent_tool_call: dict[str, Any]
    agent_iterations: int
    _pending_tool_calls: list[dict[str, Any]]
    executed_tools: list[str]
    executed_tool_counts: dict[str, int]
    tool_blocked: dict[str, Any]
    last_tool_result: str

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
    cognitive_mode: str = "ADVISORY_KNOWLEDGE"
    information_need: str = "natural_language_financial_guidance"
    allowed_tools: list[str] = Field(default_factory=lambda: ["final_answer"])
    market_context_allowed: bool = False
    scanner_allowed: bool = False
    ticker_allowed: bool = False
    ticket_allowed: bool = False
    answer_contract: str = ""
    diary: bool = False
    pennylab: bool = False
    source: str = "deterministic"


class AgentRequest(BaseModel):
    """What the agent node needs to generate a response."""

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


class AgentToolCall(BaseModel):
    """Validated tool call emitted by the ReAct agent."""

    tool: Literal[
        "collect_data",
        "f51_firewall",
        "pennylab",
        "run_experts",
        "neural_decision",
        "sdca_firewall",
        "rag_forensics",
        "market_scan",
        "penny_momentum_backtest",
        "submit_paper_order",
        "final_answer",
        "bob_search",
        "social_forensics",
        "query_expert",
        "call_math_calculator",
        "get_live_financial_data",
    ]
    args: dict[str, Any] = Field(default_factory=dict)
