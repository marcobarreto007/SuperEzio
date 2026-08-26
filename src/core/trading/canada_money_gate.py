"""Fail-closed Canadian portfolio and buying-power gate for manual TD tickets."""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections.abc import Mapping
from datetime import UTC, date, datetime, time
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from core.config.settings import Settings, get_settings
from core.trading.kill_switch import get_kill_switch
from core.trading.workflow_store import TradeWorkflowStore, WorkflowConflictError

_ACCOUNT_ALIAS = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{2,31}$")
_OPERATOR = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{2,63}$")
_OFFICIAL_PLATFORMS = {"WEBBROKER", "TD_APP", "ADVANCED_DASHBOARD", "TD_ACTIVE_TRADER"}


class CanadaMoneyGateError(RuntimeError):
    """Raised when portfolio evidence or a Canadian money limit fails closed."""


class PositionSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid")

    symbol: str = Field(min_length=1, max_length=32)
    quantity: float
    market_value_cad: float = Field(ge=0)
    currency: Literal["CAD", "USD"]
    sector: str = Field(min_length=2, max_length=64)

    @field_validator("symbol")
    @classmethod
    def normalize_symbol(cls, value: str) -> str:
        return value.strip().upper()

    @field_validator("quantity")
    @classmethod
    def finite_quantity(cls, value: float) -> float:
        if not math.isfinite(value):
            raise ValueError("quantity must be finite")
        return value


class TDAccountSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid")

    account_alias: str
    account_type: Literal["TFSA", "RRSP", "FHSA", "CASH", "MARGIN"]
    base_currency: Literal["CAD"]
    equity_cad: float = Field(gt=0)
    buying_power_cad: float = Field(ge=0)
    cash_cad: float
    margin_enabled: bool
    captured_at: datetime
    operator: str
    source_platform: str
    attested_from_td: Literal[True]
    positions: list[PositionSnapshot] = Field(default_factory=list, max_length=500)

    @field_validator("account_alias")
    @classmethod
    def valid_alias(cls, value: str) -> str:
        normalized = value.strip()
        if not _ACCOUNT_ALIAS.fullmatch(normalized):
            raise ValueError("account_alias must be a non-sensitive local label")
        return normalized

    @field_validator("operator")
    @classmethod
    def valid_operator(cls, value: str) -> str:
        normalized = value.strip()
        if not _OPERATOR.fullmatch(normalized):
            raise ValueError("operator identity is invalid")
        return normalized

    @field_validator("source_platform")
    @classmethod
    def official_platform(cls, value: str) -> str:
        normalized = value.strip().upper()
        if normalized not in _OFFICIAL_PLATFORMS:
            raise ValueError("source_platform is not an official TD platform")
        return normalized

    @field_validator("equity_cad", "buying_power_cad", "cash_cad")
    @classmethod
    def finite_money(cls, value: float) -> float:
        if not math.isfinite(value):
            raise ValueError("money values must be finite")
        return value

    @field_validator("captured_at")
    @classmethod
    def timezone_required(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("captured_at must include a timezone")
        return value


def _canonical_hash(value: Mapping[str, Any]) -> str:
    body = json.dumps(dict(value), sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


def resolve_usd_cad_evidence(*, now: datetime | None = None) -> dict[str, Any]:
    """Read the official Bank of Canada daily USD/CAD observation server-side."""

    from data.boc_provider import get_usd_cad

    current = (now or datetime.now(UTC)).astimezone(UTC)
    result = get_usd_cad()
    if result.get("error"):
        raise CanadaMoneyGateError("Bank of Canada USD/CAD evidence is unavailable")
    try:
        rate = float(result["current_value"])
        observed_date = date.fromisoformat(str(result["date"]))
    except (KeyError, TypeError, ValueError) as exc:
        raise CanadaMoneyGateError("Bank of Canada USD/CAD evidence is invalid") from exc
    if not math.isfinite(rate) or rate <= 0:
        raise CanadaMoneyGateError("Bank of Canada USD/CAD rate is invalid")
    observed_at = datetime.combine(observed_date, time.min, tzinfo=UTC)
    age_days = (current.date() - observed_date).days
    if age_days < 0 or age_days > 7:
        raise CanadaMoneyGateError("Bank of Canada USD/CAD evidence is stale or future-dated")
    evidence = {
        "pair": "USD/CAD",
        "rate": round(rate, 6),
        "observed_at": observed_at.isoformat(),
        "server_acquired_at": current.isoformat(),
        "source": "BANK_OF_CANADA_VALET_FXUSDCAD",
        "age_days": age_days,
        "stale_fallback_used": False,
    }
    evidence["evidence_hash"] = _canonical_hash(evidence)
    return evidence


class CanadaMoneyGate:
    """Compute limits in CAD and reserve buying power before human approval."""

    def __init__(self, store: TradeWorkflowStore, *, settings: Settings | None = None) -> None:
        self.store = store
        self.settings = settings or get_settings()

    def evaluate(
        self,
        ticket: Mapping[str, Any],
        snapshot_payload: Mapping[str, Any],
        *,
        operator: str,
        fx_evidence: Mapping[str, Any] | None = None,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        current = (now or datetime.now(UTC)).astimezone(UTC)
        try:
            snapshot = TDAccountSnapshot.model_validate(snapshot_payload)
        except ValidationError as exc:
            raise CanadaMoneyGateError(
                f"invalid TD account snapshot: {exc.errors()[0]['msg']}"
            ) from exc
        captured_at = snapshot.captured_at.astimezone(UTC)
        age_seconds = (current - captured_at).total_seconds()
        if (
            age_seconds < -5
            or age_seconds > self.settings.superezio_money_gate_snapshot_max_age_sec
        ):
            raise CanadaMoneyGateError("TD account snapshot is stale or future-dated")
        if snapshot.operator != operator:
            raise CanadaMoneyGateError("snapshot operator does not match authenticated operator")
        if snapshot.account_type != str(ticket.get("account_type") or "").upper():
            raise CanadaMoneyGateError("snapshot account_type does not match ticket")
        registered = snapshot.account_type in {"TFSA", "RRSP", "FHSA"}
        if (registered or snapshot.account_type == "CASH") and snapshot.margin_enabled:
            raise CanadaMoneyGateError(f"{snapshot.account_type} cannot use margin")
        if snapshot.account_type == "MARGIN" and not snapshot.margin_enabled:
            raise CanadaMoneyGateError("MARGIN snapshot must explicitly confirm margin_enabled")
        if snapshot.account_type != "MARGIN" and snapshot.cash_cad < 0:
            raise CanadaMoneyGateError(f"{snapshot.account_type} cash cannot be negative")
        if any(position.quantity < 0 for position in snapshot.positions):
            raise CanadaMoneyGateError("short positions block the conservative Canadian money gate")
        if snapshot.equity_cad < self.settings.superezio_money_gate_min_equity_cad:
            raise CanadaMoneyGateError("account equity is below the configured minimum")

        ticket_currency = str(ticket.get("currency") or "").upper()
        if ticket_currency == "CAD":
            fx_rate = 1.0
            normalized_fx = {
                "pair": "CAD/CAD",
                "rate": 1.0,
                "source": "IDENTITY",
                "stale_fallback_used": False,
                "evidence_hash": "0" * 64,
            }
        elif ticket_currency == "USD":
            normalized_fx = dict(fx_evidence or {})
            if (
                normalized_fx.get("pair") != "USD/CAD"
                or normalized_fx.get("stale_fallback_used") is not False
                or not re.fullmatch(r"[0-9a-f]{64}", str(normalized_fx.get("evidence_hash") or ""))
            ):
                raise CanadaMoneyGateError("verified server-side USD/CAD evidence is required")
            try:
                fx_rate = float(normalized_fx["rate"])
            except (KeyError, TypeError, ValueError) as exc:
                raise CanadaMoneyGateError("USD/CAD rate is invalid") from exc
            if not math.isfinite(fx_rate) or fx_rate <= 0:
                raise CanadaMoneyGateError("USD/CAD rate is invalid")
        else:
            raise CanadaMoneyGateError("ticket currency is unsupported")

        quantity = float(ticket.get("quantity") or 0)
        limit_price = float(ticket.get("limit_price") or 0)
        planned_stop_risk = float(ticket.get("planned_stop_risk") or 0)
        if quantity <= 0 or limit_price <= 0 or planned_stop_risk < 0:
            raise CanadaMoneyGateError("ticket sizing inputs are invalid")
        notional_cad = quantity * limit_price * fx_rate
        slippage_cad = notional_cad * self.settings.superezio_money_gate_slippage_bps / 10_000
        gap_risk_cad = (
            planned_stop_risk * fx_rate * self.settings.superezio_money_gate_gap_multiplier
        )
        worst_loss_cad = gap_risk_cad + slippage_cad
        equity = snapshot.equity_cad

        symbol = str(ticket.get("symbol") or "").upper()
        position = next((item for item in snapshot.positions if item.symbol == symbol), None)
        current_symbol_value = float(position.market_value_cad) if position else 0.0
        current_gross = sum(float(item.market_value_cad) for item in snapshot.positions)
        if snapshot.account_type != "MARGIN":
            balance_delta = abs(snapshot.equity_cad - (snapshot.cash_cad + current_gross))
            if balance_delta > max(50.0, snapshot.equity_cad * 0.02):
                raise CanadaMoneyGateError(
                    "TD snapshot equity does not reconcile with cash and positions"
                )
        current_non_cad = sum(
            float(item.market_value_cad) for item in snapshot.positions if item.currency != "CAD"
        )
        sector = position.sector if position else str(ticket.get("sector") or "UNCLASSIFIED")
        current_sector = sum(
            float(item.market_value_cad) for item in snapshot.positions if item.sector == sector
        )
        side = str(ticket.get("side") or "").upper()
        if side == "SELL":
            if position is None or quantity > position.quantity:
                raise CanadaMoneyGateError("SELL quantity exceeds the attested TD position")
            reduction = min(notional_cad, current_symbol_value)
            post_symbol = max(0.0, current_symbol_value - reduction)
            post_gross = max(0.0, current_gross - reduction)
            post_sector = max(0.0, current_sector - reduction)
            post_non_cad = max(
                0.0, current_non_cad - (reduction if ticket_currency != "CAD" else 0)
            )
            required_buying_power = 0.0
        elif side == "BUY":
            post_symbol = current_symbol_value + notional_cad
            post_gross = current_gross + notional_cad
            post_sector = current_sector + notional_cad
            post_non_cad = current_non_cad + (notional_cad if ticket_currency != "CAD" else 0)
            required_buying_power = notional_cad + slippage_cad
        else:
            raise CanadaMoneyGateError("ticket side is unsupported")

        metrics = {
            "notional_cad": round(notional_cad, 2),
            "required_buying_power_cad": round(required_buying_power, 2),
            "worst_loss_cad": round(worst_loss_cad, 2),
            "risk_pct_equity": round(worst_loss_cad / equity * 100, 6),
            "notional_pct_equity": round(notional_cad / equity * 100, 6),
            "post_symbol_pct_equity": round(post_symbol / equity * 100, 6),
            "post_sector_pct_equity": round(post_sector / equity * 100, 6),
            "post_non_cad_pct_equity": round(post_non_cad / equity * 100, 6),
            "post_gross_pct_equity": round(post_gross / equity * 100, 6),
        }
        limits = {
            "max_risk_pct": self.settings.superezio_money_gate_max_risk_pct,
            "max_notional_pct": self.settings.superezio_money_gate_max_notional_pct,
            "max_symbol_pct": self.settings.superezio_money_gate_max_symbol_pct,
            "max_sector_pct": self.settings.superezio_money_gate_max_sector_pct,
            "max_non_cad_pct": self.settings.superezio_money_gate_max_non_cad_pct,
            "max_gross_pct": self.settings.superezio_money_gate_max_gross_pct,
        }
        failures = [
            name
            for name, actual, maximum in (
                ("risk_per_trade", metrics["risk_pct_equity"], limits["max_risk_pct"]),
                ("order_notional", metrics["notional_pct_equity"], limits["max_notional_pct"]),
                (
                    "symbol_concentration",
                    metrics["post_symbol_pct_equity"],
                    limits["max_symbol_pct"],
                ),
                (
                    "sector_concentration",
                    metrics["post_sector_pct_equity"],
                    limits["max_sector_pct"],
                ),
                ("non_cad_exposure", metrics["post_non_cad_pct_equity"], limits["max_non_cad_pct"]),
                ("gross_exposure", metrics["post_gross_pct_equity"], limits["max_gross_pct"]),
            )
            if actual > maximum
        ]
        if failures:
            raise CanadaMoneyGateError("money gate limits failed: " + ", ".join(failures))
        if required_buying_power > snapshot.buying_power_cad:
            raise CanadaMoneyGateError("TD buying power is insufficient")
        if get_kill_switch().check().is_active:
            raise CanadaMoneyGateError("global kill switch is active")

        snapshot_record = snapshot.model_dump(mode="json")
        snapshot_hash = _canonical_hash(snapshot_record)
        account_scope = hashlib.sha256(
            f"{snapshot.operator}|{snapshot.account_alias}|{snapshot.account_type}".encode()
        ).hexdigest()
        evidence = {
            "passed": True,
            "trust": "OPERATOR_ATTESTED_TD_SNAPSHOT_SERVER_CALCULATED",
            "snapshot_hash": snapshot_hash,
            "snapshot_age_seconds": round(max(0.0, age_seconds), 3),
            "snapshot": snapshot_record,
            "fx_evidence": normalized_fx,
            "metrics": metrics,
            "limits": limits,
            "account_scope": account_scope,
            "evaluated_at": current.isoformat(),
        }
        evidence["evidence_hash"] = _canonical_hash(evidence)
        try:
            self.store.reserve_money_gate(
                str(ticket["ticket_id"]),
                account_scope=account_scope,
                snapshot_hash=snapshot_hash,
                amount_cad=required_buying_power,
                buying_power_cad=snapshot.buying_power_cad,
                symbol=symbol,
                sector=sector,
                gross_addition_cad=notional_cad if side == "BUY" else 0.0,
                non_cad_addition_cad=(
                    notional_cad if side == "BUY" and ticket_currency != "CAD" else 0.0
                ),
                base_gross_cad=current_gross,
                base_symbol_cad=current_symbol_value,
                base_sector_cad=current_sector,
                base_non_cad_cad=current_non_cad,
                equity_cad=equity,
                max_gross_pct=limits["max_gross_pct"],
                max_symbol_pct=limits["max_symbol_pct"],
                max_sector_pct=limits["max_sector_pct"],
                max_non_cad_pct=limits["max_non_cad_pct"],
            )
        except WorkflowConflictError as exc:
            raise CanadaMoneyGateError(str(exc)) from exc
        return evidence
