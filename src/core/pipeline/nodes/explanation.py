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

    ceo_text = state.get("final", "")

    try:
        from ...explanation import ExplainEngine

        explainer = ExplainEngine()
        async for chunk in explainer.stream(verdict, ceo_text=ceo_text):
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
