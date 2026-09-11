"""Safety valve node — blocks vague/unscoped financial requests."""

from langgraph.config import get_stream_writer

from core.pipeline.organ_board import sdca_block_reason

VAGUE_FINANCIAL_RESPONSE = (
    "[SuperEzio Trust OS] I cannot provide investment recommendations "
    "without a specific ticker and a clear research question.\n\n"
    "Please ask again with:\n"
    "- A ticker (e.g., ENB.TO, HIVE.V, MSFT)\n"
    "- A research goal (e.g., analyze risk, detect fraud, check volume spike)\n"
    "- Optional: country, sector, or time horizon"
)


def _sdca_blocked_response(state: dict) -> str:
    _sdca_raw = state.get("sdca_firewall")
    sdca = _sdca_raw if isinstance(_sdca_raw, dict) else {}
    summary = sdca.get("human_summary") or "SDCA-Lite blocked this candidate decision."
    tokens = sdca.get("ghost_tokens") or []
    token_text = ", ".join(str(token) for token in tokens[:6]) if tokens else "none"
    return (
        "[F51 Cognitive Risk Firewall] BLOCKED\n\n"
        f"{summary}\n\n"
        f"Ghost tokens: {token_text}\n"
        "Action: no execution. Require human review or a lower-risk scenario."
    )


def _trinity_blocked_response(state: dict) -> str:
    report = state.get("trinity_report") or "Trinity deliberation blocked this candidate."
    return (
        "[F51 Trinity Council] BLOCKED\n\n"
        f"{report}\n\n"
        "Action: no execution. Bob is bypassed because Genie and Deep reached a unanimous block."
    )


def _sdca_error_response(state: dict) -> str:
    firewall = state.get("sdca_firewall") if isinstance(state.get("sdca_firewall"), dict) else {}
    detail = firewall.get("error") or "SDCA firewall missing or failed for this ticker."
    return (
        "[F51 Cognitive Risk Firewall] BLOCKED\n\n"
        f"{detail}\n\n"
        "Action: no execution. Organ ERROR never becomes ALLOW."
    )


def render_blocked_answer(state: dict) -> str:
    """Deterministic blocked text. Used by the respond_blocked graph node."""
    if state.get("trinity_blocked"):
        return _trinity_blocked_response(state)
    reason = sdca_block_reason(state)
    if reason == "sdca_blocked" or state.get("sdca_blocked"):
        return _sdca_blocked_response(state)
    if reason in {"sdca_error", "sdca_missing"}:
        return _sdca_error_response(state)
    return VAGUE_FINANCIAL_RESPONSE


async def node_blocked(state: dict) -> dict:
    """Respond to blocked requests with a polite scope-request message."""
    writer = get_stream_writer()
    content = render_blocked_answer(state)
    writer(
        {
            "type": "PIPELINE_STEP",
            "run_id": state.get("run_id", ""),
            "step": "respond_blocked",
            "status": "started",
        }
    )
    writer({"type": "CHUNK", "content": content})
    writer(
        {
            "type": "PIPELINE_STEP",
            "run_id": state.get("run_id", ""),
            "step": "respond_blocked",
            "status": "completed",
        }
    )
    return {"final": content}
