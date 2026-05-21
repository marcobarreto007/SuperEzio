#!/usr/bin/env python3
"""Append signal_emit records from a captured /task/submit NDJSON file."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

try:
    from .collector import append_jsonl, build_emit_record, parse_ndjson
    from .policy import load_policy, project_root
except ImportError:
    from collector import append_jsonl, build_emit_record, parse_ndjson
    from policy import load_policy, project_root


def main() -> int:
    root = project_root()
    parser = argparse.ArgumentParser(description="Append signal_emit from NDJSON stream capture")
    parser.add_argument(
        "ndjson",
        type=Path,
        nargs="?",
        help="Path to NDJSON file (default: stdin)",
    )
    parser.add_argument(
        "--policy",
        type=Path,
        default=root / "docs" / "signals" / "official_signal_policy.v1.json",
        help="Official signal policy JSON",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=root / "data" / "signals" / "emitted.jsonl",
        help="Output JSONL ledger",
    )
    parser.add_argument(
        "--traces",
        type=Path,
        default=root / "data" / "traces",
        help="Collector trace directory",
    )
    parser.add_argument(
        "--archive",
        type=Path,
        default=root / "data" / "signals" / "raw_ndjson",
        help="Archive raw NDJSON copies",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print record JSON without writing",
    )
    parser.add_argument(
        "--user-excerpt",
        type=str,
        default="",
        help="Optional user message excerpt for audit",
    )
    args = parser.parse_args()

    if args.ndjson:
        text = args.ndjson.read_text(encoding="utf-8")
        raw_path = args.ndjson
    else:
        text = sys.stdin.read()
        raw_path = None

    policy = load_policy(args.policy)
    run = parse_ndjson(text)
    if args.user_excerpt:
        run.user_message_excerpt = args.user_excerpt

    archived: Path | None = None
    if raw_path and not args.dry_run:
        args.archive.mkdir(parents=True, exist_ok=True)
        archived = args.archive / raw_path.name
        if not archived.exists():
            archived.write_text(text, encoding="utf-8")

    record = build_emit_record(
        run,
        policy,
        trace_dir=args.traces,
        raw_ndjson_path=archived or raw_path,
    )

    if args.dry_run:
        print(json.dumps(record, indent=2, ensure_ascii=False))
        return 0

    append_jsonl(args.out, record)
    print(
        json.dumps(
            {
                "written": str(args.out),
                "signal_id": record["signal_id"],
                "status": record["status"],
                "action": record["action"],
                "ticker": record["ticker"],
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
