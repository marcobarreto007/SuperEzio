"""Evaluate predictive investment quality on real, diversified market history.

This is deliberately separate from answer-text QA.  It downloads observed 5Y OHLCV,
trains only on the chronological prefix, and scores an untouched future holdout against
climatology and buy-and-hold.  A model abstention is recorded as a failure to qualify,
never replaced with a neutral or fabricated prediction.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from statistics import fmean, median
from typing import Any, Iterable

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from data.yfinance_provider import YFinanceProvider  # noqa: E402
from experts.technical_neural.expert.neural_expert import TechnicalNeuralExpert  # noqa: E402


@dataclass(frozen=True)
class AssetCase:
    ticker: str
    asset_class: str


# Pre-registered before downloading data.  AAPL is intentionally absent: no single
# company is allowed to stand in for investment quality or market coverage.
DEFAULT_UNIVERSE = (
    AssetCase("SPY", "us_large_cap"),
    AssetCase("QQQ", "us_growth"),
    AssetCase("IWM", "us_small_cap"),
    AssetCase("RY.TO", "canadian_equity"),
    AssetCase("XIU.TO", "canadian_etf"),
    AssetCase("GLD", "gold"),
    AssetCase("TLT", "long_treasury"),
    AssetCase("BTC-USD", "crypto"),
)
DEFAULT_HORIZONS = (1, 5, 20)
HOLDOUT_FRACTION = 0.20
MIN_TRAIN_CANDLES = 400
MIN_HOLDOUT_CANDLES = 126
TURNOVER_COST = 0.001


def _finite(value: Any) -> bool:
    try:
        return math.isfinite(float(value))
    except (TypeError, ValueError):
        return False


def _max_drawdown(log_returns: np.ndarray) -> float:
    if len(log_returns) == 0:
        return 0.0
    equity = np.exp(np.cumsum(log_returns))
    peaks = np.maximum.accumulate(np.concatenate(([1.0], equity)))
    values = np.concatenate(([1.0], equity))
    return float(np.min(values / peaks - 1.0))


def _return_metrics(log_returns: np.ndarray, *, horizon_bars: int) -> dict[str, float]:
    values = np.asarray(log_returns, dtype=np.float64)
    if len(values) == 0:
        return {"total_return": 0.0, "annualized_sharpe": 0.0, "max_drawdown": 0.0}
    periods = 252.0 / max(1, horizon_bars)
    std = float(np.std(values, ddof=1)) if len(values) > 1 else 0.0
    sharpe = float(np.mean(values) / std * math.sqrt(periods)) if std > 0 else 0.0
    return {
        "total_return": float(math.exp(float(np.sum(values))) - 1.0),
        "annualized_sharpe": sharpe,
        "max_drawdown": _max_drawdown(values),
    }


def _strategy_metrics(
    forward_returns: np.ndarray,
    probabilities: np.ndarray,
    *,
    horizon_bars: int,
    turnover_cost: float = TURNOVER_COST,
) -> dict[str, Any]:
    """Long/cash strategy on non-overlapping, strictly future returns."""

    if len(forward_returns) != len(probabilities):
        raise ValueError("returns and probabilities must have equal length")
    positions = (np.argmax(probabilities, axis=1) == 2).astype(np.float64)
    previous = np.concatenate(([0.0], positions[:-1]))
    costs = np.abs(positions - previous) * float(turnover_cost)
    strategy_returns = positions * forward_returns - costs
    strategy = _return_metrics(strategy_returns, horizon_bars=horizon_bars)
    benchmark = _return_metrics(forward_returns, horizon_bars=horizon_bars)
    return {
        "policy": "long_when_UP_else_cash",
        "turnover_cost": float(turnover_cost),
        "observations": int(len(forward_returns)),
        "invested_fraction": float(np.mean(positions)) if len(positions) else 0.0,
        "strategy": strategy,
        "buy_and_hold": benchmark,
        "excess_total_return": strategy["total_return"] - benchmark["total_return"],
    }


def _closed_case(
    case: AssetCase,
    horizon: int,
    status: str,
    reason: str,
    **extra: Any,
) -> dict[str, Any]:
    return {
        "ticker": case.ticker,
        "asset_class": case.asset_class,
        "horizon_bars": horizon,
        "status": status,
        "reason": reason,
        **extra,
    }


def evaluate_case(
    case: AssetCase,
    candles: list[dict[str, Any]],
    horizon: int,
) -> dict[str, Any]:
    """Fit on a prefix and evaluate only on the untouched chronological suffix."""

    candle_count = len(candles)
    holdout_count = max(MIN_HOLDOUT_CANDLES, int(candle_count * HOLDOUT_FRACTION))
    train_count = candle_count - holdout_count
    if train_count < MIN_TRAIN_CANDLES:
        return _closed_case(
            case,
            horizon,
            "insufficient_data",
            "TOO_FEW_REAL_CANDLES",
            candle_count=candle_count,
        )

    with tempfile.TemporaryDirectory(prefix="superezio-investment-eval-") as artifact_dir:
        expert = TechnicalNeuralExpert(horizon_bars=horizon, artifact_dir=artifact_dir)
        try:
            train_prepared = expert._prepare_with_horizon(candles[:train_count])
            qualification, artifact = expert._fit_and_qualify(case.ticker, train_prepared)
        except Exception as exc:
            return _closed_case(
                case,
                horizon,
                "error",
                f"TRAINING_ERROR:{type(exc).__name__}",
                detail=str(exc)[:240],
                candle_count=candle_count,
                train_candles=train_count,
                holdout_candles=holdout_count,
            )

        if artifact is None:
            return _closed_case(
                case,
                horizon,
                "abstain",
                str(qualification.get("reason_codes", ["MODEL_NOT_QUALIFIED"])[0]),
                candle_count=candle_count,
                train_candles=train_count,
                holdout_candles=holdout_count,
                internal_qualification=qualification.get("baseline_comparison", {}),
            )

        full_prepared = expert._prepare_with_horizon(candles)
        first_unseen = len(train_prepared.features)
        indices = np.arange(first_unseen, len(full_prepared.features), horizon, dtype=np.int64)
        if len(indices) < 12:
            return _closed_case(case, horizon, "insufficient_data", "HOLDOUT_TOO_SHORT")

        probabilities = np.vstack(
            [expert._predict_artifact(artifact, full_prepared.features[index]) for index in indices]
        )
        returns = full_prepared.forward_returns[indices]
        threshold = float(artifact["movement_threshold"])
        labels = np.where(returns > threshold, 2, np.where(returns < -threshold, 0, 1))
        metrics = expert._metrics(labels.astype(np.int64), probabilities, artifact["climatology"])
        model_metrics = metrics["model"]
        baseline_metrics = metrics["baseline"]
        brier_skill = 1.0 - model_metrics["brier"] / baseline_metrics["brier"]
        strategy = _strategy_metrics(returns, probabilities, horizon_bars=horizon)

        return _closed_case(
            case,
            horizon,
            "evaluated",
            "UNTOUCHED_HOLDOUT_SCORED",
            candle_count=candle_count,
            train_candles=train_count,
            holdout_candles=holdout_count,
            holdout_observations=int(len(indices)),
            holdout_start=full_prepared.timestamps[int(indices[0])].isoformat(),
            holdout_end=full_prepared.timestamps[int(indices[-1])].isoformat(),
            probabilistic={
                "model": model_metrics,
                "climatology": baseline_metrics,
                "brier_skill": float(brier_skill),
                "balanced_accuracy_lift": model_metrics["balanced_accuracy"]
                - baseline_metrics["balanced_accuracy"],
            },
            investment=strategy,
        )


def overall_verdict(results: Iterable[dict[str, Any]], *, data_cases: int) -> dict[str, Any]:
    rows = list(results)
    evaluated = [row for row in rows if row.get("status") == "evaluated"]
    brier_skills = [row["probabilistic"]["brier_skill"] for row in evaluated]
    accuracy_lifts = [row["probabilistic"]["balanced_accuracy_lift"] for row in evaluated]
    excess_returns = [row["investment"]["excess_total_return"] for row in evaluated]
    represented_classes = {row["asset_class"] for row in evaluated}
    qualification_rate = len(evaluated) / data_cases if data_cases else 0.0

    gates = {
        "at_least_six_qualified_cases": len(evaluated) >= 6,
        "at_least_four_asset_classes": len(represented_classes) >= 4,
        "qualification_rate_at_least_half": qualification_rate >= 0.50,
        "positive_mean_brier_skill": bool(brier_skills) and fmean(brier_skills) > 0.0,
        "positive_mean_balanced_accuracy_lift": bool(accuracy_lifts)
        and fmean(accuracy_lifts) > 0.0,
        "positive_median_excess_return": bool(excess_returns) and median(excess_returns) > 0.0,
    }
    proven = all(gates.values())
    return {
        "verdict": "EVIDENCE_OF_MULTI_ASSET_SKILL" if proven else "INVESTMENT_SKILL_NOT_PROVEN",
        "gates": gates,
        "data_cases": data_cases,
        "evaluated_cases": len(evaluated),
        "qualification_rate": qualification_rate,
        "asset_classes_evaluated": sorted(represented_classes),
        "mean_brier_skill": fmean(brier_skills) if brier_skills else None,
        "mean_balanced_accuracy_lift": fmean(accuracy_lifts) if accuracy_lifts else None,
        "median_excess_total_return": median(excess_returns) if excess_returns else None,
    }


def run_evaluation(
    universe: tuple[AssetCase, ...] = DEFAULT_UNIVERSE,
    horizons: tuple[int, ...] = DEFAULT_HORIZONS,
) -> dict[str, Any]:
    provider = YFinanceProvider()
    results: list[dict[str, Any]] = []
    data_cases = 0
    data_inventory: list[dict[str, Any]] = []

    for case in universe:
        payload = provider.get_candles(case.ticker, timeframe="5Y")
        candles = payload.get("candles") if isinstance(payload, dict) else None
        source = payload.get("source") if isinstance(payload, dict) else None
        if source != "yfinance" or not isinstance(candles, list) or not candles:
            reason = (
                str(payload.get("error", "NO_REAL_CANDLES"))
                if isinstance(payload, dict)
                else "INVALID_PROVIDER_PAYLOAD"
            )
            data_inventory.append(
                {
                    "ticker": case.ticker,
                    "asset_class": case.asset_class,
                    "status": "error",
                    "reason": reason,
                }
            )
            for horizon in horizons:
                results.append(_closed_case(case, horizon, "data_error", reason))
            continue

        data_cases += len(horizons)
        data_inventory.append(
            {
                "ticker": case.ticker,
                "asset_class": case.asset_class,
                "status": "observed",
                "source": source,
                "candles": len(candles),
                "first": str(candles[0].get("datetime")),
                "last": str(candles[-1].get("datetime")),
            }
        )
        for horizon in horizons:
            results.append(evaluate_case(case, candles, horizon))

    return {
        "schema_version": 1,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "method": {
            "data": "observed adjusted daily OHLCV from yfinance",
            "split": "80% chronological development prefix, 20% untouched future holdout",
            "internal_gate": "train/validation/calibration/test with horizon gaps",
            "external_holdout": "never used for fitting, calibration, convergence or qualification",
            "strategy": "long on UP, cash otherwise; non-overlapping horizon returns",
            "turnover_cost": TURNOVER_COST,
            "benchmarks": ["training_climatology", "buy_and_hold", "cash"],
        },
        "universe": [case.__dict__ for case in universe],
        "horizons": list(horizons),
        "data_inventory": data_inventory,
        "results": results,
        "summary": overall_verdict(results, data_cases=data_cases),
    }


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, help="Write the full JSON evidence report")
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Exit non-zero unless every pre-registered investment-skill gate passes",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    report = run_evaluation()
    rendered = json.dumps(report, indent=2, sort_keys=True, default=str) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    print(json.dumps(report["summary"], indent=2, sort_keys=True))
    return int(args.strict and report["summary"]["verdict"] != "EVIDENCE_OF_MULTI_ASSET_SKILL")


if __name__ == "__main__":
    raise SystemExit(main())
