"""Safety valve node — blocks vague/unscoped financial requests."""

from langgraph.config import get_stream_writer

VAGUE_FINANCIAL_RESPONSE = (
    "[SuperEzio Trust OS] I cannot provide investment recommendations "
    "without a specific ticker and a clear research question.\n\n"
    "Please ask again with:\n"
    "- A ticker (e.g., AAPL, ENB.TO, HIVE.V)\n"
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


async def node_blocked(state: dict) -> dict:
    """Respond to blocked requests with a polite scope-request message."""
    writer = get_stream_writer()
    content = (
        _sdca_blocked_response(state) if state.get("sdca_blocked") else VAGUE_FINANCIAL_RESPONSE
    )
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
