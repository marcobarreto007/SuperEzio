#!/usr/bin/env python
"""
SuperEzio Decision Trace Viewer.

Blame report no terminal para debugging de pipeline runs.
"""

import argparse
import json
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from core.audit.decision_trace import DecisionTraceLogger, get_agent_stats
from core.paths import resolve_project_path


def print_blame_report(run_id: str, tracer: DecisionTraceLogger) -> None:
    """Print human-readable blame report."""
    report = tracer.blame_report(run_id)
    entries = report.get("entries", [])

    print(f"=== BLAME REPORT — run_id: {run_id} ===")
    print()

    if not entries:
        print("No traces found.")
        return

    # Summary
    summary = report.get("summary", {})
    print(f"## Summary")
    print(f"- Total events: {summary.get('total_events', 0)}")
    print(f"- Completed: {summary.get('completed_nodes', 0)}")
    print(f"- Skipped: {summary.get('skipped_nodes', 0)}")
    print(f"- Errors: {summary.get('error_nodes', 0)}")
    print(f"- Blockers: {summary.get('blockers', 0)}")
    print()

    # Pipeline flow
    print("## Pipeline Flow (com latência)")
    for i, entry in enumerate([e for e in entries if e.get("phase") == "end"], 1):
        decision = entry.get("decision", "N/A")
        elapsed = entry.get("elapsed_ms", 0)
        status = entry.get("status", "unknown")
        agent = entry.get("agent", "unknown")

        print(f"{i}. {entry.get('node', 'unknown')} ({agent}) — {elapsed}ms")
        print(f"   → {decision} ({status})")

        if entry.get("reason"):
            reason = entry.get("reason", "")
            print(f"   Razão: {reason[:80]}")

        if entry.get("errors"):
            errors = entry.get("errors", [])
            if isinstance(errors, str):
                errors = json.loads(errors)
            if errors:
                print(f"   → ⚠️ Errors: {', '.join(str(e) for e in errors[:2])}")

        if entry.get("overrides"):
            ov = entry.get("overrides", {})
            if isinstance(ov, str):
                ov = json.loads(ov)
            if isinstance(ov, dict):
                overridden = ov.get("overridden_node", "N/A")
                print(f"   → ⚠️ OVERRIDE: Discordou de {overridden}")

    print()

    # Blockers
    blockers = report.get("blockers", [])
    if blockers:
        print("## Blockers")
        for b in blockers:
            print(f"- {b.get('node', 'unknown')}: {b.get('decision', 'N/A')}")
            if b.get("reason"):
                print(f"  {b.get('reason', '')[:80]}")
        print()

    # Slowest nodes
    slowest = report.get("slowest_nodes", [])
    if slowest:
        print("## Slowest Nodes")
        for s in slowest:
            print(f"- {s.get('node', 'unknown')}: {s.get('elapsed_ms', 0)}ms")
        print()

    # Agent stats
    agent_stats = report.get("agent_stats", [])
    if agent_stats:
        print("## Agent Performance (esta run)")
        for stat in agent_stats:
            print(f"- {stat['agent']}: avg {stat['avg_latency_ms']:.0f}ms ({stat['calls']} calls)")
        print()


def print_agent_stats(agent: str, days: int) -> None:
    """Print agent performance stats."""
    stats = get_agent_stats(agent, days)
    print(f"=== Agent Stats — {agent} (últimos {days} dias) ===")
    print(f"- Calls: {stats['calls']}")
    print(f"- Avg latency: {stats['avg_latency_ms']:.0f}ms")
    print(f"- Error rate: {stats['error_rate']:.1%}")
    print(f"- Avg confidence: {stats['avg_confidence']:.2f}")


def main():
    parser = argparse.ArgumentParser(description="SuperEzio Decision Trace Viewer")
    sub = parser.add_subparsers(dest="command", help="Command to run")

    # Blame report command
    blame = sub.add_parser("blame", help="Show blame report for a run")
    blame.add_argument("run_id", help="Run ID to inspect")

    # Agent stats command
    stats = sub.add_parser("stats", help="Show agent performance stats")
    stats.add_argument("agent", help="Agent name (e.g., bob_qwen_local)")
    stats.add_argument("--days", type=int, default=7, help="Days to look back (default: 7)")

    # List runs command
    ls = sub.add_parser("ls", help="List recent runs")

    args = parser.parse_args()

    tracer = DecisionTraceLogger()

    if args.command == "blame":
        print_blame_report(args.run_id, tracer)
    elif args.command == "stats":
        print_agent_stats(args.agent, args.days)
    elif args.command == "ls":
        traces_dir = resolve_project_path("runtime/traces")
        print(f"=== Recent Runs ===")
        print(f"Traces dir: {traces_dir}")
        if traces_dir.exists():
            for path in sorted(traces_dir.glob("decision_trace_*.jsonl"))[:5]:
                print(f"- {path.name}")
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
