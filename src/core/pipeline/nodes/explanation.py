"""Explanation node — streams interpretability layer for F51 verdict."""

from langgraph.config import get_stream_writer


async def node_explanation(state: dict) -> dict:
    """Generate explanation for the F51 verdict using ExplainEngine."""
    writer = get_stream_writer()
    run_id = state.get("run_id", "")

    if state.get("explanation"):
        writer(
            {
                "type": "PIPELINE_STEP",
                "run_id": run_id,
                "step": "explanation",
                "status": "skipped_duplicate",
            }
        )
        return {}

    writer(
        {
            "type": "PIPELINE_STEP",
            "run_id": run_id,
            "step": "explanation",
            "status": "started",
        }
    )

    verdict = state.get("f51_verdict") or {}
    # CONTRACT: explanation is an interpretability layer for the deterministic
    # F51 verdict ONLY — it is not a polish step for the agent's answer. The
    # agent already streamed the final answer (state["final"]) and the user-
    # facing response is complete without this node (the ExplainEngine itself
    # appends "the Decision Room brief above remains the controlling answer").
    # With no verdict (ticker-less route, or F51 errored/skipped upstream)
    # there is nothing to explain: skip instead of fabricating a nurse note.
    if not verdict:
        writer(
            {
                "type": "PIPELINE_STEP",
                "run_id": run_id,
                "step": "explanation",
                "status": "skipped",
            }
        )
        return {"explanation": ""}

    agent_text = state.get("final", "")

    try:
        from ...explanation import ExplainEngine

        explainer = ExplainEngine()
        async for chunk in explainer.stream(verdict, agent_text=agent_text):
            writer({"type": "EXPLANATION_CHUNK", "content": chunk})

        writer(
            {
                "type": "PIPELINE_STEP",
                "run_id": run_id,
                "step": "explanation",
                "status": "completed",
            }
        )
        return {"explanation": "(streamed)"}

    except Exception as exc:
        writer(
            {
                "type": "ERROR",
                "run_id": run_id,
                "detail": f"explanation: {exc}",
            }
        )
        writer(
            {
                "type": "PIPELINE_STEP",
                "run_id": run_id,
                "step": "explanation",
                "status": "error",
            }
        )
        return {
            "explanation": "",
            "errors": state.get("errors", []) + [f"explanation:{exc}"],
        }
