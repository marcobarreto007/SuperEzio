"""Bob Consciousness — Self-aware, self-healing agent body.

Bob monitors every component of his own system. When something breaks,
he feels pain, diagnoses the problem, and tries to heal himself.

Quick start:
    from core.bob_consciousness import bob_body_scan, start_ans
    start_ans()  # background health monitor
    report = bob_body_scan()  # on-demand health check
"""

from .body import (
    BobsBody, Organ, OrganCategory, PainLevel, PainEvent, SystemMode,
    get_bobs_body, bob_body_scan, bob_pain_summary,
)
from .autonomic import (
    AutonomicNervousSystem, get_ans, start_ans, stop_ans,
)

__all__ = [
    "BobsBody", "Organ", "OrganCategory", "PainLevel", "PainEvent", "SystemMode",
    "get_bobs_body", "bob_body_scan", "bob_pain_summary",
    "AutonomicNervousSystem", "get_ans", "start_ans", "stop_ans",
]

def check_man_at_work_guard(operation: str = "trading") -> tuple[bool, str]:
    """Convenience wrapper - check if operation is allowed in current mode."""
    return get_bobs_body().check_man_at_work_guard(operation)
