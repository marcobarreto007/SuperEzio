"""Temporal join between abnormal moves (P1) and market events (P2).

Session impact uses America/New_York regular close (16:00 ET), not UTC hour 16.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, date, datetime, timedelta
from typing import Any, TypedDict
from zoneinfo import ZoneInfo

try:
    from core.heart.event_book import MarketEvent
except ImportError:  # pragma: no cover — synthetic tests only

    class MarketEvent(TypedDict, total=False):
        identity: str
        source: str
        event_type: str
        occurred_at: datetime
        timestamp_precision: str
        symbol: str | None
        mic_code: str | None


# Declared before any golden-set measurement (roadmap §6 Peça 3).
MIN_AUTO_CONFIDENCE = 0.6

SESSION_TZ = "America/New_York"
SESSION_CLOSE_HOUR = 16

# Precedence tiers (highest first). Lower index = higher priority.
_TIER_LULD_HALT = 0
_TIER_SEC_FILING = 1
_TIER_BUSINESS_WIRE = 2
_TIER_RSS_STRUCTURED = 3
_TIER_OTHER = 4

_TIER_CONFIDENCE = {
    _TIER_LULD_HALT: 0.95,
    _TIER_SEC_FILING: 0.85,
    _TIER_BUSINESS_WIRE: 0.75,
    _TIER_RSS_STRUCTURED: 0.65,
    _TIER_OTHER: 0.50,
}


class DailyMove(TypedDict):
    mic_code: str
    symbol: str
    first_seen: str
    session_date: str
    abnormal_ret: float
    gross_ret: float
    surprise_q: float
    ewma_vol: float


class Attribution(TypedDict):
    move_key: str
    event_identity: str | None
    confidence: float
    evidence: dict[str, Any]
    cluster_id: str | None
    human_override: str | None


def session_impact_date(
    occurred_at: datetime,
    *,
    session_tz: str = SESSION_TZ,
    session_close_hour: int = SESSION_CLOSE_HOUR,
) -> date:
    """Map event timestamp to the session whose return it can explain."""
    moment = occurred_at if occurred_at.tzinfo else occurred_at.replace(tzinfo=UTC)
    local = moment.astimezone(ZoneInfo(session_tz))
    if local.hour > session_close_hour or (
        local.hour == session_close_hour and local.minute >= 0
    ):
        return (local + timedelta(days=1)).date()
    return local.date()


def move_key(move: DailyMove) -> str:
    return f"{move['mic_code']}:{move['symbol']}:{move['first_seen']}:{move['session_date']}"


def _event_field(event: MarketEvent | Any, name: str, default: str = "") -> str:
    if isinstance(event, dict):
        return str(event.get(name, default) or default)
    return str(getattr(event, name, default) or default)


def _event_occurred_at(event: MarketEvent | Any) -> datetime:
    if isinstance(event, dict):
        raw = event["occurred_at"]
    else:
        raw = event.occurred_at
    if isinstance(raw, datetime):
        occurred = raw
    else:
        occurred = datetime.fromisoformat(str(raw))
    if occurred.tzinfo is None:
        occurred = occurred.replace(tzinfo=UTC)
    return occurred


def _event_symbol(event: MarketEvent | Any) -> str | None:
    sym = _event_field(event, "symbol", "")
    return sym.upper() if sym else None


def _event_tier(event: MarketEvent | Any) -> int:
    event_type = _event_field(event, "event_type")
    event_type_u = event_type.upper()
    source = _event_field(event, "source").lower()

    if (
        event_type == "nyse.luld_pause"
        or event_type_u in {"LULD", "HALT", "TRADING_HALT"}
        or "halt" in source
    ):
        return _TIER_LULD_HALT
    if event_type_u in {"8-K", "4", "FORM 4", "SC 13D", "SC 13G", "13D", "13G"}:
        return _TIER_SEC_FILING
    if source.startswith("business_wire") or source == "business_wire":
        return _TIER_BUSINESS_WIRE
    if "rss" in source or source.endswith("_rss"):
        return _TIER_RSS_STRUCTURED
    return _TIER_OTHER


def _confidence_for_tier(tier: int) -> float:
    return _TIER_CONFIDENCE[tier]


def _precedence_sort_key(event: MarketEvent | Any) -> tuple[int, datetime, str]:
    occurred = _event_occurred_at(event)
    return (_event_tier(event), occurred, _event_field(event, "identity"))


def _matches_move(move: DailyMove, event: MarketEvent | Any) -> bool:
    sym = _event_symbol(event)
    if sym and sym != move["symbol"].upper():
        return False
    impact = session_impact_date(_event_occurred_at(event))
    move_date = date.fromisoformat(move["session_date"])
    return impact == move_date


def _candidate_evidence(event: MarketEvent | Any) -> dict[str, Any]:
    occurred = _event_occurred_at(event)
    tier = _event_tier(event)
    return {
        "identity": _event_field(event, "identity"),
        "source": _event_field(event, "source"),
        "event_type": _event_field(event, "event_type"),
        "occurred_at": occurred.astimezone(UTC).isoformat(),
        "impact_date": session_impact_date(occurred).isoformat(),
        "tier": tier,
        "confidence": _confidence_for_tier(tier),
    }


def attribute_move(
    move: DailyMove,
    events: Sequence[MarketEvent | Any],
) -> Attribution:
    """Join one move to the best matching event by asymmetric window + precedence."""
    candidates = [ev for ev in events if _matches_move(move, ev)]
    key = move_key(move)

    if not candidates:
        return Attribution(
            move_key=key,
            event_identity=None,
            confidence=0.0,
            evidence={"candidates": [], "reason": "no_event_in_window"},
            cluster_id=None,
            human_override=None,
        )

    ranked = sorted(candidates, key=_precedence_sort_key)
    best = ranked[0]
    tier = _event_tier(best)
    confidence = _confidence_for_tier(tier)
    identity = _event_field(best, "identity")

    evidence: dict[str, Any] = {
        "selected": _candidate_evidence(best),
        "candidates": [_candidate_evidence(ev) for ev in ranked],
        "precedence_tier": tier,
        "min_auto_confidence": MIN_AUTO_CONFIDENCE,
        "auto_accepted": confidence >= MIN_AUTO_CONFIDENCE,
    }

    return Attribution(
        move_key=key,
        event_identity=identity,
        confidence=confidence,
        evidence=evidence,
        cluster_id=identity,
        human_override=None,
    )


def attribute_moves(
    moves: Sequence[DailyMove],
    events: Sequence[MarketEvent | Any],
) -> dict[str, Attribution]:
    """Batch join: one Attribution per move keyed by move_key."""
    if not moves:
        return {}
    return {move_key(m): attribute_move(m, events) for m in moves}
