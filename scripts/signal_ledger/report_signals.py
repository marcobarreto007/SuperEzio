#!/usr/bin/env python3
"""Report metrics from signal ledger (emitted + resolutions)."""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

_PKG = Path(__file__).resolve().parent
if str(_PKG) not in sys.path:
    sys.path.insert(0, str(_PKG))

from policy import project_root


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        rows.append(json.loads(line))
    return rows


def main() -> int:
    root = project_root()
    parser = argparse.ArgumentParser(description="Signal ledger metrics report")
    parser.add_argument(
        "--emitted",
        type=Path,
        default=root / "data" / "signals" / "emitted.jsonl",
    )
    parser.add_argument(
        "--resolutions",
        type=Path,
        default=root / "data" / "signals" / "resolutions.jsonl",
    )
    parser.add_argument("--json", action="store_true", help="Machine-readable output")
    args = parser.parse_args()

    emitted = load_jsonl(args.emitted)
    resolutions = load_jsonl(args.resolutions)
    res_by_id = {r["signal_id"]: r for r in resolutions if r.get("signal_id")}

    counts: dict[str, int] = defaultdict(int)
    for e in emitted:
        counts[str(e.get("status") or "unknown")] += 1

    official = [e for e in emitted if e.get("status") == "official"]
    resolved_official = [e for e in official if e.get("signal_id") in res_by_id]

    hits = 0
    returns: list[float] = []
    by_action: dict[str, dict[str, int]] = defaultdict(lambda: {"n": 0, "hits": 0})

    for e in resolved_official:
        sid = e["signal_id"]
        r = res_by_id[sid]
        action = str(e.get("action") or "?")
        by_action[action]["n"] += 1
        if r.get("hit"):
            hits += 1
            by_action[action]["hits"] += 1
        if r.get("return_pct") is not None:
            returns.append(float(r["return_pct"]))

    n_res = len(resolved_official)
    hit_rate = (hits / n_res * 100) if n_res else None
    avg_ret = (sum(returns) / len(returns)) if returns else None

    report = {
        "emitted_total": len(emitted),
        "emitted_by_status": dict(counts),
        "official_count": len(official),
        "resolved_official": n_res,
        "open_official": len(official) - n_res,
        "hit_rate_pct": round(hit_rate, 2) if hit_rate is not None else None,
        "avg_return_pct": round(avg_ret, 4) if avg_ret is not None else None,
        "by_action": {
            k: {
                "resolved": v["n"],
                "hits": v["hits"],
                "hit_rate_pct": round(v["hits"] / v["n"] * 100, 2) if v["n"] else None,
            }
            for k, v in by_action.items()
        },
        "policy_versions": sorted({str(e.get("policy_version")) for e in emitted if e.get("policy_version")}),
    }

    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
        return 0

    print("=== SuperEzio Signal Ledger ===")
    print(f"Emitted total:     {report['emitted_total']}")
    for status, n in sorted(report["emitted_by_status"].items()):
        print(f"  {status}: {n}")
    print(f"Official:          {report['official_count']}")
    print(f"Resolved official: {report['resolved_official']}")
    print(f"Open official:     {report['open_official']}")
    if report["hit_rate_pct"] is not None:
        print(f"Hit rate:          {report['hit_rate_pct']}%")
    if report["avg_return_pct"] is not None:
        print(f"Avg return:        {report['avg_return_pct']}%")
    if report["by_action"]:
        print("By action:")
        for action, stats in report["by_action"].items():
            print(f"  {action}: resolved={stats['resolved']} hit_rate={stats['hit_rate_pct']}%")
    if report["policy_versions"]:
        print(f"Policy versions:   {', '.join(report['policy_versions'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
