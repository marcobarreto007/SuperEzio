"""
Tests for DecisionTraceLogger.
"""

import json
import tempfile
from pathlib import Path

import pytest

from core.audit.decision_trace import (
    DecisionTraceLogger,
    TraceToken,
    _ensure_db_table,
    _write_trace_to_db,
    get_agent_stats,
)


@pytest.fixture
def temp_tracer(tmp_path: Path) -> DecisionTraceLogger:
    """Create tracer with temp output dir."""
    return DecisionTraceLogger(output_dir=tmp_path / "traces")


@pytest.fixture
def temp_db(tmp_path: Path) -> Path:
    """Create temp database path."""
    return tmp_path / "investor.db"


def test_start_node(temp_tracer: DecisionTraceLogger) -> None:
    """start_node returns a TraceToken."""
    token = temp_tracer.start_node("test_run", "test_node")
    assert isinstance(token, TraceToken)
    assert token.run_id == "test_run"
    assert token.node == "test_node"
    assert token.trace_id


def test_end_node(temp_tracer: DecisionTraceLogger) -> None:
    """end_node writes entry."""
    token = temp_tracer.start_node("test_run", "test_node", agent="test_agent")
    entry = temp_tracer.end_node(
        token,
        status="completed",
        decision="BUY",
        reason="Good setup",
        agent="test_agent",
        confidence=0.8,
    )
    assert entry["decision"] == "BUY"
    assert entry["status"] == "completed"
    assert entry["elapsed_ms"] >= 0


def test_skip_node(temp_tracer: DecisionTraceLogger) -> None:
    """skip_node writes skipped entry."""
    entry = temp_tracer.skip_node("test_run", "test_node", reason="Not needed")
    assert entry["status"] == "skipped"
    assert entry["decision"] == "SKIP"


def test_error_node(temp_tracer: DecisionTraceLogger) -> None:
    """error_node writes error entry."""
    token = temp_tracer.start_node("test_run", "test_node")
    exc = ValueError("Test error")
    entry = temp_tracer.error_node(token, exc)
    assert entry["status"] == "error"
    assert "Test error" in entry["reason"]


def test_load_entries(temp_tracer: DecisionTraceLogger) -> None:
    """load_entries retrieves all entries for a run."""
    token = temp_tracer.start_node("test_run", "node1")
    temp_tracer.end_node(token, decision="BUY")
    token = temp_tracer.start_node("test_run", "node2")
    temp_tracer.end_node(token, decision="SELL")

    entries = temp_tracer.load_entries("test_run")
    assert len(entries) == 4  # 2 starts + 2 ends


def test_blame_report(temp_tracer: DecisionTraceLogger) -> None:
    """blame_report generates summary."""
    token = temp_tracer.start_node("test_run", "node1", agent="agent1")
    temp_tracer.end_node(token, status="completed", decision="BUY", agent="agent1")
    token = temp_tracer.start_node("test_run", "node2", agent="agent2")
    temp_tracer.end_node(token, status="error", decision="ERROR", agent="agent2")

    report = temp_tracer.blame_report("test_run")
    assert report["run_id"] == "test_run"
    assert report["summary"]["total_events"] == 4
    assert report["summary"]["error_nodes"] == 1
    assert len(report["blockers"]) == 1
    assert len(report["slowest_nodes"]) <= 5


def test_blame_report_with_overrides(temp_tracer: DecisionTraceLogger) -> None:
    """blame_report includes overrides."""
    token = temp_tracer.start_node("test_run", "node1", agent="agent1")
    temp_tracer.end_node(
        token,
        status="completed",
        decision="WAIT",
        agent="agent1",
        overrides={"overridden_node": "expert_fundamental", "reason": "Social signal weak"},
    )

    report = temp_tracer.blame_report("test_run")
    assert len(report["overrides"]) == 1
    assert report["overrides"][0]["overrides"]["overridden_node"] == "expert_fundamental"


def test_db_table_creation(temp_db: Path) -> None:
    """_ensure_db_table creates the table."""
    _ensure_db_table(temp_db)
    assert temp_db.exists()

    # Check table exists
    import sqlite3
    conn = sqlite3.connect(temp_db)
    cursor = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='decision_traces'"
    )
    assert cursor.fetchone() is not None
    conn.close()


def test_write_trace_to_db(temp_db: Path) -> None:
    """_write_trace_to_db inserts a row."""
    _write_trace_to_db(
        db_path=temp_db,
        trace_id="test123",
        run_id="run456",
        node="test_node",
        agent="test_agent",
        latency_ms=123,
        decision="BUY",
        confidence=0.8,
        evidence_refs=["ev1", "ev2"],
        errors=["err1"],
        overrides=None,
        input_summary="test input",
        output_summary="test output",
    )

    import sqlite3
    conn = sqlite3.connect(temp_db)
    cursor = conn.execute("SELECT * FROM decision_traces WHERE trace_id=?", ("test123",))
    row = cursor.fetchone()
    assert row is not None
    assert row[2] == "run456"  # run_id (0=id, 1=trace_id, 2=run_id, 3=session_id, 4=node, 5=agent, 6=timestamp, 7=latency_ms, 8=decision, 9=confidence)
    assert row[5] == "test_agent"  # agent
    assert row[8] == "BUY"  # decision
    conn.close()


def test_get_agent_stats(temp_db: Path) -> None:
    """get_agent_stats returns correct stats."""
    # Insert 3 traces for agent1, 1 for agent2
    for i in range(3):
        _write_trace_to_db(
            db_path=temp_db,
            trace_id=f"t{i}",
            run_id="run1",
            node="node1",
            agent="agent1",
            latency_ms=100 + i * 10,
            decision="BUY",
            confidence=0.7 + i * 0.1,
            evidence_refs=[],
            errors=[] if i < 2 else ["error1"],
            overrides=None,
            input_summary="",
            output_summary="",
        )
    _write_trace_to_db(
        db_path=temp_db,
        trace_id="t3",
        run_id="run1",
        node="node2",
        agent="agent2",
        latency_ms=200,
        decision="SELL",
        confidence=0.6,
        evidence_refs=[],
        errors=[],
        overrides=None,
        input_summary="",
        output_summary="",
    )

    stats = get_agent_stats("agent1", days=7, db_path=temp_db)
    assert stats["agent"] == "agent1"
    assert stats["calls"] == 3
    assert stats["avg_latency_ms"] > 0
    assert stats["error_rate"] == 1 / 3
    assert stats["avg_confidence"] > 0
