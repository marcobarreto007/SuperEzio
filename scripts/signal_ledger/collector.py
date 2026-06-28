"""Agrega eventos NDJSON do /task/submit em candidato a signal_emit."""

from __future__ import annotations

import hashlib
import json
import re
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


_TICKER_RE = re.compile(r"^[A-Za-z0-9.\-^]{1,12}$")


@dataclass
class StreamRun:
    run_id: str = ""
    msg_id: str | None = None
    session_id: str | None = None
    ticker: str = ""
    route: str = ""
    intent: str = ""
    time_horizon: str = ""
    analysis_id: str | None = None
    data_quality: str | None = None
    f51_passed: bool | None = None
    f51_confidence: float | None = None
    f51_hub_risk_score: float | None = None
    neural: dict[str, Any] = field(default_factory=dict)
    sdca: dict[str, Any] = field(default_factory=dict)
    pennylab_decision: str | None = None
    crisis_systemic_risk: float | None = None
    reference_price: float | None = None
    reference_price_source: str | None = None
    user_message_excerpt: str = ""
    ceo_chunks: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    first_ts: datetime | None = None

    def ingest_line(self, obj: dict[str, Any]) -> None:
        if self.first_ts is None:
            self.first_ts = datetime.now(UTC)
        kind = obj.get("type") or ""
        if kind == "STREAM_START":
            self.msg_id = obj.get("msg_id")
            self.run_id = self.run_id or str(obj.get("run_id") or "")
        elif kind == "CHART_DATA":
            if obj.get("ticker"):
                self.ticker = str(obj["ticker"]).upper()
        elif kind == "INTENT_CLASSIFIED":
            self.route = str(obj.get("route") or self.route)
            self.intent = str(obj.get("intent") or self.intent)
            if obj.get("ticker"):
                self.ticker = str(obj["ticker"]).upper()
            self.time_horizon = str(obj.get("time_horizon") or self.time_horizon)
        elif kind == "DATA_COLLECTED":
            self.analysis_id = obj.get("analysis_id") or self.analysis_id
            self.data_quality = obj.get("data_quality") or obj.get("quality") or self.data_quality
            if obj.get("ticker"):
                self.ticker = str(obj["ticker"]).upper()
            price = obj.get("price") or obj.get("close")
            if price is not None:
                try:
                    self.reference_price = float(price)
                    self.reference_price_source = str(obj.get("source") or "data_collected")
                except (TypeError, ValueError):
                    pass
        elif kind == "F51_VERDICT":
            if "passed" in obj:
                self.f51_passed = bool(obj["passed"])
            if obj.get("confidence") is not None:
                try:
                    self.f51_confidence = float(obj["confidence"])
                except (TypeError, ValueError):
                    pass
            if obj.get("hub_risk_score") is not None:
                try:
                    self.f51_hub_risk_score = float(obj["hub_risk_score"])
                except (TypeError, ValueError):
                    pass
        elif kind == "NEURAL_DECISION":
            self.neural = {
                "direction_prob": obj.get("direction_prob"),
                "expected_return": obj.get("expected_return"),
                "drawdown_risk": obj.get("drawdown_risk"),
                "uncertainty": obj.get("uncertainty"),
                "regime": obj.get("regime"),
                "recommendation": obj.get("recommendation"),
                "veto": obj.get("veto"),
            }
            if obj.get("symbol"):
                self.ticker = str(obj["symbol"]).upper()
        elif kind == "SDCA_FIREWALL":
            self.sdca = {
                "decision": obj.get("decision"),
                "confidence": obj.get("confidence"),
                "uncertainty": obj.get("uncertainty"),
            }
        elif kind == "CRISIS_MATH":
            if obj.get("systemic_risk") is not None:
                try:
                    self.crisis_systemic_risk = float(obj["systemic_risk"])
                except (TypeError, ValueError):
                    pass
        elif kind == "CHUNK":
            content = obj.get("content")
            if isinstance(content, str) and content:
                self.ceo_chunks.append(content)
        elif kind == "ERROR":
            detail = str(obj.get("detail") or "pipeline_error")
            self.errors.append(detail[:300])
        elif kind == "PIPELINE_STEP":
            if obj.get("run_id") and not self.run_id:
                self.run_id = str(obj["run_id"])

    def load_trace_price(self, traces_dir: Path) -> None:
        if self.reference_price is not None or not self.analysis_id:
            return
        trace_path = traces_dir / f"{self.analysis_id}.json"
        if not trace_path.exists():
            return
        try:
            trace = json.loads(trace_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return
        for key in ("realtime_price", "technicals"):
            block = trace.get(key) or {}
            price = block.get("price")
            if price is not None:
                self.reference_price = float(price)
                self.reference_price_source = str(block.get("source") or f"trace:{key}")
                return


def parse_ndjson(text: str) -> StreamRun:
    run = StreamRun()
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            run.errors.append("invalid_ndjson_line")
            continue
        if not isinstance(obj, dict):
            continue
        if not run.run_id and obj.get("run_id"):
            run.run_id = str(obj["run_id"])
        run.ingest_line(obj)
    if not run.run_id:
        run.run_id = uuid.uuid4().hex[:12]
    return run


def _valid_ticker(ticker: str, policy: dict[str, Any]) -> bool:
    if not ticker or not _TICKER_RE.match(ticker):
        return False
    universe = policy.get("universe") or {}
    blocked = {t.upper() for t in universe.get("blocked_tickers") or []}
    if ticker in blocked:
        return False
    suffixes = universe.get("allowed_suffixes") or []
    if suffixes:
        return any(ticker.endswith(s) for s in suffixes)
    return True


def derive_action(run: StreamRun, policy: dict[str, Any]) -> str:
    rules = policy.get("action_rules") or {}
    neural = run.neural or {}
    rec = str(neural.get("recommendation") or "")
    veto_blocks = set(rules.get("veto_recommendation_blocks") or ["veto_block"])
    if rec in veto_blocks or neural.get("veto") is True:
        return "FLAT"
    try:
        dp = float(neural.get("direction_prob"))
    except (TypeError, ValueError):
        dp = 0.5
    long_min = float(rules.get("long_direction_prob_min", 0.55))
    short_max = float(rules.get("short_direction_prob_max", 0.45))
    if dp >= long_min:
        return "LONG"
    if dp <= short_max:
        return "SHORT"
    return "HOLD"


def classify_emit(run: StreamRun, policy: dict[str, Any]) -> tuple[str, list[str], str]:
    """Retorna (status, reject_reasons, action)."""
    reasons: list[str] = []
    elig = policy.get("eligibility") or {}

    if run.errors:
        reasons.append(f"pipeline_errors:{len(run.errors)}")

    route_need = elig.get("require_route", "ticker_analysis")
    if run.route and run.route != route_need:
        reasons.append(f"route:{run.route}")
    if not _valid_ticker(run.ticker, policy):
        reasons.append("invalid_or_blocked_ticker")

    dq = (run.data_quality or "").lower()
    blocked_dq = [x.lower() for x in elig.get("blocked_data_quality") or []]
    if dq in blocked_dq:
        reasons.append(f"data_quality:{run.data_quality}")

    if elig.get("require_f51_passed") and run.f51_passed is not True:
        reasons.append("f51_not_passed")
    min_conf = float(elig.get("f51_min_confidence", 0.55))
    if run.f51_confidence is not None and run.f51_confidence < min_conf:
        reasons.append(f"f51_confidence_below:{min_conf}")

    if elig.get("require_neural_veto_false") and run.neural.get("veto") is True:
        reasons.append("neural_veto")

    action = derive_action(run, policy)
    sdca_dec = str((run.sdca or {}).get("decision") or "").upper()
    official_sdca = elig.get("sdca_official", "ALLOW")
    watch_sdca = elig.get("sdca_watchlist", "REVIEW")
    reject_sdca = elig.get("sdca_reject", "BLOCK")

    if sdca_dec == reject_sdca:
        reasons.append(f"sdca:{sdca_dec}")
    elif sdca_dec == watch_sdca:
        return "watchlist", reasons, action
    elif sdca_dec and sdca_dec != official_sdca:
        reasons.append(f"sdca:{sdca_dec or 'missing'}")

    official_actions = set(
        policy.get("action_rules", {}).get("official_actions") or ["LONG", "SHORT"]
    )
    if action not in official_actions:
        reasons.append(f"action_not_official:{action}")

    if reasons:
        return "rejected", reasons, action
    return "official", [], action


def build_emit_record(
    run: StreamRun,
    policy: dict[str, Any],
    *,
    trace_dir: Path,
    raw_ndjson_path: Path | None = None,
) -> dict[str, Any]:
    run.load_trace_price(trace_dir)
    status, reject_reasons, action = classify_emit(run, policy)
    now = datetime.now(UTC)
    ref_ts = run.first_ts or now
    signal_id = f"{run.ticker or 'UNK'}-{ref_ts.strftime('%Y%m%d')}-{uuid.uuid4().hex[:8]}"

    ceo_text = "".join(run.ceo_chunks)
    ceo_hash = None
    if ceo_text:
        ceo_hash = hashlib.sha256(ceo_text.encode("utf-8")).hexdigest()[:16]

    trace_path = None
    if run.analysis_id:
        candidate = trace_dir / f"{run.analysis_id}.json"
        if candidate.exists():
            trace_path = str(candidate.relative_to(trace_dir.parent.parent))

    neural = run.neural or {}
    try:
        direction_prob = (
            float(neural["direction_prob"]) if neural.get("direction_prob") is not None else None
        )
    except (TypeError, ValueError):
        direction_prob = None

    record: dict[str, Any] = {
        "record_type": "signal_emit",
        "signal_id": signal_id,
        "run_id": run.run_id,
        "msg_id": run.msg_id,
        "session_id": run.session_id,
        "policy_version": policy["policy_version"],
        "status": status,
        "reject_reasons": reject_reasons,
        "ticker": run.ticker or "UNKNOWN",
        "action": action,
        "resolution_horizon": policy.get("resolution_horizon", "5d"),
        "emitted_at": now.isoformat(),
        "reference_ts": ref_ts.isoformat(),
        "user_message_excerpt": (run.user_message_excerpt or "")[:500],
        "ceo_text_hash": ceo_hash,
        "trace_path": trace_path,
        "raw_ndjson_path": str(raw_ndjson_path) if raw_ndjson_path else None,
        "evidence": {
            "analysis_id": run.analysis_id,
            "data_quality": run.data_quality,
            "route": run.route,
            "intent": run.intent,
            "time_horizon": run.time_horizon,
            "f51_passed": run.f51_passed,
            "f51_confidence": run.f51_confidence,
            "f51_hub_risk_score": run.f51_hub_risk_score,
            "neural_direction_prob": direction_prob,
            "neural_expected_return": neural.get("expected_return"),
            "neural_drawdown_risk": neural.get("drawdown_risk"),
            "neural_uncertainty": neural.get("uncertainty"),
            "neural_regime": neural.get("regime"),
            "neural_recommendation": neural.get("recommendation"),
            "neural_veto": neural.get("veto"),
            "sdca_decision": (run.sdca or {}).get("decision"),
            "sdca_confidence": (run.sdca or {}).get("confidence"),
            "sdca_uncertainty": (run.sdca or {}).get("uncertainty"),
            "pennylab_decision": run.pennylab_decision,
            "crisis_systemic_risk": run.crisis_systemic_risk,
            "reference_price": run.reference_price,
            "reference_price_source": run.reference_price_source,
        },
    }
    return record


def append_jsonl(path: Path, record: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
