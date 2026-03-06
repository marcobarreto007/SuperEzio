"""Observability package."""

from .neural_log import (
    log_event,
    log_queue,
    get_tracer,
    metrics,
    SimpleMetrics,
    setup_telemetry,
    trace_span,
    trace_span_async,
    SpanContext,
)
from .debug_logger import debug_logger, DebugLogger
from .event_hub import (
    EventEnvelope,
    EventHub,
    InMemoryHub,
    RedisStreamsHub,
    create_event_hub,
    get_event_hub,
    set_event_hub,
)

__all__ = [
    "log_event",
    "log_queue",
    "setup_telemetry",
    "get_tracer",
    "trace_span",
    "trace_span_async",
    "SpanContext",
    "metrics",
    "SimpleMetrics",
    "debug_logger",
    "DebugLogger",
    "EventHub",
    "InMemoryHub",
    "RedisStreamsHub",
    "EventEnvelope",
    "create_event_hub",
    "get_event_hub",
    "set_event_hub",
]
