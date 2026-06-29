"""Structured logging configuration for SuperEzio.

Configures structlog with:
- JSON format for production (machine-parseable)
- Colored console format for development
- Automatic trace_id binding from contextvars
- ISO 8601 timestamps in UTC

Usage:
    from core.config.logging_config import get_logger
    logger = get_logger(__name__)
    logger.info("order_evaluated", ticker="AAPL", gate="freeze", decision="BLOCK")
"""

from __future__ import annotations

import logging
import os
import sys
from typing import Any

import structlog

# Shared context for trace_id propagation across modules
from structlog.contextvars import (
    bind_contextvars,
    clear_contextvars,
    merge_contextvars,
)

# ═══════════════════════════════════════════════════════════════
# Processors chain
# ═══════════════════════════════════════════════════════════════

_shared_processors: list[Any] = [
    merge_contextvars,  # Inject trace_id, run_id from context
    structlog.stdlib.add_log_level,
    structlog.stdlib.add_logger_name,
    structlog.processors.TimeStamper(fmt="iso", utc=True),
    structlog.stdlib.PositionalArgumentsFormatter(),
    structlog.processors.StackInfoRenderer(),
    structlog.processors.format_exc_info,
    structlog.processors.UnicodeDecoder(),
]


def _is_structured() -> bool:
    """Check if structured JSON output is enabled."""
    return os.getenv("STRUCTLOG_ENABLED", "true").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def configure_logging() -> None:
    """Configure structlog globally. Call once at application startup."""

    if _is_structured():
        # Production: JSON to stdout
        structlog.configure(
            processors=_shared_processors
            + [
                structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
            ],
            logger_factory=structlog.stdlib.LoggerFactory(),
            wrapper_class=structlog.stdlib.BoundLogger,
            cache_logger_on_first_use=True,
        )

        # Console handler with JSON formatter
        formatter = structlog.stdlib.ProcessorFormatter(
            processor=structlog.processors.JSONRenderer(ensure_ascii=False),
            foreign_pre_chain=_shared_processors,
        )
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(formatter)

        root_logger = logging.getLogger()
        root_logger.handlers.clear()
        root_logger.addHandler(handler)
        root_logger.setLevel(logging.INFO)
    else:
        # Development: colored console
        structlog.configure(
            processors=_shared_processors
            + [
                structlog.dev.ConsoleRenderer(colors=True),
            ],
            logger_factory=structlog.stdlib.LoggerFactory(),
            wrapper_class=structlog.stdlib.BoundLogger,
            cache_logger_on_first_use=True,
        )


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    """Get a structured logger for the given module name.

    Usage:
        logger = get_logger(__name__)
        logger.info("event_name", key="value", ticker="AAPL")
    """
    return structlog.get_logger(name)


def bind_trace(run_id: str = "", trace_id: str = "") -> None:
    """Bind trace context for the current execution.

    Call this at the start of every pipeline run.
    All subsequent logs will include these values automatically.
    """
    bind_contextvars(
        run_id=run_id or "unknown",
        trace_id=trace_id or run_id or "unknown",
    )


def unbind_trace() -> None:
    """Clear trace context. Call at the end of every pipeline run."""
    clear_contextvars()
