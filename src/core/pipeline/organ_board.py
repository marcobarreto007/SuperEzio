"""C4 organ board — SDCA fail-closed as a graph edge.

The mega-nó still computes the firewall. This module only decides whether
the turn may reach Trinity/Bob. Observe (flag off) logs C4_WOULD_BLOCK and
keeps the legacy edge to trinity.
"""

from __future__ import annotations

import logging
from typing import Any, Literal

from core.evidence.arch_flags import is_arch_c4_enabled

logger = logging.getLogger(__name__)

ROUTE_TRINITY = "trinity"
ROUTE_BLOCKED = "respond_blocked"


def _has_ticker(state: dict[str, Any]) -> bool:
    ticker = str(state.get("ticker") or "").strip()
    if ticker:
        return True
    data = state.get("data")
    return bool(isinstance(data, dict) and str(data.get("ticker") or "").strip())


def _errors_mention_sdca(state: dict[str, Any]) -> bool:
    for item in state.get("errors") or []:
        text = str(item)
        if "sdca_firewall" in text:
            return True
    return False


def sdca_block_reason(state: dict[str, Any]) -> str | None:
    """Why the board would fail-close. None means continue. No ticker never blocks."""
    if not _has_ticker(state):
        return None
    if state.get("sdca_blocked"):
        return "sdca_blocked"
    firewall = state.get("sdca_firewall")
    if isinstance(firewall, dict) and firewall:
        if firewall.get("error"):
            return "sdca_error"
        if firewall.get("decision") == "BLOCK":
            return "sdca_blocked"
        return None
    if _errors_mention_sdca(state):
        return "sdca_error"
    return "sdca_missing"


def route_after_organ_board(state: dict[str, Any]) -> Literal["trinity", "respond_blocked"]:
    reason = sdca_block_reason(state)
    if reason:
        logger.info("C4_WOULD_BLOCK reason=%s", reason)
    if is_arch_c4_enabled() and reason:
        return ROUTE_BLOCKED
    return ROUTE_TRINITY
