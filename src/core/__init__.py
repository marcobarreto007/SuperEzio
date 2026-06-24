"""SuperEzio core package."""

__version__ = "4.0.0"
__author__ = "Fabria Labs"

from .config import UniversalConfig, get_config, reload_config
from .model_serving import GatewayConfig, ModelGateway, ModelProvider
from .observability import (
    EventEnvelope,
    EventHub,
    InMemoryHub,
    SpanContext,
    create_event_hub,
    log_event,
    log_queue,
    metrics,
    setup_telemetry,
    trace_span,
    trace_span_async,
)

__all__ = [
    "__version__",
    "__author__",
    "get_config",
    "reload_config",
    "UniversalConfig",
    "ModelGateway",
    "ModelProvider",
    "GatewayConfig",
    "log_event",
    "log_queue",
    "setup_telemetry",
    "trace_span",
    "trace_span_async",
    "SpanContext",
    "metrics",
    "EventHub",
    "InMemoryHub",
    "create_event_hub",
    "EventEnvelope",
]
