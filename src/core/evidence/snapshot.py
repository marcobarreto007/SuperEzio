"""C2 Frozen Snapshot — numbers with provenance. Does not bind Bob.

Same facts seal to the same digest. Timestamps (as_of) are stored but excluded
from the hash so C3 can compare snapshot.numbers, not wall-clock.
"""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any

from core.storage.atomic import atomic_write_text

from .pack import canonical_json, pack_digest, sha256_hex

SCHEMA_VERSION = "c2.1"
SNAPSHOT_FILENAME = "snapshot.json"

_HASH_EXCLUDE = frozenset({"integrity", "as_of"})

# name -> (unit, formula_id, provenance fact keys)
_NUMBER_META: dict[str, tuple[str, str, tuple[str, ...]]] = {
    "latest_price": ("quote", "math_hub.price_series", ("price",)),
    "annualized_return": ("fraction", "math_hub.annualized_return", ("ohlcv",)),
    "volatility": ("fraction", "math_hub.volatility", ("ohlcv",)),
    "sharpe": ("ratio", "math_hub.sharpe", ("ohlcv",)),
    "sortino": ("ratio", "math_hub.sortino", ("ohlcv",)),
    "max_drawdown": ("fraction", "math_hub.max_drawdown", ("ohlcv",)),
    "var_95": ("fraction", "math_hub.var_95", ("ohlcv",)),
    "cvar_95": ("fraction", "math_hub.cvar_95", ("ohlcv",)),
    "kelly_fraction": ("fraction", "math_hub.kelly", ("ohlcv",)),
    "crisis_score": ("score", "math_hub.crisis_aggregate", ("ohlcv",)),
    "bootstrap_expected_return": ("fraction", "math_hub.return_bootstrap", ("ohlcv",)),
    "f51_decision_score": ("score", "f51.decision_score", ("ohlcv", "price")),
    "rsi": ("index", "math_hub.rsi14", ("ohlcv",)),
    "macd": ("quote", "math_hub.macd", ("ohlcv",)),
    "sma20": ("quote", "math_hub.sma20", ("ohlcv",)),
    "sma50": ("quote", "math_hub.sma50", ("ohlcv",)),
    "ema20": ("quote", "math_hub.ema20", ("ohlcv",)),
    "vwap": ("quote", "math_hub.vwap", ("ohlcv",)),
}


def payload_for_snapshot_hash(snapshot: dict[str, Any]) -> dict[str, Any]:
    payload = {key: value for key, value in snapshot.items() if key not in _HASH_EXCLUDE}
    price = payload.get("price")
    if isinstance(price, dict):
        payload["price"] = {key: value for key, value in price.items() if key != "as_of"}
    return payload


def seal_snapshot(snapshot: dict[str, Any], *, writer: str = "evidence.snapshot") -> dict[str, Any]:
    sealed = dict(snapshot)
    digest = sha256_hex(canonical_json(payload_for_snapshot_hash(sealed)))
    sealed["integrity"] = {
        "canonical_json_sha256": digest,
        "writer": writer,
        "schema_version": SCHEMA_VERSION,
    }
    return sealed


def verify_snapshot_seal(snapshot: dict[str, Any]) -> bool:
    integrity = snapshot.get("integrity") or {}
    digest = integrity.get("canonical_json_sha256")
    if not isinstance(digest, str) or len(digest) != 64:
        return False
    return digest == sha256_hex(canonical_json(payload_for_snapshot_hash(snapshot)))


def _scalar(value: Any) -> Any:
    if isinstance(value, (int, float, str, bool)) or value is None:
        return value
    return None


def _number(
    *,
    name: str,
    value: Any,
    unit: str,
    formula_id: str,
    provenance: tuple[str, ...],
    computed_by: str,
) -> dict[str, Any] | None:
    scalar = _scalar(value)
    if scalar is None:
        return None
    return {
        "name": name,
        "value": scalar,
        "unit": unit,
        "formula_id": formula_id,
        "provenance": list(provenance),
        "computed_by": computed_by,
    }


def freeze_snapshot(
    *,
    pack: dict[str, Any],
    math_report: dict[str, Any] | None,
    run_id: str,
) -> dict[str, Any]:
    """Project pack facts + MathHub numbers into an immutable snapshot."""
    facts = pack.get("facts") if isinstance(pack.get("facts"), dict) else {}
    ticker = str(pack.get("ticker") or "")
    as_of = str(pack.get("created_at") or "")
    report = math_report if isinstance(math_report, dict) else {}
    math_numbers = report.get("numbers") if isinstance(report.get("numbers"), dict) else {}
    summary = report.get("summary") if isinstance(report.get("summary"), dict) else {}

    price_fact = facts.get("price") if isinstance(facts.get("price"), dict) else {}
    price_block: dict[str, Any] | None = None
    if price_fact.get("status") == "OK":
        price_block = {
            "value": price_fact.get("value"),
            "as_of": price_fact.get("as_of"),
            "provider": price_fact.get("provider") or "unknown",
            "fact_key": "price",
        }

    ohlcv_fact = facts.get("ohlcv") if isinstance(facts.get("ohlcv"), dict) else {}
    series_ref = None
    if ohlcv_fact.get("status") == "OK" and isinstance(ohlcv_fact.get("value"), dict):
        series_ref = dict(ohlcv_fact["value"])

    numbers: dict[str, Any] = {}
    if price_block is not None:
        entry = _number(
            name="price",
            value=price_block["value"],
            unit="quote",
            formula_id="fact.price",
            provenance=("price",),
            computed_by=str(price_block["provider"]),
        )
        if entry is not None:
            numbers["price"] = entry

    for name, (unit, formula_id, provenance) in _NUMBER_META.items():
        value = math_numbers.get(name)
        if value is None:
            value = summary.get(name)
        entry = _number(
            name=name,
            value=value,
            unit=unit,
            formula_id=formula_id,
            provenance=provenance,
            computed_by="math_hub",
        )
        if entry is not None:
            numbers[name] = entry

    try:
        pack_sha = pack_digest(pack)
    except ValueError:
        pack_sha = ""

    body = {
        "snapshot_id": uuid.uuid5(uuid.NAMESPACE_OID, f"snapshot:{run_id}:{ticker}").hex,
        "pack_id": pack.get("pack_id"),
        "pack_sha256": pack_sha,
        "run_id": run_id,
        "ticker": ticker,
        "as_of": as_of,
        "currency": None,
        "frozen": True,
        "price": price_block,
        "series_ref": series_ref,
        "numbers": numbers,
        "schema_version": SCHEMA_VERSION,
    }
    return seal_snapshot(body, writer="core.evidence.snapshot")


def save_snapshot(snapshot: dict[str, Any], dest_dir: Path | str) -> Path:
    directory = Path(dest_dir)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / SNAPSHOT_FILENAME
    atomic_write_text(path, canonical_json(snapshot) + "\n", encoding="utf-8")
    return path


def format_snapshot_binding(snapshot: dict[str, Any]) -> str:
    """Deterministic text for C3. C2 does not inject this into Bob."""
    lines = ["═══ SNAPSHOT FROZEN (cite only these numbers) ═══"]
    numbers = snapshot.get("numbers") if isinstance(snapshot.get("numbers"), dict) else {}
    for name in sorted(numbers):
        item = numbers[name]
        if not isinstance(item, dict):
            continue
        provenance = ",".join(str(part) for part in (item.get("provenance") or []))
        lines.append(
            f"{name}={item.get('value')} unit={item.get('unit')} "
            f"formula={item.get('formula_id')} provenance={provenance}"
        )
    return "\n".join(lines)
