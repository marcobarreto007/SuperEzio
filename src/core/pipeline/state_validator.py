"""PipelineState runtime validator — optional type-safety for LangGraph state.

Usage:
    from core.pipeline.state_validator import validate_state

    state = validate_state(raw_state)  # returns validated dict with defaults
"""

from __future__ import annotations

from typing import Any

# All known PipelineState keys with their expected types and defaults
_STATE_SCHEMA: dict[str, dict] = {
    # Identity
    "run_id": {"type": str, "default": ""},
    "session_id": {"type": str, "default": "default"},
    "memory_mode": {"type": str, "default": "relevant_all"},
    "rigor": {"type": str, "default": "strict"},
    # User input
    "message": {"type": str, "default": ""},
    "context": {"type": str, "default": ""},
    # Orchestrator
    "route": {"type": str, "default": "agent"},
    "intent": {"type": str, "default": "bob_decides"},
    "action": {"type": str, "default": "analyze_and_execute"},
    "intent_confidence": {"type": (int, float), "default": 0.0},
    "intent_reasons": {"type": list, "default": []},
    "required_slots": {"type": list, "default": []},
    "entities": {"type": dict, "default": {}},
    "ticker": {"type": str, "default": ""},
    "filters": {"type": dict, "default": {}},
    "cognitive_mode": {"type": str, "default": "FULL_ACCESS"},
    "allowed_tools": {"type": list, "default": ["final_answer"]},
    "scanner_allowed": {"type": bool, "default": True},
    "ticker_allowed": {"type": bool, "default": True},
    "ticket_allowed": {"type": bool, "default": False},
    "answer_contract": {"type": str, "default": ""},
    "time_horizon": {"type": str, "default": "14 days"},
    "trade_order_context": {"type": dict, "default": {}},
    # Portfolio
    "portfolio_snapshot": {"type": str, "default": ""},
    "portfolio_context": {"type": str, "default": ""},
    # Bob Sovereign
    "bob_intent": {"type": str, "default": ""},
    "risk_tolerance": {"type": str, "default": "moderada"},
    "bob_thesis": {"type": str, "default": ""},
    "bob_reasoning_trace": {"type": list, "default": []},
    "current_datetime": {"type": str, "default": ""},
    # Data collection
    "data": {"type": dict, "default": {}},
    "data_context": {"type": str, "default": ""},
    "scan": {"type": dict, "default": {}},
    # Math/Guardrails
    "math_report": {"type": dict, "default": {}},
    "guardrail_hub": {"type": dict, "default": {}},
    "decision_trace": {"type": dict, "default": {}},
    # Trinity
    "trinity_report": {"type": str, "default": ""},
    "trinity_blocked": {"type": bool, "default": False},
    # PennyLab
    "pennylab_result": {"type": dict, "default": {}},
    # Experts
    "expert_results": {"type": list, "default": []},
    "expert_summary": {"type": str, "default": ""},
    # F51
    "f51_verdict": {"type": dict, "default": {}},
    # RAG
    "rag_context": {"type": str, "default": ""},
    # SDCA
    "sdca_firewall": {"type": dict, "default": {}},
    "sdca_blocked": {"type": bool, "default": False},
    # Agent
    "final": {"type": str, "default": ""},
    "agent_tool_call": {"type": dict, "default": {}},
    "agent_iterations": {"type": int, "default": 0},
    "_pending_tool_calls": {"type": list, "default": []},
    "executed_tools": {"type": list, "default": []},
    "executed_tool_counts": {"type": dict, "default": {}},
    "tool_blocked": {"type": dict, "default": {}},
    "last_tool_result": {"type": str, "default": ""},
    # Errors
    "errors": {"type": list, "default": []},
    # Social forensics veto
    "social_forensics_veto": {"type": dict, "default": {}},
    # Neural decision
    "neural_decision": {"type": dict, "default": {}},
    # Explanation
    "explanation": {"type": str, "default": ""},
    # CASE
    "case_pending": {"type": list, "default": []},
    "case_context": {"type": str, "default": ""},
    "financial_case": {"type": object, "default": None},
}


def validate_state(state: dict[str, Any], strict: bool = False) -> dict[str, Any]:
    """Validate and fill defaults for pipeline state.

    Args:
        state: Raw state dict from LangGraph.
        strict: If True, warn on unknown keys (default: silently pass through).

    Returns:
        State dict with defaults filled for missing known keys.
        Unknown keys are preserved (LangGraph passes through extra fields).
    """
    validated: dict[str, Any] = {}

    for key, spec in _STATE_SCHEMA.items():
        if key in state:
            value = state[key]
            expected = spec["type"]
            # Accept the value if it matches expected type
            if isinstance(expected, tuple):
                if isinstance(value, expected):
                    validated[key] = value
                else:
                    validated[key] = spec["default"]
            elif expected is object:
                validated[key] = value  # accept anything
            elif isinstance(value, expected):
                validated[key] = value
            else:
                validated[key] = spec["default"]
        else:
            validated[key] = spec["default"]

    # Pass through unknown keys (LangGraph may add internal keys)
    for key in state:
        if key not in _STATE_SCHEMA:
            validated[key] = state[key]

    return validated


def get_state_keys() -> list[str]:
    """Return all known state keys for auto-complete / debugging."""
    return sorted(_STATE_SCHEMA.keys())


def get_required_for_route(route: str) -> list[str]:
    """Return minimum required keys for a given pipeline route."""
    common = ["run_id", "message", "route", "intent", "allowed_tools"]
    route_specific = {
        "market_scan": ["scanner_allowed", "scan"],
        "ticker_analysis": ["ticker", "ticker_allowed", "data"],
        "agent": ["cognitive_mode", "allowed_tools"],
    }
    return common + route_specific.get(route, [])
