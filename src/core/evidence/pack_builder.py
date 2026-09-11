"""Build a shadow EvidencePack from the live PipelineState.

C1: observe only. INSUFFICIENT does not abort the turn. Nothing in agent.py
reads this pack. Required facts by route start measuring coverage so C4
can fail-closed without guessing.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from .arch_flags import is_arch_c1_enabled
from .pack import SCHEMA_VERSION, canonical_json, seal_pack, sha256_hex

__all__ = [
    "build_evidence_pack_from_state",
    "is_arch_c1_enabled",
]

# ticker_analysis needs a price and a series. Crisis macro is requested so
# coverage.missing is honest; it is NOT required in C1 (that would mark
# almost every current run INSUFFICIENT and change the operator's reading
# of health without yet changing decisions).
_ROUTE_REQUIRED: dict[str, tuple[str, ...]] = {
    "ticker_analysis": ("price", "ohlcv"),
    "market_scan": ("scan_candidates",),
}
_ALWAYS_REQUEST: tuple[str, ...] = (
    "price",
    "ohlcv",
    "macro_observations",
    "news",
    "sentiment",
)


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _route_of(state: dict[str, Any]) -> str:
    route = str(state.get("route") or "").strip()
    if route:
        return route
    if state.get("scan"):
        return "market_scan"
    if state.get("ticker") or _as_dict(state.get("data")).get("ticker"):
        return "ticker_analysis"
    return "general"


def _fact(
    *,
    key: str,
    value: Any,
    unit: str,
    provider: str,
    status: str,
    as_of: str,
    call_ref: str = "",
    latency_ms: int | None = None,
) -> dict[str, Any]:
    return {
        "key": key,
        "value": value,
        "unit": unit,
        "as_of": as_of,
        "provider": provider,
        "call_ref": call_ref,
        "latency_ms": latency_ms,
        "status": status,
    }


def _missing(key: str, as_of: str) -> dict[str, Any]:
    return _fact(
        key=key,
        value=None,
        unit="",
        provider="",
        status="MISSING",
        as_of=as_of,
    )


def _price_fact(state: dict[str, Any], as_of: str) -> dict[str, Any]:
    data = _as_dict(state.get("data"))
    price_obj = data.get("price")
    provider = "unknown"
    value: Any = None
    if isinstance(price_obj, dict):
        value = price_obj.get("price", price_obj.get("value", price_obj.get("close")))
        provider = str(
            price_obj.get("source") or price_obj.get("provider") or data.get("source") or "unknown"
        )
    elif isinstance(price_obj, (int, float)):
        value = float(price_obj)
        provider = str(data.get("source") or "unknown")
    if value is None:
        math_report = _as_dict(state.get("math_report"))
        value = _as_dict(math_report.get("summary")).get("latest_price")
        if value is not None:
            provider = "math_hub"
    if value is None:
        return _missing("price", as_of)
    return _fact(
        key="price",
        value=value,
        unit="quote",
        provider=provider,
        status="OK",
        as_of=as_of,
        call_ref="state.data.price|math_report.summary.latest_price",
    )


def _ohlcv_fact(state: dict[str, Any], as_of: str) -> dict[str, Any]:
    data = _as_dict(state.get("data"))
    candles = data.get("ohlcv")
    if not isinstance(candles, list) or not candles:
        return _missing("ohlcv", as_of)
    closes: list[float] = []
    for row in candles:
        if not isinstance(row, dict):
            continue
        close = row.get("close")
        try:
            closes.append(float(close))
        except (TypeError, ValueError):
            continue
    digest = sha256_hex(canonical_json(closes)) if closes else ""
    return _fact(
        key="ohlcv",
        value={
            "rows": len(candles),
            "closes": len(closes),
            "first_close": closes[0] if closes else None,
            "last_close": closes[-1] if closes else None,
            "series_sha256": digest,
        },
        unit="bars",
        provider=str(_as_dict(data.get("price")).get("source") or data.get("source") or "unknown"),
        status="OK",
        as_of=as_of,
        call_ref="state.data.ohlcv",
    )


def _list_fact(
    state: dict[str, Any], key: str, path: tuple[str, ...], as_of: str
) -> dict[str, Any]:
    cursor: Any = state
    for part in path:
        if isinstance(cursor, dict):
            cursor = cursor.get(part)
        else:
            cursor = None
            break
    if isinstance(cursor, list) and cursor:
        return _fact(
            key=key,
            value={"count": len(cursor)},
            unit="items",
            provider=key,
            status="OK",
            as_of=as_of,
            call_ref=".".join(("state", *path)),
        )
    if isinstance(cursor, dict) and cursor:
        return _fact(
            key=key,
            value={"keys": sorted(str(item) for item in cursor)[:20]},
            unit="map",
            provider=key,
            status="OK",
            as_of=as_of,
            call_ref=".".join(("state", *path)),
        )
    return _missing(key, as_of)


def _scan_fact(state: dict[str, Any], as_of: str) -> dict[str, Any]:
    scan = _as_dict(state.get("scan"))
    candidates = scan.get("candidates")
    if isinstance(candidates, list) and candidates:
        return _fact(
            key="scan_candidates",
            value={"count": len(candidates)},
            unit="tickers",
            provider="scanner",
            status="OK",
            as_of=as_of,
            call_ref="state.scan.candidates",
        )
    return _missing("scan_candidates", as_of)


def build_evidence_pack_from_state(
    state: dict[str, Any],
    *,
    run_id: str,
    requested_by: str = "pipeline.stream",
    created_at: str | None = None,
) -> dict[str, Any]:
    """Project current pipeline state into the C1 EvidencePack schema."""
    as_of = created_at or _now()
    route = _route_of(state)
    ticker = str(state.get("ticker") or _as_dict(state.get("data")).get("ticker") or "").upper()
    required = _ROUTE_REQUIRED.get(route, ())
    request_keys = list(dict.fromkeys([*required, *_ALWAYS_REQUEST]))
    if route == "market_scan":
        request_keys = list(dict.fromkeys(["scan_candidates", *request_keys]))

    facts: dict[str, Any] = {
        "price": _price_fact(state, as_of),
        "ohlcv": _ohlcv_fact(state, as_of),
        "macro_observations": _list_fact(
            state, "macro_observations", ("data", "macro_observations"), as_of
        ),
        "news": _list_fact(state, "news", ("data", "news"), as_of),
        "sentiment": _list_fact(state, "sentiment", ("data", "sentiment"), as_of),
        "scan_candidates": _scan_fact(state, as_of),
    }
    facts = {key: facts[key] for key in request_keys if key in facts}

    missing = [
        key for key in required if facts.get(key, {}).get("status") in {None, "MISSING", "ERROR"}
    ]
    stale = [key for key, fact in facts.items() if fact.get("status") == "STALE"]
    present = sum(1 for key in required if facts.get(key, {}).get("status") == "OK")
    optional_missing = any(fact.get("status") == "MISSING" for fact in facts.values())
    if required and missing:
        status: str = "INSUFFICIENT"
    elif required and (present < len(required) or optional_missing):
        status = "PARTIAL"
    else:
        status = "COMPLETE"

    pack = {
        "pack_id": uuid.uuid5(uuid.NAMESPACE_OID, f"{run_id}:{ticker}:{route}").hex,
        "run_id": run_id,
        "created_at": as_of,
        "ticker": ticker,
        "requested_by": requested_by,
        "route": route,
        "requests": [
            {
                "key": key,
                "required": key in required,
                "max_staleness_s": 120 if key == "price" else 86400,
            }
            for key in facts
        ],
        "facts": facts,
        "coverage": {
            "required": len(required),
            "present": present,
            "missing": missing,
            "stale": stale,
        },
        "status": status,
        "schema_version": SCHEMA_VERSION,
    }
    return seal_pack(pack, writer="core.evidence.pack_builder")
