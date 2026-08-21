"""Regression: synthetic test/probe run ids must never reach the decision ledger."""

from __future__ import annotations

import sqlite3

import core.audit.decision_trace as decision_trace
from core.audit.decision_trace import DecisionTraceLogger, is_synthetic_run_id


def test_synthetic_run_id_detection():
    synthetic = [
        "agent-full-access-no-prescan-test",
        "auto-full-analysis-test",
        "auto-skip-market-stack-test",
        "node1",
        "node2",
        "test_node",
        "contract_test",
        "pytest-abc",
        "probe-x",
        "benchmark-run",
        "unknown",
        "",
        None,
    ]
    real = ["run456", "run1", "bob-a608c9ba-f082-49cc-9cca-c3e3f247974d", "7f54d6b589c5"]
    for rid in synthetic:
        assert is_synthetic_run_id(rid) is True, f"{rid!r} should be synthetic"
    for rid in real:
        assert is_synthetic_run_id(rid) is False, f"{rid!r} should be real"


def test_synthetic_run_does_not_reach_sqlite(tmp_path, monkeypatch):
    db = tmp_path / "guard-test.sqlite3"
    monkeypatch.setattr(decision_trace, "DB_PATH", db)

    logger = DecisionTraceLogger(output_dir=tmp_path / "traces")
    token = logger.start_node("auto-full-analysis-test", "guardrail.cost_guard")
    logger.end_node(token, decision="ALLOW")

    logger.start_node("bob-real-run-1", "guardrail.cost_guard")
    logger.end_node(logger.start_node("bob-real-run-1", "guardrail.cost_guard"), decision="ALLOW")

    conn = sqlite3.connect(db)
    rows = conn.execute("SELECT run_id FROM decision_traces").fetchall()
    conn.close()
    run_ids = [row[0] for row in rows]
    assert "auto-full-analysis-test" not in run_ids
    assert run_ids == ["bob-real-run-1"]
