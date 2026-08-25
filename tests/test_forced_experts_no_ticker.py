"""O gate de ferramentas forcadas delibera experts para pergunta sem ticker."""

from __future__ import annotations

from src.core.pipeline.nodes.agent import (
    _forced_tool_call_before_final,
    _looks_financially_substantive,
)


def test_allocation_question_is_financially_substantive() -> None:
    message = (
        "Moro no Canada, tenho CAD 25.000 para alocar entre reserva de "
        "emergencia, dividas, ETFs, equipamento e educacao."
    )
    assert _looks_financially_substantive(message) is True


def test_smalltalk_is_not_financially_substantive() -> None:
    assert _looks_financially_substantive("oi bob") is False
    assert _looks_financially_substantive("como vai?") is False


def test_gate_forces_run_experts_for_no_ticker_allocation() -> None:
    state = {
        "message": "Tenho CAD 25.000 para alocar entre reserva e ETFs. De um framework.",
        "route": "general",
        "intent": "general",
        "ticker": "",
        "allowed_tools": ["final_answer", "run_experts", "market_scan"],
        "executed_tools": [],
        "scanner_allowed": True,
    }
    forced = _forced_tool_call_before_final(state)
    assert forced is not None
    assert forced["tool"] == "run_experts"


def test_gate_does_not_force_experts_twice() -> None:
    state = {
        "message": "Tenho CAD 25.000 para alocar entre reserva e ETFs.",
        "route": "general",
        "intent": "general",
        "ticker": "",
        "allowed_tools": ["final_answer", "run_experts"],
        "executed_tools": ["run_experts"],
        "expert_results": [{"ok": True}],
        "scanner_allowed": True,
    }
    assert _forced_tool_call_before_final(state) is None


def test_gate_does_not_force_for_plain_smalltalk() -> None:
    state = {
        "message": "oi bob",
        "route": "smalltalk",
        "intent": "smalltalk",
        "ticker": "",
        "allowed_tools": ["final_answer", "run_experts"],
        "executed_tools": [],
        "scanner_allowed": False,
    }
    assert _forced_tool_call_before_final(state) is None
