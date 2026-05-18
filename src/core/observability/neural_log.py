"""
F51 OBSERVABILITY - OpenTelemetry Integration
==============================================
Sistema unificado de observabilidade com:
- NeuralLog (logs formatados para o frontend)
- OpenTelemetry (traces e métricas)
- Spans para rastrear o fluxo da Tríade
"""

import logging
import json
import os
from queue import Queue
from datetime import datetime
from typing import Dict, Any, Optional
from functools import wraps
import warnings

# Silencia deprecation ruidoso do OTEL (utcfromtimestamp)
warnings.filterwarnings(
    "ignore",
    category=DeprecationWarning,
    module=r"opentelemetry\..*",
)
warnings.filterwarnings(
    "ignore",
    category=DeprecationWarning,
    message=r".*utcfromtimestamp.*",
)

# OpenTelemetry imports
OTEL_AVAILABLE = False
if os.getenv("DISABLE_OTEL") != "1":
    try:
        from opentelemetry import trace
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import (
            ConsoleSpanExporter,
            SimpleSpanProcessor,
        )
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.trace import Status, StatusCode

        OTEL_AVAILABLE = True
    except ImportError:
        logging.getLogger(__name__).warning(
            "OpenTelemetry não instalado. Traces desabilitados."
        )

# ============================================
# NEURAL LOG (Original do F51)
# ============================================

# Queue for log events (para o frontend consumir via SSE)
log_queue = Queue()


class NeuralLogHandler(logging.Handler):
    """
    Handler customizado que captura logs e coloca na queue
    para streaming no frontend.
    """

    def emit(self, record):
        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "phase": getattr(record, "phase", "SYSTEM"),
            "event": getattr(record, "event", record.levelname),
            "data": getattr(record, "data", {}),
            "message": record.getMessage(),
        }
        formatted = f"NEURAL_LOG: {json.dumps(log_entry)}"
        log_queue.put(formatted)


# Setup neural logger
neural_handler = NeuralLogHandler()
neural_handler.setLevel(logging.DEBUG)

neural_logger = logging.getLogger("F51-NEURAL")
neural_logger.setLevel(logging.DEBUG)
neural_logger.addHandler(neural_handler)

# Also add console handler for development
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)
console_format = logging.Formatter("[%(levelname)s] %(message)s")
console_handler.setFormatter(console_format)
neural_logger.addHandler(console_handler)


def log_event(phase: str, event: str, data: Optional[Dict[str, Any]] = None) -> None:
    """
    Log a neural event to the queue and console.

    Args:
        phase: Category like 'SYSTEM', 'TRIADE_LOOP', 'AGENT_RUNTIME', etc.
        event: What happened like 'BOOT', 'TOOL_CALL', 'ERROR'
        data: Additional data dict
    """
    record = neural_logger.makeRecord(
        name="F51-NEURAL",
        level=logging.INFO,
        fn="",
        lno=0,
        msg=f"[{phase}] {event}",
        args=(),
        exc_info=None,
    )
    record.phase = phase
    record.event = event
    record.data = data or {}
    neural_logger.handle(record)


# ============================================
# OPENTELEMETRY TRACER
# ============================================

_tracer = None


def setup_telemetry(service_name: str = "f51-universal-agent") -> Optional[Any]:
    """
    Setup OpenTelemetry tracing.
    Returns the tracer instance.
    """
    global _tracer

    if not OTEL_AVAILABLE:
        return None

    # Create resource with service info
    resource = Resource.create(
        {
            "service.name": service_name,
            "service.version": "2.0.0",
            "deployment.environment": "local",
        }
    )

    # Create tracer provider
    provider = TracerProvider(resource=resource)

    # Add console exporter (for development visibility)
    console_processor = SimpleSpanProcessor(ConsoleSpanExporter())
    provider.add_span_processor(console_processor)

    # Set as global provider
    trace.set_tracer_provider(provider)

    _tracer = trace.get_tracer("f51.kernel")

    log_event("OBSERVABILITY", "OTEL_READY", {"service": service_name})

    return _tracer


def get_tracer() -> Any:
    """Get the global tracer instance."""
    global _tracer
    if _tracer is None and OTEL_AVAILABLE:
        _tracer = setup_telemetry()
    return _tracer


# ============================================
# SPAN DECORATORS & HELPERS
# ============================================


def trace_span(name: str, attributes: Optional[Dict[str, Any]] = None):
    """
    Decorator to trace a function with OpenTelemetry span.
    Also logs to Neural Log.

    Usage:
        @trace_span("triade.orchestrator.plan")
        def create_plan(task: str):
            ...
    """

    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            tracer = get_tracer()

            # Log start
            log_event("TRACE", f"START:{name}", attributes or {})

            if tracer:
                with tracer.start_as_current_span(name) as span:
                    if attributes:
                        for k, v in attributes.items():
                            span.set_attribute(k, str(v))

                    try:
                        result = func(*args, **kwargs)
                        span.set_status(Status(StatusCode.OK))
                        log_event("TRACE", f"END:{name}", {"status": "OK"})
                        return result
                    except Exception as e:
                        span.set_status(Status(StatusCode.ERROR, str(e)))
                        span.record_exception(e)
                        log_event("TRACE", f"ERROR:{name}", {"error": str(e)})
                        raise
            else:
                # No tracer, just execute
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    log_event("TRACE", f"ERROR:{name}", {"error": str(e)})
                    raise

        return wrapper

    return decorator


def trace_span_async(name: str, attributes: Optional[Dict[str, Any]] = None):
    """
    Async version of trace_span decorator.
    """

    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            tracer = get_tracer()

            log_event("TRACE", f"START:{name}", attributes or {})

            if tracer:
                with tracer.start_as_current_span(name) as span:
                    if attributes:
                        for k, v in attributes.items():
                            span.set_attribute(k, str(v))

                    try:
                        result = await func(*args, **kwargs)
                        span.set_status(Status(StatusCode.OK))
                        log_event("TRACE", f"END:{name}", {"status": "OK"})
                        return result
                    except Exception as e:
                        span.set_status(Status(StatusCode.ERROR, str(e)))
                        span.record_exception(e)
                        log_event("TRACE", f"ERROR:{name}", {"error": str(e)})
                        raise
            else:
                try:
                    return await func(*args, **kwargs)
                except Exception as e:
                    log_event("TRACE", f"ERROR:{name}", {"error": str(e)})
                    raise

        return wrapper

    return decorator


class SpanContext:
    """
    Context manager for manual span creation.

    Usage:
        with SpanContext("triade.worker.execute") as span:
            span.set_attribute("tool", "read_file")
            result = do_work()
    """

    def __init__(self, name: str, attributes: Optional[Dict[str, Any]] = None):
        self.name = name
        self.attributes = attributes or {}
        self.span = None
        self.tracer = get_tracer()

    def __enter__(self):
        log_event("SPAN", f"ENTER:{self.name}", self.attributes)

        if self.tracer:
            self.span = self.tracer.start_span(self.name)
            for k, v in self.attributes.items():
                self.span.set_attribute(k, str(v))
            return self.span
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.span:
            if exc_type:
                self.span.set_status(Status(StatusCode.ERROR, str(exc_val)))
                self.span.record_exception(exc_val)
            else:
                self.span.set_status(Status(StatusCode.OK))
            self.span.end()

        log_event(
            "SPAN", f"EXIT:{self.name}", {"error": str(exc_val) if exc_val else None}
        )
        return False

    def set_attribute(self, key: str, value: Any):
        """Set span attribute."""
        if self.span:
            self.span.set_attribute(key, str(value))


# ============================================
# METRICS (Simple counters for now)
# ============================================


class SimpleMetrics:
    """In-memory metrics collector com percentis, latência e erro rate."""

    def __init__(self):
        self._counters: Dict[str, int] = {}
        self._histograms: Dict[str, list] = {}
        self._start_time: float = __import__("time").time()

    def increment(self, name: str, value: int = 1):
        self._counters[name] = self._counters.get(name, 0) + value

    def observe(self, name: str, value: float):
        if name not in self._histograms:
            self._histograms[name] = []
        self._histograms[name].append(value)

    def latency(self, name: str, seconds: float):
        """Registra latência em segundos."""
        self.increment(f"{name}_count")
        self.observe(f"{name}_latency_s", seconds)

    def error(self, name: str):
        """Registra erro. Taxa = errors / total."""
        self.increment(f"{name}_errors")

    def token_usage(self, provider: str, tokens: int):
        """Registra tokens consumidos por provider."""
        self.increment(f"{provider}_tokens_total", tokens)

    def get_counter(self, name: str) -> int:
        return self._counters.get(name, 0)

    def get_histogram_avg(self, name: str) -> float:
        values = self._histograms.get(name, [])
        return sum(values) / len(values) if values else 0.0

    def get_percentile(self, name: str, pct: float) -> float:
        """Retorna percentil pct (ex: 0.95 = p95) do histograma."""
        values = sorted(self._histograms.get(name, []))
        if not values:
            return 0.0
        idx = int(len(values) * pct)
        return values[min(idx, len(values) - 1)]

    def error_rate(self, name: str) -> float:
        total = self.get_counter(f"{name}_count")
        errors = self.get_counter(f"{name}_errors")
        return errors / total if total > 0 else 0.0

    def uptime_seconds(self) -> float:
        return __import__("time").time() - self._start_time

    def get_all(self) -> Dict[str, Any]:
        histograms = {}
        for k, v in self._histograms.items():
            sv = sorted(v)
            n = len(sv)
            histograms[k] = {
                "count": n,
                "avg": sum(sv) / n if n else 0,
                "p50": self.get_percentile(k, 0.50),
                "p95": self.get_percentile(k, 0.95),
                "p99": self.get_percentile(k, 0.99),
            }
        return {
            "uptime_seconds": self.uptime_seconds(),
            "counters": self._counters.copy(),
            "histograms": histograms,
        }


# Global metrics instance
metrics = SimpleMetrics()
