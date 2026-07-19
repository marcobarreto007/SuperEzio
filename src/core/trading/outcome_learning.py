"""Transactional learning from terminal paper-trade outcomes.

The ledger is the single durable boundary between a closed trade and adaptive
weights. A trade submission is never a learning event. Replaying the same
version is a no-op; changing its payload is an explicit conflict.
"""

from __future__ import annotations

import hashlib
import json
import math
import sqlite3
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from .reward import RewardFunction, TradeOutcome


DEFAULT_OUTCOME_DB = Path(__file__).resolve().parents[3] / "data" / "adaptive_outcomes.sqlite3"
OUTCOME_SCHEMA_VERSION = 2
DEFAULT_EXPERT_WEIGHTS = {
    "social_forensics": 0.25,
    "sentiment": 0.15,
    "macro_risk": 0.15,
    "fundamental_value": 0.20,
    "momentum_technical": 0.15,
    "contrarian_opportunity": 0.10,
}
EXPERT_ROLE_ALIASES = {
    "fundamental": "fundamental_value",
    "technical": "momentum_technical",
    "momentum": "momentum_technical",
    "contrarian": "contrarian_opportunity",
    "risk": "macro_risk",
    "crisis": "macro_risk",
}


class OutcomeConflictError(RuntimeError):
    """The same immutable event id was replayed with different contents."""


@dataclass(frozen=True)
class OutcomeLearningResult:
    event_id: str
    processed: bool
    reward: dict[str, float]
    normalized_weights: dict[str, float]


def _parse_datetime(value: Any) -> datetime:
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _unit_confidence(value: Any) -> float:
    try:
        confidence = float(value)
    except (TypeError, ValueError):
        return 0.0
    if confidence > 1.0:
        confidence /= 100.0
    return max(0.0, min(1.0, confidence))


def _normalize_direction(value: Any) -> str | None:
    token = str(value or "").strip().upper()
    if token in {"UP", "BUY", "LONG", "BULLISH", "UNDERVALUED", "SUPPORT"}:
        return "UP"
    if token in {"DOWN", "SELL", "SHORT", "BEARISH", "OVERVALUED", "BLOCK"}:
        return "DOWN"
    if token in {"SIDEWAYS", "NEUTRAL", "WAIT", "HOLD", "FAIR_VALUE"}:
        return "SIDEWAYS"
    return None


def _canonical_prediction(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, Mapping):
        return None
    direction = _normalize_direction(
        value.get("direction") or value.get("decision") or value.get("verdict")
    )
    raw_probabilities = value.get("probabilities") or value.get("direction_prob")
    if isinstance(raw_probabilities, Mapping):
        try:
            probabilities = {
                label: float(raw_probabilities[label]) for label in ("up", "down", "sideways")
            }
        except (KeyError, TypeError, ValueError):
            return None
        if any(
            not math.isfinite(probability) or probability < 0.0 or probability > 1.0
            for probability in probabilities.values()
        ):
            return None
        if not math.isclose(sum(probabilities.values()), 1.0, abs_tol=1e-6):
            return None
        probability_direction = max(probabilities, key=probabilities.get).upper()
        if direction is None:
            direction = probability_direction
        elif direction != probability_direction:
            return None
    elif direction is not None:
        confidence = _unit_confidence(value.get("confidence"))
        remainder = (1.0 - confidence) / 2.0
        probabilities = {"up": remainder, "down": remainder, "sideways": remainder}
        probabilities[direction.lower()] = confidence
    else:
        return None
    return {"direction": direction, "probabilities": probabilities}


class OutcomeLearningEngine:
    """Compute reward and update expert statistics exactly once per outcome."""

    def __init__(self, db_path: Path | None = None, reward_function: RewardFunction | None = None):
        self.db_path = Path(db_path or DEFAULT_OUTCOME_DB)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.reward_function = reward_function or RewardFunction()
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS processed_outcomes (
                    event_id TEXT PRIMARY KEY,
                    trade_id TEXT NOT NULL,
                    schema_version INTEGER NOT NULL,
                    payload_hash TEXT NOT NULL,
                    reward_json TEXT NOT NULL,
                    processed_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS expert_stats (
                    expert_name TEXT PRIMARY KEY,
                    total_calls INTEGER NOT NULL,
                    correct_calls REAL NOT NULL,
                    total_confidence REAL NOT NULL,
                    total_brier REAL NOT NULL DEFAULT 0.0,
                    baseline_brier REAL NOT NULL DEFAULT 0.0,
                    brier_skill REAL NOT NULL DEFAULT 0.0,
                    last_called_at TEXT NOT NULL,
                    weight REAL NOT NULL CHECK(weight >= 0.1 AND weight <= 3.0)
                );
                """
            )
            columns = {
                row[1] for row in connection.execute("PRAGMA table_info(expert_stats)").fetchall()
            }
            for name in ("total_brier", "baseline_brier", "brier_skill"):
                if name not in columns:
                    connection.execute(
                        f"ALTER TABLE expert_stats ADD COLUMN {name} REAL NOT NULL DEFAULT 0.0"
                    )

    def process_trade(self, trade: Mapping[str, Any]) -> OutcomeLearningResult:
        payload = self._canonical_payload(trade)
        event_id = f"{payload['trade_id']}:v{OUTCOME_SCHEMA_VERSION}"
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        payload_hash = hashlib.sha256(encoded.encode("utf-8")).hexdigest()
        outcome = self._to_trade_outcome(payload)
        reward = asdict(self.reward_function.compute(outcome))

        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            existing = connection.execute(
                "SELECT payload_hash, reward_json FROM processed_outcomes WHERE event_id = ?",
                (event_id,),
            ).fetchone()
            if existing:
                if existing["payload_hash"] != payload_hash:
                    raise OutcomeConflictError(f"outcome payload conflict for {event_id}")
                connection.commit()
                return OutcomeLearningResult(
                    event_id=event_id,
                    processed=False,
                    reward=json.loads(existing["reward_json"]),
                    normalized_weights=self.get_normalized_weights(connection),
                )

            now = datetime.now(timezone.utc).isoformat()
            connection.execute(
                """INSERT INTO processed_outcomes
                   (event_id, trade_id, schema_version, payload_hash, reward_json, processed_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    event_id,
                    payload["trade_id"],
                    OUTCOME_SCHEMA_VERSION,
                    payload_hash,
                    json.dumps(reward, sort_keys=True),
                    now,
                ),
            )
            for expert_name, prediction in payload["expert_predictions"].items():
                self._update_expert(
                    connection,
                    expert_name,
                    prediction["probabilities"],
                    payload["realized_direction"],
                    now,
                )
            connection.commit()

        return OutcomeLearningResult(
            event_id=event_id,
            processed=True,
            reward=reward,
            normalized_weights=self.get_normalized_weights(),
        )

    def _canonical_payload(self, trade: Mapping[str, Any]) -> dict[str, Any]:
        trade_id = str(trade.get("trade_id") or "").strip()
        outcome = str(trade.get("outcome") or "").lower()
        if not trade_id:
            raise ValueError("terminal outcome requires trade_id")
        if outcome not in {"win", "loss", "breakeven"}:
            raise ValueError("learning requires a terminal win/loss/breakeven outcome")
        if trade.get("exit_price") is None or not trade.get("exit_date"):
            raise ValueError("learning requires exit_price and exit_date")

        raw_predictions = trade.get("expert_predictions") or {}
        predictions: dict[str, dict[str, Any]] = {}
        for name, prediction in raw_predictions.items():
            role = str(name).strip().lower().split("#", 1)[0]
            role = EXPERT_ROLE_ALIASES.get(role, role)
            canonical = _canonical_prediction(prediction)
            if role in DEFAULT_EXPERT_WEIGHTS and canonical is not None:
                predictions[role] = canonical

        entry_price = float(trade.get("entry_price") or 0.0)
        exit_price = float(trade["exit_price"])
        qty = float(trade.get("shares") or trade.get("qty") or 0.0)
        side = str(trade.get("direction") or trade.get("side") or "").lower()
        if entry_price <= 0 or exit_price <= 0 or qty <= 0:
            raise ValueError("learning requires positive entry_price, exit_price, and qty")
        if side not in {"long", "buy", "short", "sell"}:
            raise ValueError("learning requires an explicit long/short side")
        move = exit_price / entry_price - 1.0
        costs = float(trade.get("fees") or 0.0) + float(trade.get("slippage") or 0.0)
        cost_rate = max(0.0, costs) / max(entry_price * qty, 1e-12)
        deadband = max(0.001, cost_rate)
        if move > deadband:
            realized_direction = "UP"
        elif move < -deadband:
            realized_direction = "DOWN"
        else:
            realized_direction = "SIDEWAYS"

        calibration_status = str(trade.get("calibration_status") or "").lower()
        raw_probability = trade.get("prediction_probability_at_entry")
        prediction_class = _normalize_direction(trade.get("prediction_class_at_entry"))
        profitable_class = "UP" if side in {"long", "buy"} else "DOWN"
        prediction_probability = (
            _unit_confidence(raw_probability)
            if raw_probability is not None
            and calibration_status in {"calibrated", "validated_oos"}
            and prediction_class == profitable_class
            else None
        )
        return {
            "trade_id": trade_id,
            "symbol": str(trade.get("ticker") or trade.get("symbol") or "").upper(),
            "side": side,
            "entry_price": entry_price,
            "exit_price": exit_price,
            "qty": qty,
            "pnl": float(trade.get("pnl_amount") or 0.0),
            "entry_date": str(trade.get("entry_date") or trade["exit_date"]),
            "exit_date": str(trade["exit_date"]),
            "outcome": outcome,
            "prediction_probability_at_entry": prediction_probability,
            "prediction_class_at_entry": prediction_class,
            "calibration_status": calibration_status or "unknown",
            "model_id": str(trade.get("model_id") or ""),
            "forecast_as_of": str(trade.get("forecast_as_of") or ""),
            "forecast_horizon": trade.get("forecast_horizon"),
            "risk_at_entry": (
                float(trade["risk_at_entry"]) if trade.get("risk_at_entry") is not None else None
            ),
            "fees": float(trade.get("fees") or 0.0),
            "slippage": float(trade.get("slippage") or 0.0),
            "expert_predictions": predictions,
            "realized_direction": realized_direction,
        }

    def _to_trade_outcome(self, payload: Mapping[str, Any]) -> TradeOutcome:
        duration = max(
            0.0,
            (
                _parse_datetime(payload["exit_date"]) - _parse_datetime(payload["entry_date"])
            ).total_seconds(),
        )
        return TradeOutcome(
            symbol=payload["symbol"],
            side=payload["side"],
            entry_price=payload["entry_price"],
            exit_price=payload["exit_price"],
            qty=payload["qty"],
            pnl=payload["pnl"],
            hold_duration_seconds=duration,
            confidence_at_entry=payload["prediction_probability_at_entry"],
            verdict_at_entry=payload["prediction_probability_at_entry"],
            risk_at_entry=payload["risk_at_entry"],
            fees=payload["fees"],
            slippage=payload["slippage"],
        )

    @staticmethod
    def _update_expert(
        connection: sqlite3.Connection,
        expert_name: str,
        probabilities: Mapping[str, float],
        realized_direction: str,
        now: str,
    ) -> None:
        row = connection.execute(
            """SELECT total_calls, correct_calls, total_confidence,
                      total_brier, baseline_brier
               FROM expert_stats WHERE expert_name = ?""",
            (expert_name,),
        ).fetchone()
        total = (row["total_calls"] if row else 0) + 1
        selected = max(probabilities, key=probabilities.get).upper()
        correct_total = (row["correct_calls"] if row else 0.0) + float(
            selected == realized_direction
        )
        confidence_total = (row["total_confidence"] if row else 0.0) + max(probabilities.values())
        target = {
            "up": float(realized_direction == "UP"),
            "down": float(realized_direction == "DOWN"),
            "sideways": float(realized_direction == "SIDEWAYS"),
        }
        brier = sum((probabilities[label] - target[label]) ** 2 for label in target)
        total_brier = (row["total_brier"] if row else 0.0) + brier
        baseline_brier = (row["baseline_brier"] if row else 0.0) + 2.0 / 3.0
        raw_skill = 1.0 - total_brier / baseline_brier
        shrunk_skill = raw_skill * total / (total + 20.0)
        weight = max(0.5, min(2.0, math.exp(2.0 * shrunk_skill)))
        connection.execute(
            """INSERT INTO expert_stats
               (expert_name, total_calls, correct_calls, total_confidence,
                total_brier, baseline_brier, brier_skill, last_called_at, weight)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(expert_name) DO UPDATE SET
                 total_calls=excluded.total_calls,
                 correct_calls=excluded.correct_calls,
                 total_confidence=excluded.total_confidence,
                 total_brier=excluded.total_brier,
                 baseline_brier=excluded.baseline_brier,
                 brier_skill=excluded.brier_skill,
                 last_called_at=excluded.last_called_at,
                 weight=excluded.weight""",
            (
                expert_name,
                total,
                correct_total,
                confidence_total,
                total_brier,
                baseline_brier,
                shrunk_skill,
                now,
                weight,
            ),
        )

    def get_normalized_weights(
        self, connection: sqlite3.Connection | None = None
    ) -> dict[str, float]:
        owns_connection = connection is None
        connection = connection or self._connect()
        try:
            rows = connection.execute(
                "SELECT expert_name, weight FROM expert_stats ORDER BY expert_name"
            ).fetchall()
            total = sum(float(row["weight"]) for row in rows)
            if total <= 0:
                return {}
            return {row["expert_name"]: float(row["weight"]) / total for row in rows}
        finally:
            if owns_connection:
                connection.close()


def get_effective_expert_weights(db_path: Path | None = None) -> dict[str, float]:
    """Blend durable learned reliability with safe static priors."""
    resolved = Path(db_path or DEFAULT_OUTCOME_DB)
    baseline = dict(DEFAULT_EXPERT_WEIGHTS)
    if not resolved.exists():
        return baseline

    learned = OutcomeLearningEngine(resolved).get_normalized_weights()
    learned_roles = {role: value for role, value in learned.items() if role in baseline}
    if not learned_roles:
        return baseline

    # A learned distribution is relative only to roles with observations.
    # Scaling by their count makes equal learned reliability preserve priors.
    scale = len(learned_roles)
    for role, reliability in learned_roles.items():
        baseline[role] *= reliability * scale
    total = sum(baseline.values())
    return {role: weight / total for role, weight in baseline.items()}
