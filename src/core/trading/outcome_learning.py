"""Transactional learning from terminal paper-trade outcomes.

The ledger is the single durable boundary between a closed trade and adaptive
weights. A trade submission is never a learning event. Replaying the same
version is a no-op; changing its payload is an explicit conflict.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from .reward import RewardFunction, TradeOutcome


DEFAULT_OUTCOME_DB = Path(__file__).resolve().parents[3] / "data" / "adaptive_outcomes.sqlite3"
OUTCOME_SCHEMA_VERSION = 1


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
                    correct_calls INTEGER NOT NULL,
                    total_confidence REAL NOT NULL,
                    last_called_at TEXT NOT NULL,
                    weight REAL NOT NULL CHECK(weight >= 0.1 AND weight <= 3.0)
                );
                """
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
            correct = 1 if payload["outcome"] == "win" else 0
            for expert_name, confidence in payload["expert_attribution"].items():
                self._update_expert(connection, expert_name, confidence, correct, now)
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

        raw_attribution = trade.get("expert_attribution") or {}
        attribution = {
            str(name): _unit_confidence(confidence)
            for name, confidence in raw_attribution.items()
            if str(name).strip()
        }
        return {
            "trade_id": trade_id,
            "symbol": str(trade.get("ticker") or trade.get("symbol") or "").upper(),
            "side": str(trade.get("direction") or trade.get("side") or "long").lower(),
            "entry_price": float(trade.get("entry_price") or 0.0),
            "exit_price": float(trade["exit_price"]),
            "qty": float(trade.get("shares") or trade.get("qty") or 0.0),
            "pnl": float(trade.get("pnl_amount") or 0.0),
            "entry_date": str(trade.get("entry_date") or trade["exit_date"]),
            "exit_date": str(trade["exit_date"]),
            "outcome": outcome,
            "confidence_at_entry": _unit_confidence(trade.get("confidence_at_entry", 0.0)),
            "risk_at_entry": (
                float(trade["risk_at_entry"]) if trade.get("risk_at_entry") is not None else None
            ),
            "fees": float(trade.get("fees") or 0.0),
            "slippage": float(trade.get("slippage") or 0.0),
            "expert_attribution": attribution,
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
            confidence_at_entry=payload["confidence_at_entry"],
            verdict_at_entry=payload["confidence_at_entry"],
            risk_at_entry=payload["risk_at_entry"],
            fees=payload["fees"],
            slippage=payload["slippage"],
        )

    @staticmethod
    def _update_expert(
        connection: sqlite3.Connection,
        expert_name: str,
        confidence: float,
        correct: int,
        now: str,
    ) -> None:
        row = connection.execute(
            "SELECT total_calls, correct_calls, total_confidence FROM expert_stats WHERE expert_name = ?",
            (expert_name,),
        ).fetchone()
        total = (row["total_calls"] if row else 0) + 1
        correct_total = (row["correct_calls"] if row else 0) + correct
        confidence_total = (row["total_confidence"] if row else 0.0) + confidence
        smoothed_accuracy = (correct_total + 1.0) / (total + 2.0)
        weight = max(0.1, min(3.0, 0.5 + smoothed_accuracy))
        connection.execute(
            """INSERT INTO expert_stats
               (expert_name, total_calls, correct_calls, total_confidence, last_called_at, weight)
               VALUES (?, ?, ?, ?, ?, ?)
               ON CONFLICT(expert_name) DO UPDATE SET
                 total_calls=excluded.total_calls,
                 correct_calls=excluded.correct_calls,
                 total_confidence=excluded.total_confidence,
                 last_called_at=excluded.last_called_at,
                 weight=excluded.weight""",
            (expert_name, total, correct_total, confidence_total, now, weight),
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
