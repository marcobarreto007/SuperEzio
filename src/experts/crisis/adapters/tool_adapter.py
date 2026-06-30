"""Tool adapter for the active CrisisMath expert."""

from __future__ import annotations

from typing import Any

from experts.crisis.contracts.schemas import CrisisInput
from experts.crisis.expert.crisis_expert import CrisisMathExpert


def tool_analyze_systemic_risk(payload: dict[str, Any] | None = None, **kwargs: Any) -> dict[str, Any]:
    """Run CrisisMath from a tool-style dict payload."""
    data = dict(payload or {})
    data.update(kwargs)
    report = CrisisMathExpert().analyze(CrisisInput(**data))
    return report.model_dump(mode="json")
