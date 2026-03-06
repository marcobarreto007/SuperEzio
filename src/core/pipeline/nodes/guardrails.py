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


async def node_blocked(state: dict) -> dict:
    """Respond to blocked requests with a polite scope-request message."""
    writer = get_stream_writer()
    writer(
        {
            "type": "PIPELINE_STEP",
            "run_id": state.get("run_id", ""),
            "step": "respond_blocked",
            "status": "started",
        }
    )
    writer({"type": "CHUNK", "content": VAGUE_FINANCIAL_RESPONSE})
    writer(
        {
            "type": "PIPELINE_STEP",
            "run_id": state.get("run_id", ""),
            "step": "respond_blocked",
            "status": "completed",
        }
    )
    return {"final": VAGUE_FINANCIAL_RESPONSE}
