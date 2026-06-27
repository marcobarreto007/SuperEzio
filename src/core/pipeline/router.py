"""Trade Router — re-exports from agent.py (Phase 1 facade).

Trade decision, paper orders, safety gates, allocation logic.
Import from here instead of agent.py to reduce coupling.

Usage:
    from core.pipeline.router import _build_trade_order_context
"""

from __future__ import annotations

from .nodes.agent import (
    _build_submit_paper_order_call,
    _build_trade_order_context,
    _compute_model_confidence,
    _estimate_share_quantity,
    _extract_account_reference,
    _extract_requested_allocation,
    _format_money_amount,
    _is_paper_training_request,
    _paper_order_execution_answer,
    _paper_order_explicitly_blocked,
    _paper_order_submit_enabled,
    _should_use_decisive_mode,
    _trade_safety_gate_failures,
)

__all__ = [
    "_build_submit_paper_order_call",
    "_build_trade_order_context",
    "_compute_model_confidence",
    "_estimate_share_quantity",
    "_extract_account_reference",
    "_extract_requested_allocation",
    "_format_money_amount",
    "_is_paper_training_request",
    "_paper_order_execution_answer",
    "_paper_order_explicitly_blocked",
    "_paper_order_submit_enabled",
    "_should_use_decisive_mode",
    "_trade_safety_gate_failures",
]
