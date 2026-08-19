"""Fail-closed live order tickets for manual execution in TD Direct Investing Canada.

This module never authenticates to TD, reads WebBroker, or transmits an order. It prepares
an auditable ticket that the operator must independently verify and enter on a TD platform.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
from datetime import datetime, timedelta, timezone
from decimal import ROUND_CEILING, Decimal
from pathlib import Path
from typing import Any, Mapping

from core.paths import resolve_project_path


DEFAULT_TICKET_LOG = resolve_project_path("runtime/td_direct/tickets.jsonl")
DEFAULT_COMMISSION_MANIFEST = resolve_project_path("config/td_direct_commission_free_etfs.json")
_SYMBOL_RE = re.compile(r"^[A-Z0-9]{1,8}(?:[.-][A-Z0-9]{1,4})?$")
_EXCHANGE_CURRENCY = {
    "TSX": "CAD",
    "TSXV": "CAD",
    "NYSE": "USD",
    "NASDAQ": "USD",
    "AMEX": "USD",
}
_FORBIDDEN_SECRET_FIELDS = {
    "account_number",
    "connect_id",
    "cookie",
    "password",
    "refresh_token",
    "session_token",
    "username",
}
_ALLOWED_FIELDS = {
    "account_type",
    "action",
    "currency",
    "exchange",
    "invalidation",
    "limit_price",
    "order_type",
    "position_qty",
    "qty",
    "quantity",
    "quote_as_of",
    "quote_price",
    "quote_source",
    "require_commission_free",
    "risk_budget",
    "side",
    "stop_price",
    "thesis",
    "ticker",
}


class TDDirectTicketError(ValueError):
    """Raised when a TD manual-live ticket cannot be produced safely."""


def _positive_float(value: Any, field: str) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError) as exc:
        raise TDDirectTicketError(f"{field} must be a number") from exc
    if not math.isfinite(parsed) or parsed <= 0:
        raise TDDirectTicketError(f"{field} must be finite and greater than zero")
    return parsed


def _positive_int(value: Any, field: str) -> int:
    if isinstance(value, bool):
        raise TDDirectTicketError(f"{field} must be a positive integer")
    try:
        parsed_float = float(value)
    except (TypeError, ValueError) as exc:
        raise TDDirectTicketError(f"{field} must be a positive integer") from exc
    if not math.isfinite(parsed_float) or parsed_float <= 0 or not parsed_float.is_integer():
        raise TDDirectTicketError(f"{field} must be a positive integer")
    return int(parsed_float)


def _positive_env_float(name: str, default: str) -> float:
    try:
        value = float(os.getenv(name, default))
    except ValueError as exc:
        raise TDDirectTicketError(f"{name} must be a positive finite number") from exc
    if not math.isfinite(value) or value <= 0:
        raise TDDirectTicketError(f"{name} must be a positive finite number")
    return value


def _positive_env_int(name: str, default: str) -> int:
    try:
        value = int(os.getenv(name, default))
    except ValueError as exc:
        raise TDDirectTicketError(f"{name} must be a positive integer") from exc
    if value <= 0:
        raise TDDirectTicketError(f"{name} must be a positive integer")
    return value


def _utc_datetime(value: Any, field: str) -> datetime:
    if isinstance(value, datetime):
        parsed = value
    else:
        text = str(value or "").strip()
        if not text:
            raise TDDirectTicketError(f"{field} is required")
        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError as exc:
            raise TDDirectTicketError(f"{field} must be an ISO-8601 datetime") from exc
    if parsed.tzinfo is None:
        raise TDDirectTicketError(f"{field} must include a timezone")
    return parsed.astimezone(timezone.utc)


def _normalize_symbol(raw_symbol: Any, exchange: str) -> tuple[str, str | None]:
    original = str(raw_symbol or "").strip().upper()
    symbol = original
    note = None
    if exchange == "TSX" and symbol.endswith(".TO"):
        symbol = symbol[:-3]
        note = f"Normalized market-data symbol {original} to WebBroker symbol {symbol}."
    elif exchange == "TSXV" and symbol.endswith(".V"):
        symbol = symbol[:-2]
        note = f"Normalized market-data symbol {original} to WebBroker symbol {symbol}."
    if exchange in {"TSX", "TSXV"} and "-" in symbol:
        symbol = symbol.replace("-", ".")
        note = f"Normalized market-data symbol {original} to WebBroker symbol {symbol}."
    if not symbol or not _SYMBOL_RE.fullmatch(symbol):
        raise TDDirectTicketError("ticker has an unsupported format")
    return symbol, note


def td_commission_eligibility(
    symbol: str,
    exchange: str,
    *,
    manifest_path: str | Path | None = None,
) -> dict[str, Any]:
    """Return evidence-backed TD commission-free eligibility for one simple digital ETF trade."""

    path = Path(manifest_path) if manifest_path is not None else DEFAULT_COMMISSION_MANIFEST
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
        verified_date = datetime.fromisoformat(str(manifest["verified_at"])).date()
        manifest_age_days = (datetime.now(timezone.utc).date() - verified_date).days
        max_age_days = _positive_env_int("SUPEREZIO_TD_COMMISSION_LIST_MAX_AGE_DAYS", "7")
        if manifest_age_days < 0 or manifest_age_days > max_age_days:
            raise ValueError("commission-free manifest is stale or future-dated")
        country = "CAN" if exchange in {"TSX", "TSXV"} else "US"
        symbols = manifest["symbols"][country]
        if not isinstance(symbols, list):
            raise TypeError("symbols must be a list")
        eligible = symbol.upper() in {str(item).upper() for item in symbols}
        return {
            "status": "ELIGIBLE" if eligible else "NOT_LISTED",
            "eligible": eligible,
            "estimated_base_commission": 0.0 if eligible else None,
            "currency": "CAD" if country == "CAN" else "USD",
            "verified_at": str(manifest["verified_at"]),
            "source_url": str(manifest["source_url"]),
            "conditions": list(manifest.get("conditions") or []),
            "operator_must_confirm_td_preview": True,
            "venue_verified": False,
        }
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError, TDDirectTicketError):
        return {
            "status": "UNKNOWN",
            "eligible": None,
            "estimated_base_commission": None,
            "currency": None,
            "verified_at": None,
            "source_url": None,
            "conditions": [],
            "operator_must_confirm_td_preview": True,
            "venue_verified": False,
        }


def load_td_commission_free_manifest(
    manifest_path: str | Path | None = None,
) -> dict[str, Any]:
    """Load and minimally validate the official TD commission-free ETF snapshot."""

    path = Path(manifest_path) if manifest_path is not None else DEFAULT_COMMISSION_MANIFEST
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
        canadian = manifest["symbols"]["CAN"]
        us = manifest["symbols"]["US"]
        if not isinstance(canadian, list) or not isinstance(us, list):
            raise TypeError("symbol collections must be lists")
        symbols = [str(item).strip().upper() for item in [*canadian, *us]]
        if any(not symbol for symbol in symbols) or len(symbols) != len(set(symbols)):
            raise ValueError("commission-free symbols must be non-empty and unique")
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise TDDirectTicketError(
            "TD commission-free ETF manifest is unavailable or invalid"
        ) from exc
    return manifest


def build_td_direct_ticket(
    payload: Mapping[str, Any],
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Build a short-lived, non-transmitting TD Direct Investing order ticket."""

    supplied_secret_fields = sorted(
        field for field in _FORBIDDEN_SECRET_FIELDS if payload.get(field) not in (None, "")
    )
    if supplied_secret_fields:
        raise TDDirectTicketError(
            "TD credentials/account identifiers are forbidden: " + ", ".join(supplied_secret_fields)
        )
    unknown_fields = sorted(str(field) for field in payload if field not in _ALLOWED_FIELDS)
    if unknown_fields:
        raise TDDirectTicketError("unsupported fields: " + ", ".join(unknown_fields))

    current = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    exchange = str(payload.get("exchange") or "").strip().upper()
    if exchange not in _EXCHANGE_CURRENCY:
        raise TDDirectTicketError(
            "exchange must be one of: " + ", ".join(sorted(_EXCHANGE_CURRENCY))
        )
    expected_currency = _EXCHANGE_CURRENCY[exchange]
    currency = str(payload.get("currency") or "").strip().upper()
    if currency != expected_currency:
        raise TDDirectTicketError(
            f"currency {currency or 'missing'} does not match {exchange} ({expected_currency})"
        )

    symbol, normalization_note = _normalize_symbol(payload.get("ticker"), exchange)
    commission = td_commission_eligibility(symbol, exchange)
    require_commission_free = payload.get("require_commission_free") is True
    if require_commission_free and commission["eligible"] is not True:
        raise TDDirectTicketError(
            f"{symbol} is not proven commission-free for a simple digital TD Direct trade"
        )
    side = str(payload.get("side") or payload.get("action") or "").strip().upper()
    if side not in {"BUY", "SELL"}:
        raise TDDirectTicketError("side must be BUY or SELL")
    order_type = str(payload.get("order_type") or "LIMIT").strip().upper()
    if order_type != "LIMIT":
        raise TDDirectTicketError("initial TD live mode supports LIMIT orders only")

    quantity = _positive_int(payload.get("quantity", payload.get("qty")), "quantity")
    limit_price = _positive_float(payload.get("limit_price"), "limit_price")
    quote_price = _positive_float(payload.get("quote_price"), "quote_price")
    quote_as_of = _utc_datetime(payload.get("quote_as_of"), "quote_as_of")
    quote_source = str(payload.get("quote_source") or "").strip()
    if not quote_source:
        raise TDDirectTicketError("quote_source is required")

    max_quote_age = _positive_env_int("SUPEREZIO_TD_TICKET_MAX_QUOTE_AGE_SEC", "120")
    quote_age = (current - quote_as_of).total_seconds()
    if quote_age < -5:
        raise TDDirectTicketError("quote_as_of is in the future")
    if quote_age > max_quote_age:
        raise TDDirectTicketError(
            f"quote is stale ({int(quote_age)}s old; maximum {max_quote_age}s)"
        )

    max_deviation_pct = _positive_env_float("SUPEREZIO_TD_TICKET_MAX_LIMIT_DEVIATION_PCT", "2")
    deviation_pct = abs(limit_price - quote_price) / quote_price * 100
    if deviation_pct > max_deviation_pct:
        raise TDDirectTicketError(
            f"limit price deviates {deviation_pct:.2f}% from quote; maximum {max_deviation_pct:.2f}%"
        )

    thesis = str(payload.get("thesis") or "").strip()
    invalidation = str(payload.get("invalidation") or "").strip()
    if len(thesis) < 12:
        raise TDDirectTicketError("thesis must contain at least 12 characters")
    if len(invalidation) < 12:
        raise TDDirectTicketError("invalidation must contain at least 12 characters")
    if len(thesis) > 500 or len(invalidation) > 500 or len(quote_source) > 100:
        raise TDDirectTicketError("quote_source, thesis, or invalidation exceeds its size limit")

    stop_price: float | None = None
    risk_budget: float | None = None
    planned_stop_risk: float | None = None
    position_qty: int | None = None
    if side == "BUY":
        stop_price = _positive_float(payload.get("stop_price"), "stop_price")
        if stop_price >= limit_price:
            raise TDDirectTicketError("BUY stop_price must be below limit_price")
        risk_budget = _positive_float(payload.get("risk_budget"), "risk_budget")
        exact_stop_risk = (Decimal(str(limit_price)) - Decimal(str(stop_price))) * quantity
        if exact_stop_risk > Decimal(str(risk_budget)):
            raise TDDirectTicketError(
                f"planned stop risk {exact_stop_risk:.4f} exceeds risk budget "
                f"{risk_budget:.2f} {currency}"
            )
        planned_stop_risk = float(exact_stop_risk.quantize(Decimal("0.01"), rounding=ROUND_CEILING))
    else:
        position_qty = _positive_int(payload.get("position_qty"), "position_qty")
        if quantity > position_qty:
            raise TDDirectTicketError(
                "SELL quantity exceeds declared position; short selling is blocked"
            )

    account_type = str(payload.get("account_type") or "").strip().upper()
    if account_type not in {"CASH", "MARGIN", "TFSA", "FHSA", "RRSP"}:
        raise TDDirectTicketError("account_type must be CASH, MARGIN, TFSA, FHSA, or RRSP")

    notional = round(limit_price * quantity, 2)
    max_notional = _positive_env_float("SUPEREZIO_TD_TICKET_MAX_NOTIONAL", "25000")
    if notional > max_notional:
        raise TDDirectTicketError(
            f"notional {notional:.2f} exceeds draft limit {max_notional:.2f} {currency}"
        )
    canonical = {
        "symbol": symbol,
        "exchange": exchange,
        "currency": currency,
        "side": side,
        "quantity": quantity,
        "order_type": order_type,
        "limit_price": round(limit_price, 4),
        "stop_price": round(stop_price, 4) if stop_price is not None else None,
        "account_type": account_type,
        "commission": commission,
        "quote_as_of": quote_as_of.isoformat(),
    }
    fingerprint = hashlib.sha256(
        json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    ticket_id = f"td-live-{current.strftime('%Y%m%dT%H%M%SZ')}-{fingerprint[:12]}"
    expires_at = quote_as_of + timedelta(seconds=max_quote_age)

    warnings = [
        "NOT AN ORDER: nothing was transmitted to TD Direct Investing.",
        "Verify the live TD snap quote, buying power, account, symbol, currency, and quantity.",
        "Enter and transmit the order yourself in WebBroker, TD app, Advanced Dashboard, or TD Active Trader.",
        "Do not submit after expires_at; regenerate the ticket with a fresh quote.",
        "Planned stop risk is not a maximum loss; gaps, slippage, fees, and FX can increase loss.",
    ]
    if normalization_note:
        warnings.append(normalization_note)

    return {
        "ticket_id": ticket_id,
        "fingerprint": fingerprint,
        "broker": "TD_DIRECT_INVESTING_CANADA",
        "execution_mode": "LIVE_MANUAL",
        "status": "DRAFT_UNVERIFIED_QUOTE",
        "phase": "independent_quote_verification_required",
        "submitted_to_broker": False,
        "transmission_capability": False,
        "ready_for_execution": False,
        "symbol": symbol,
        "input_symbol": str(payload.get("ticker") or "").strip().upper(),
        "exchange": exchange,
        "currency": currency,
        "side": side,
        "quantity": quantity,
        "order_type": order_type,
        "limit_price": round(limit_price, 4),
        "stop_price": round(stop_price, 4) if stop_price is not None else None,
        "position_qty": position_qty,
        "notional": notional,
        "risk_budget": round(risk_budget, 2) if risk_budget is not None else None,
        "planned_stop_risk": planned_stop_risk,
        "account_type": account_type,
        "commission": commission,
        "thesis": thesis,
        "invalidation": invalidation,
        "quote": {
            "price": round(quote_price, 4),
            "source": quote_source,
            "as_of": quote_as_of.isoformat(),
            "age_seconds": max(0, round(quote_age, 3)),
            "limit_deviation_pct": round(deviation_pct, 4),
            "trust": "UNVERIFIED_CLIENT_ASSERTION",
        },
        "required_gates": {
            "server_side_quote": False,
            "money_gate": False,
            "portfolio_risk": False,
            "buying_power": False,
            "td_order_preview": False,
        },
        "created_at": current.isoformat(),
        "expires_at": expires_at.isoformat(),
        "manual_checklist": [
            "Open an official TD Direct Investing platform yourself.",
            "Select the declared account type; never paste an account number into SuperEzio.",
            "Confirm symbol, exchange, currency, side, quantity, and LIMIT price.",
            "Confirm the live TD quote and buying power/position immediately before transmit.",
            "Transmit manually, then record TD's order confirmation separately.",
        ],
        "warnings": warnings,
    }


def append_td_direct_ticket(
    ticket: Mapping[str, Any],
    path: str | Path | None = None,
) -> Path:
    """Claim and append one ticket to the local audit log.

    The exclusive claim is intentionally retained if the append fails. A poisoned claim is
    safer than silently allowing the operator to generate the same live ticket twice; a fresh
    quote produces a different fingerprint.
    """

    target = Path(path) if path is not None else DEFAULT_TICKET_LOG
    target.parent.mkdir(parents=True, exist_ok=True)
    fingerprint = str(ticket.get("fingerprint") or "").strip().lower()
    if not re.fullmatch(r"[0-9a-f]{64}", fingerprint):
        raise TDDirectTicketError("ticket fingerprint is missing or invalid")

    claims_dir = target.parent / "claims"
    claims_dir.mkdir(parents=True, exist_ok=True)
    claim_path = claims_dir / f"{fingerprint}.json"
    claim_flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, "O_BINARY", 0)
    try:
        claim_descriptor = os.open(claim_path, claim_flags, 0o600)
    except FileExistsError as exc:
        if target.exists():
            for raw_line in target.read_text(encoding="utf-8").splitlines():
                try:
                    existing = json.loads(raw_line)
                except json.JSONDecodeError:
                    continue
                if str(existing.get("fingerprint") or "").lower() == fingerprint:
                    return target
        raise TDDirectTicketError(
            "incomplete TD ticket audit claim requires dead-letter replay"
        ) from exc
    try:
        claim = json.dumps(
            {"ticket_id": ticket.get("ticket_id"), "fingerprint": fingerprint},
            sort_keys=True,
        ).encode("utf-8")
        os.write(claim_descriptor, claim)
        os.fsync(claim_descriptor)
    finally:
        os.close(claim_descriptor)

    line = (json.dumps(dict(ticket), ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8")
    flags = os.O_APPEND | os.O_CREAT | os.O_WRONLY | getattr(os, "O_BINARY", 0)
    descriptor = os.open(target, flags, 0o600)
    try:
        offset = 0
        while offset < len(line):
            offset += os.write(descriptor, line[offset:])
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    return target


def replay_td_direct_ticket_audit(
    ticket: Mapping[str, Any],
    path: str | Path | None = None,
) -> Path:
    """Repair an incomplete claimed audit append without creating a new ticket claim."""

    target = Path(path) if path is not None else DEFAULT_TICKET_LOG
    fingerprint = str(ticket.get("fingerprint") or "").strip().lower()
    if not re.fullmatch(r"[0-9a-f]{64}", fingerprint):
        raise TDDirectTicketError("ticket fingerprint is missing or invalid")
    claim_path = target.parent / "claims" / f"{fingerprint}.json"
    try:
        claim = json.loads(claim_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise TDDirectTicketError("TD ticket audit claim is unavailable or corrupt") from exc
    if claim.get("fingerprint") != fingerprint or claim.get("ticket_id") != ticket.get("ticket_id"):
        raise TDDirectTicketError("TD ticket audit claim does not match the durable ticket")
    if target.exists():
        for raw_line in target.read_text(encoding="utf-8").splitlines():
            try:
                existing = json.loads(raw_line)
            except json.JSONDecodeError:
                continue
            if str(existing.get("fingerprint") or "").lower() == fingerprint:
                return target

    replay_lock = claim_path.with_suffix(".replay.lock")
    lock_flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, "O_BINARY", 0)
    try:
        lock_descriptor = os.open(replay_lock, lock_flags, 0o600)
    except FileExistsError as exc:
        raise TDDirectTicketError("TD ticket audit replay is already claimed") from exc
    try:
        os.write(lock_descriptor, str(ticket.get("ticket_id") or "").encode("utf-8"))
        os.fsync(lock_descriptor)
    finally:
        os.close(lock_descriptor)

    line = (json.dumps(dict(ticket), ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8")
    flags = os.O_APPEND | os.O_CREAT | os.O_WRONLY | getattr(os, "O_BINARY", 0)
    descriptor = os.open(target, flags, 0o600)
    try:
        offset = 0
        while offset < len(line):
            offset += os.write(descriptor, line[offset:])
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    try:
        replay_lock.unlink()
    except OSError:
        pass
    return target
