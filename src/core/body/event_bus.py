"""
F51 BODY EVENT BUS — Sistema de Eventos do Corpo
=================================================
Wrapper sobre core.observability.event_hub com namespaces padronizados.

12 namespaces de evento:
  event:pipeline.math.completed
  event:pipeline.f51.verdict
  event:pipeline.pennylab.whale
  event:pipeline.mangala.found
  event:pipeline.guardrail.blocked
  event:body.pain.{organ}
  event:body.dna.mutated
  event:body.memory.crystallized
  event:body.heartbeat.full
  event:body.heartbeat.light
  event:body.heartbeat.deep
  event:body.pain.heartbeat
"""

import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

from core.observability.event_hub import (
    EventEnvelope,
    EventHub,
    InMemoryHub,
    RedisStreamsHub,
    set_event_hub,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

EVENT_NAMESPACES: list[str] = [
    "event:pipeline.math.completed",
    "event:pipeline.f51.verdict",
    "event:pipeline.pennylab.whale",
    "event:pipeline.mangala.found",
    "event:pipeline.guardrail.blocked",
    "event:body.pain.{organ}",
    "event:body.dna.mutated",
    "event:body.memory.crystallized",
    "event:body.heartbeat.full",
    "event:body.heartbeat.light",
    "event:body.heartbeat.deep",
    "event:body.pain.heartbeat",
]

# ---------------------------------------------------------------------------
# Severity levels
# ---------------------------------------------------------------------------


class EventSeverity(str, Enum):
    DEBUG = "debug"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


# ---------------------------------------------------------------------------
# BodyEvent (Pydantic model)
# ---------------------------------------------------------------------------


class BodyEvent(BaseModel):
    """Evento padronizado do corpo F51."""

    event_type: str = Field(..., description="Namespace do evento (ex: event:body.pain.liver)")
    source: str = Field(default="f51-body", description="Componente de origem")
    timestamp: str = Field(
        default_factory=lambda: datetime.now(UTC).isoformat(),
        description="ISO 8601 timestamp",
    )
    correlation_id: str = Field(
        default_factory=lambda: str(uuid.uuid4()),
        description="ID de correlação para rastreamento",
    )
    payload: dict[str, Any] = Field(default_factory=dict, description="Dados do evento")
    severity: EventSeverity = Field(default=EventSeverity.INFO, description="Severidade")

    def to_envelope(self) -> EventEnvelope:
        """Converte para EventEnvelope do event_hub subjacente."""
        return EventEnvelope(
            event_type=self.event_type,
            payload={
                "body_event": self.model_dump(),
            },
            correlation_id=self.correlation_id,
            timestamp=self.timestamp,
            source=self.source,
        )

    @classmethod
    def from_envelope(cls, envelope: EventEnvelope) -> "BodyEvent":
        """Reconstrói BodyEvent a partir de um EventEnvelope."""
        raw = envelope.payload.get("body_event", {})
        return cls(
            event_type=raw.get("event_type", envelope.event_type),
            source=raw.get("source", envelope.source),
            timestamp=raw.get("timestamp", envelope.timestamp),
            correlation_id=raw.get("correlation_id", envelope.correlation_id),
            payload=raw.get("payload", envelope.payload),
            severity=raw.get("severity", EventSeverity.INFO),
        )


# ---------------------------------------------------------------------------
# Callback type
# ---------------------------------------------------------------------------

BodyEventHandler = Callable[[BodyEvent], Awaitable[None]]


# ---------------------------------------------------------------------------
# BodyEventBus
# ---------------------------------------------------------------------------


class BodyEventBus:
    """
    Barramento de eventos do corpo F51.

    Wrapper sobre o EventHub global (core.observability.event_hub)
    que adiciona tipagem, namespaces padronizados e método health_check.
    """

    def __init__(self, hub_type: str = "memory", hub: EventHub | None = None):
        self._hub_type = hub_type
        self._active_topics: dict[str, list[BodyEventHandler]] = {}

        if hub is not None:
            self._hub = hub
        elif hub_type == "redis":
            self._hub = RedisStreamsHub(
                redis_url="redis://localhost:6379",
                stream_key="f51_body_events",
            )
        else:
            self._hub = InMemoryHub()

        # Register self as the global hub so other components can publish
        set_event_hub(self._hub)

    # ------------------------------------------------------------------
    # Publish
    # ------------------------------------------------------------------

    async def publish(
        self,
        event_type: str,
        payload: dict[str, Any] | None = None,
        source: str = "f51-body",
        correlation_id: str | None = None,
        severity: EventSeverity = EventSeverity.INFO,
    ) -> None:
        """Publica um BodyEvent no barramento."""
        event = BodyEvent(
            event_type=event_type,
            source=source,
            payload=payload or {},
            correlation_id=correlation_id or str(uuid.uuid4()),
            severity=severity,
        )
        envelope = event.to_envelope()
        await self._hub.publish(envelope)

    # ------------------------------------------------------------------
    # Subscribe
    # ------------------------------------------------------------------

    async def subscribe(self, event_type: str, callback: BodyEventHandler) -> None:
        """Registra um callback para um tipo específico de evento."""

        # Wrap the BodyEventHandler to adapt from EventEnvelope
        async def _wrapper(envelope: EventEnvelope) -> None:
            body_event = BodyEvent.from_envelope(envelope)
            await callback(body_event)

        await self._hub.subscribe_to(event_type, _wrapper)

        # Track active subscriptions
        if event_type not in self._active_topics:
            self._active_topics[event_type] = []
        self._active_topics[event_type].append(callback)

    # ------------------------------------------------------------------
    # Topic listing
    # ------------------------------------------------------------------

    def list_topics(self) -> list[str]:
        """Retorna lista de tópicos (event_types) com subscrições ativas."""
        return list(self._active_topics.keys())

    # ------------------------------------------------------------------
    # Health check
    # ------------------------------------------------------------------

    async def health_check(self) -> dict[str, Any]:
        """
        Verifica conectividade do barramento.

        Returns:
            dict com status, hub_type, active_topics_count
        """
        try:
            # Try publishing a health-check event
            await self.publish(
                event_type="event:body.health.check",
                payload={"check": True},
                severity=EventSeverity.DEBUG,
            )
            return {
                "status": "ok",
                "hub_type": self._hub_type,
                "active_topics_count": len(self._active_topics),
                "active_topics": self.list_topics(),
            }
        except Exception as e:  # noqa: BLE001 — health_check deve reportar qualquer falha do hub (ex: redis fora) como status error, nunca estourar excecao
            return {
                "status": "error",
                "hub_type": self._hub_type,
                "error": str(e),
            }

    # ------------------------------------------------------------------
    # Access to underlying hub
    # ------------------------------------------------------------------

    @property
    def hub(self) -> EventHub:
        """Acesso ao EventHub subjacente (para uso avançado)."""
        return self._hub
