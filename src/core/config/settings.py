"""Pydantic Settings — single source of truth for ALL environment variables.

Replaces scattered os.getenv() calls with typed, validated settings.
Typo in a security-critical env var will crash at boot, not silently disable protection.

Design contract:
- CRITICAL vars default to SAFE (FREEZE=true, paper_submit=false)
- extra="forbid" — unknown env vars raise ValidationError
- Secrets use SecretStr — never logged
"""

from __future__ import annotations

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",  # Stage 1: ignore unknown vars. Stage 2: add all 55+ to schema.
    )

    # ═══════════════════════════════════════════════════════════
    # SECURITY — CRITICAL
    # ═══════════════════════════════════════════════════════════

    f51_trading_execution_freeze: bool = Field(
        default=True,
        description="Global kill switch. TRUE = ALL orders BLOCKED. "
        "NEVER set to false in production without explicit approval.",
    )
    superezio_enable_paper_order_submit: bool = Field(
        default=False,
        description="Enable paper order submission to IBKR TWS. Requires explicit opt-in.",
    )
    superezio_bob_sovereign: bool = Field(
        default=False,
        description="Bob sovereign mode — allows unrestricted ticket references.",
    )

    # ═══════════════════════════════════════════════════════════
    # CONNECTIVITY — HIGH
    # ═══════════════════════════════════════════════════════════

    ibkr_host: str = Field(
        default="127.0.0.1",
        description="IBKR TWS/Gateway host address.",
    )
    ibkr_port: int = Field(
        default=7497,
        ge=1024,
        le=65535,
        description="IBKR TWS paper port (7497) or Gateway port (4002).",
    )

    # ═══════════════════════════════════════════════════════════
    # BEHAVIOR — MEDIUM
    # ═══════════════════════════════════════════════════════════

    universal_skip_gateway: bool = Field(
        default=False,
        description="Skip gateway checks in test/dev environments.",
    )
    log_level: str = Field(
        default="INFO",
        description="Python logging level.",
    )
    structlog_enabled: bool = Field(
        default=True,
        description="Enable structured JSON logging via structlog.",
    )
    trace_id_header: str = Field(
        default="x-trace-id",
        description="HTTP header name for trace ID propagation.",
    )

    # ═══════════════════════════════════════════════════════════
    # SECRETS — CRITICAL (never log these)
    # ═══════════════════════════════════════════════════════════

    ibkr_account_id: SecretStr | None = Field(
        default=None,
        description="IBKR account ID for live trading. Paper uses default.",
    )
    alpaca_api_key: SecretStr | None = Field(
        default=None,
        description="Alpaca API key. Optional.",
    )
    alpaca_secret_key: SecretStr | None = Field(
        default=None,
        description="Alpaca secret key. Optional.",
    )
    questrade_refresh_token: SecretStr | None = Field(
        default=None,
        description=(
            "Questrade OAuth refresh token for read-only account and market-data access. "
            "Never use a Questrade account password as an API credential."
        ),
    )
    questrade_practice: bool = Field(
        default=True,
        description="Use Questrade's practice OAuth login endpoint for read-only connectivity.",
    )

    # Canadian live-manual Money Gate — conservative defaults, all percentages of equity.
    superezio_money_gate_snapshot_max_age_sec: int = Field(default=120, ge=30, le=600)
    superezio_money_gate_min_equity_cad: float = Field(default=1000.0, gt=0)
    superezio_money_gate_max_risk_pct: float = Field(default=0.5, gt=0, le=2)
    superezio_money_gate_max_notional_pct: float = Field(default=10.0, gt=0, le=25)
    superezio_money_gate_max_symbol_pct: float = Field(default=10.0, gt=0, le=25)
    superezio_money_gate_max_sector_pct: float = Field(default=25.0, gt=0, le=50)
    superezio_money_gate_max_non_cad_pct: float = Field(default=30.0, gt=0, le=75)
    superezio_money_gate_max_gross_pct: float = Field(default=100.0, gt=0, le=150)
    superezio_money_gate_gap_multiplier: float = Field(default=2.0, ge=1, le=5)
    superezio_money_gate_slippage_bps: float = Field(default=25.0, ge=0, le=200)


# Singleton — validated at import time
_settings: Settings | None = None
_validation_error: Exception | None = None

try:
    _settings = Settings()
except Exception as exc:
    _validation_error = exc


def get_settings() -> Settings:
    """Return the validated Settings singleton.

    Raises ValidationError if env vars are misconfigured.
    Call this at boot time; if it raises, DO NOT START the system.
    """
    if _validation_error is not None:
        raise RuntimeError(
            "Settings validation failed at boot. Fix env vars and restart."
        ) from _validation_error
    assert _settings is not None
    return _settings


def is_frozen() -> bool:
    """Check if trading execution is frozen (global kill switch)."""
    try:
        return get_settings().f51_trading_execution_freeze
    except RuntimeError:
        # If settings are invalid, default to SAFE (frozen)
        return True


def is_paper_submit_enabled() -> bool:
    """Check if paper order submission is enabled."""
    try:
        return get_settings().superezio_enable_paper_order_submit
    except RuntimeError:
        return False
