"""Peça 5: rótulo reutiliza a barreira tripla já existente. Não a reescreve."""

from __future__ import annotations

from core.heart.labels import label_with_existing_barrier
from core.trading.triple_barrier import evaluate_triple_barrier


def test_heart_labels_call_the_existing_evaluator(monkeypatch):
    called = {}

    def fake_evaluate(*args, **kwargs):
        called["args"] = args
        called["kwargs"] = kwargs
        return {"hit": "profit", "ok": True}

    monkeypatch.setattr("core.heart.labels.evaluate_triple_barrier", fake_evaluate)
    result = label_with_existing_barrier(
        bars=[{"high": 11, "low": 9, "close": 10, "open": 10}],
        side="long",
        stop_loss_price=9.0,
        take_profit_price=12.0,
        time_horizon_bars=5,
    )
    assert called, "heart must reuse core.trading.triple_barrier"
    assert result == {"hit": "profit", "ok": True}


def test_evaluator_is_the_same_function_object():
    from core.heart import labels

    assert labels.evaluate_triple_barrier is evaluate_triple_barrier
