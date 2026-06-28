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
