"""Normalize and hash the operator-observed TD order preview before approval."""

from __future__ import annotations

import hashlib
import json
import math
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Mapping


_OFFICIAL_PLATFORMS = {"WEBBROKER", "TD_APP", "ADVANCED_DASHBOARD", "TD_ACTIVE_TRADER"}
_OPERATOR = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{2,63}$")


class TDCostGateError(RuntimeError):
    """Raised when a TD preview omits or contradicts economic cost evidence."""


def _nonnegative(value: Any, field: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise TDCostGateError(f"{field} must be a non-negative number") from exc
    if not math.isfinite(number) or number < 0:
        raise TDCostGateError(f"{field} must be a non-negative number")
    return round(number, 4)


def _timestamp(value: Any, field: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(str(value or "").replace("Z", "+00:00"))
    except ValueError as exc:
        raise TDCostGateError(f"{field} must be an ISO-8601 datetime") from exc
    if parsed.tzinfo is None:
        raise TDCostGateError(f"{field} must include a timezone")
    return parsed.astimezone(timezone.utc)


def _hash(value: Mapping[str, Any]) -> str:
    encoded = json.dumps(dict(value), sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def normalize_td_preview_costs(
    ticket: Mapping[str, Any],
    preview: Mapping[str, Any],
    *,
    actor: str,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Return immutable economic preview evidence or fail closed."""

    current = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    operator = actor.strip()
    if not _OPERATOR.fullmatch(operator):
        raise TDCostGateError("operator identity is invalid")
    if preview.get("commission_confirmed") is not True:
        raise TDCostGateError("TD preview commission must be explicitly confirmed")
    if preview.get("digital_trade") is not True:
        raise TDCostGateError("commission eligibility requires a digital TD trade")
    if preview.get("strategy_order") is not False:
        raise TDCostGateError(
            "strategy orders are not eligible for automatic commission-free status"
        )
    if preview.get("td_easy_trade") is not False:
        raise TDCostGateError("TD Easy Trade is outside this TD Direct workflow")
    platform = str(preview.get("platform") or "").strip().upper()
    if platform not in _OFFICIAL_PLATFORMS:
        raise TDCostGateError("unsupported official TD platform")
    preview_as_of = _timestamp(preview.get("td_preview_as_of"), "td_preview_as_of")
    age_seconds = (current - preview_as_of).total_seconds()
    if age_seconds < -5 or age_seconds > 120:
        raise TDCostGateError("TD preview is stale or future-dated")
    cost_currency = str(preview.get("cost_currency") or "").strip().upper()
    if cost_currency != str(ticket.get("currency") or "").upper():
        raise TDCostGateError("TD preview cost_currency does not match ticket currency")

    commission = _nonnegative(preview.get("estimated_commission"), "estimated_commission")
    spread = _nonnegative(preview.get("estimated_spread"), "estimated_spread")
    fx = _nonnegative(preview.get("estimated_fx"), "estimated_fx")
    ecn = _nonnegative(preview.get("estimated_ecn_fees", 0), "estimated_ecn_fees")
    regulatory = _nonnegative(
        preview.get("estimated_regulatory_fees", 0), "estimated_regulatory_fees"
    )
    other = _nonnegative(preview.get("estimated_other_fees", 0), "estimated_other_fees")
    total = _nonnegative(preview.get("total_estimated_cost"), "total_estimated_cost")
    if abs(total - (commission + spread + fx + ecn + regulatory + other)) > 0.01:
        raise TDCostGateError("total_estimated_cost does not match all cost components")

    conversion_required = preview.get("fx_conversion_required") is True
    fx_rate: float | None = None
    if conversion_required:
        try:
            fx_rate = float(preview.get("fx_rate"))
        except (TypeError, ValueError) as exc:
            raise TDCostGateError("fx_rate is required when TD performs conversion") from exc
        if not math.isfinite(fx_rate) or fx_rate <= 0 or fx <= 0:
            raise TDCostGateError("positive fx_rate and estimated_fx are required for conversion")
    elif fx != 0 or preview.get("fx_rate") not in (None, ""):
        raise TDCostGateError("FX cost/rate requires fx_conversion_required=true")

    commission_evidence = dict(ticket.get("commission") or {})
    eligible = commission_evidence.get("eligible") is True
    eligibility_confirmed = preview.get("commission_free_eligibility_confirmed") is True
    if eligible and commission == 0 and not eligibility_confirmed:
        raise TDCostGateError("zero commission requires explicit eligibility confirmation")
    if ticket.get("require_commission_free") is True and commission != 0:
        raise TDCostGateError(
            "TD preview shows a commission but this ticket requires commission-free"
        )

    economic = {
        "operator": operator,
        "platform": platform,
        "td_preview_as_of": preview_as_of.isoformat(),
        "cost_currency": cost_currency,
        "commission_confirmed": True,
        "commission_free_eligibility_confirmed": eligibility_confirmed,
        "commission_exception": eligible and commission != 0,
        "digital_trade": True,
        "strategy_order": False,
        "td_easy_trade": False,
        "fx_conversion_required": conversion_required,
        "fx_rate": round(fx_rate, 6) if fx_rate is not None else None,
        "estimated_commission": commission,
        "estimated_spread": spread,
        "estimated_fx": fx,
        "estimated_ecn_fees": ecn,
        "estimated_regulatory_fees": regulatory,
        "estimated_other_fees": other,
        "total_estimated_cost": total,
        "commission_manifest_verified_at": commission_evidence.get("verified_at"),
        "commission_manifest_source": commission_evidence.get("source_url"),
    }
    evidence_hash = _hash(economic)
    return {
        **economic,
        "evidence_hash": evidence_hash,
        "validated_at": current.isoformat(),
        "expires_at": (preview_as_of + timedelta(seconds=120)).isoformat(),
        "trust": "OPERATOR_OBSERVED_TD_PREVIEW_SERVER_VALIDATED",
    }
