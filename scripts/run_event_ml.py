"""Run isolated shadow experiment; CSV must follow event_dataset OHLCV schema."""

import argparse
import hashlib
import io
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pandas as pd

from core.ml.event_experiment import ExperimentConfig, run_experiment, write_artifacts


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--horizon", type=int, default=14)
    parser.add_argument("--stop-pct", type=float, default=0.02)
    parser.add_argument("--profit-multiple", type=float, default=2.5)
    parser.add_argument("--cost-bps", type=float, default=50)
    parser.add_argument("--embargo-days", type=int, default=1)
    args = parser.parse_args()
    try:
        raw = args.input.read_bytes()
        input_hash = hashlib.sha256(raw).hexdigest()
        manifest_path = args.input.with_name("input_manifest.json")
        manifest = (
            json.loads(manifest_path.read_text(encoding="utf-8-sig"))
            if manifest_path.exists()
            else None
        )
        if manifest is not None and (
            not isinstance(manifest, dict) or manifest.get("input_sha256") != input_hash
        ):
            raise ValueError("input_manifest.json input_sha256 does not match input CSV")
        config = ExperimentConfig(
            horizon=args.horizon,
            stop_pct=args.stop_pct,
            profit_multiple=args.profit_multiple,
            cost_bps=args.cost_bps,
            embargo_days=args.embargo_days,
        )
        report, predictions = run_experiment(
            pd.read_csv(io.BytesIO(raw)), config=config, input_sha256=input_hash
        )
        report["source_manifest"] = manifest
        report["source_manifest_status"] = (
            "hash_matched_not_independently_verified" if manifest else "unverified"
        )
    except (ValueError, OSError) as exc:
        report = {
            "schema_version": 1,
            "status": "invalid_input",
            "research_only": True,
            "broker_approval": False,
            "alpha_claim": False,
            "reasons": [str(exc)],
            "metrics": {},
        }
        predictions = pd.DataFrame()
    write_artifacts(report, predictions, args.output)
    print(
        json.dumps(
            {
                "status": report["status"],
                "research_only": True,
                "output": str(args.output.resolve()),
                "reasons": report.get("reasons", []),
            }
        )
    )
    return 0 if report["status"] == "evaluated" else 2


if __name__ == "__main__":
    raise SystemExit(main())
