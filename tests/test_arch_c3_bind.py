"""C3 bind — Bob reads the frozen snapshot; CENSORSHIP_SKIPPED cannot skip."""

from __future__ import annotations

from core.evidence.arch_flags import is_arch_c3_enabled
from core.evidence.snapshot import bind_answer_to_snapshot
from core.pipeline.nodes.agent import _trust_unbound_answer
from core.pipeline.nodes.observation_builder import _inject_evidence

_DATA_STATE = {
    "math_report": {"summary": {"latest_price": 190.5}},
    "data": {"ticker": "AAPL", "price": {"price": 190.5}},
}


def _frozen_snapshot() -> dict:
    return {
        "frozen": True,
        "numbers": {
            "price": {
                "value": 190.5,
                "unit": "quote",
                "formula_id": "math_hub.price_series",
                "provenance": ["price"],
            },
            "rsi": {
                "value": 55.0,
                "unit": "index",
                "formula_id": "math_hub.rsi14",
                "provenance": ["ohlcv"],
            },
        },
    }


def test_c3_flag_default_on(monkeypatch) -> None:
    monkeypatch.delenv("SUPEREZIO_ARCH_C3", raising=False)
    assert is_arch_c3_enabled() is True
    from core.config.settings import Settings

    assert Settings.model_fields["superezio_arch_c3"].default is True
    monkeypatch.setenv("SUPEREZIO_ARCH_C3", "0")
    assert is_arch_c3_enabled() is False


def test_c3_injects_snapshot_frozen_before_math_prompt(monkeypatch) -> None:
    monkeypatch.setenv("SUPEREZIO_ARCH_C3", "1")
    observations: list[str] = []
    _inject_evidence(
        {
            "snapshot": _frozen_snapshot(),
            "math_prompt": "RSI=99.99 from MathHub (do not treat as citation source)",
        },
        observations,
    )
    frozen_idx = next(i for i, item in enumerate(observations) if "SNAPSHOT FROZEN" in item)
    math_idx = next(i for i, item in enumerate(observations) if "Math Analysis" in item)
    assert frozen_idx < math_idx
    assert "rsi=55.0" in observations[frozen_idx]
    assert "190.5" in observations[frozen_idx]


def test_c3_off_does_not_inject_frozen_block(monkeypatch) -> None:
    monkeypatch.setenv("SUPEREZIO_ARCH_C3", "0")
    observations: list[str] = []
    _inject_evidence({"snapshot": _frozen_snapshot(), "math_prompt": "RSI=99.99"}, observations)
    joined = "\n".join(observations)
    assert "SNAPSHOT FROZEN" not in joined


def test_trust_unbound_answer_false_when_c3_on_even_with_data(monkeypatch) -> None:
    monkeypatch.setenv("SUPEREZIO_ARCH_C3", "1")
    assert _trust_unbound_answer(_DATA_STATE) is False


def test_trust_unbound_answer_true_when_c3_off_and_has_data(monkeypatch) -> None:
    monkeypatch.setenv("SUPEREZIO_ARCH_C3", "0")
    assert _trust_unbound_answer(_DATA_STATE) is True
    assert _trust_unbound_answer({"message": "hello"}) is False


def test_bind_allows_snapshot_price() -> None:
    content = "AAPL last print $190.5 with RSI 55.00."
    assert bind_answer_to_snapshot(content, _frozen_snapshot()) == content


def test_bind_rejects_price_absent_from_snapshot() -> None:
    raw = "AAPL trades at $999.99 right now."
    bound = bind_answer_to_snapshot(raw, _frozen_snapshot())
    assert bound != raw
    assert not bound.startswith("AAPL trades at $999.99")
    assert "SNAPSHOT BIND REJECTED" in bound
    assert "SNAPSHOT FROZEN" in bound
    assert "$999.99" in bound


def test_bind_passthrough_without_snapshot() -> None:
    content = "Casual hello with $999.99 in the text."
    assert bind_answer_to_snapshot(content, None) == content
    assert bind_answer_to_snapshot(content, {"frozen": False, "numbers": {}}) == content
