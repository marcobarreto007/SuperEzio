"""
F51 EVENT HUB - Sistema de Eventos Unificado
=============================================
Sistema de eventos pub/sub com suporte a:
- In-Memory (sempre disponível)
- Redis Streams (para produção/escalabilidade)

Permite comunicação assíncrona entre componentes do F51.
"""

import asyncio
import json
import threading as _threading
from abc import ABC, abstractmethod
from typing import Callable, Awaitable, Dict, Any, List, Optional
from dataclasses import dataclass, field
from datetime import datetime

from .neural_log import log_event

# Type for event handlers
EventHandler = Callable[["EventEnvelope"], Awaitable[None]]


@dataclass
class EventEnvelope:
    """
    Envelope para eventos do sistema.
    """

    event_type: str
    payload: Dict[str, Any]
    correlation_id: str = ""
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    source: str = "f51-kernel"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "event_type": self.event_type,
            "payload": self.payload,
            "correlation_id": self.correlation_id,
            "timestamp": self.timestamp,
            "source": self.source,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict())

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "EventEnvelope":
        return cls(
            event_type=data.get("event_type", "unknown"),
            payload=data.get("payload", {}),
            correlation_id=data.get("correlation_id", ""),
            timestamp=data.get("timestamp", datetime.now().isoformat()),
            source=data.get("source", "unknown"),
        )


class EventHub(ABC):
    """
    Interface abstrata para o sistema de eventos.
    """

    @abstractmethod
    async def publish(self, event: EventEnvelope) -> None:
        """Publica um evento."""
        pass

    @abstractmethod
    async def subscribe(self, handler: EventHandler) -> None:
        """Registra um handler para receber eventos."""
        pass

    @abstractmethod
    async def subscribe_to(self, event_type: str, handler: EventHandler) -> None:
        """Registra handler para tipo específico de evento."""
        pass


class InMemoryHub(EventHub):
    """
    Implementação in-memory do EventHub.
    Não requer Redis - funciona sempre.
    """

    def __init__(self):
        self._handlers: List[EventHandler] = []
        self._type_handlers: Dict[str, List[EventHandler]] = {}
        self._event_queue: Optional[asyncio.Queue] = None
        self._running = False
        self._task = None
        log_event("EVENT_HUB", "INIT", {"type": "in-memory"})

    async def _ensure_queue(self):
        if self._event_queue is None:
            self._event_queue = asyncio.Queue()

    async def publish(self, event: EventEnvelope) -> None:
        await self._ensure_queue()
        assert self._event_queue is not None
        await self._event_queue.put(event)

        # Process immediately for in-memory
        await self._process_event(event)

        log_event(
            "EVENT_HUB",
            "PUBLISHED",
            {"type": event.event_type, "correlation": event.correlation_id},
        )

    async def _process_event(self, event: EventEnvelope):
        # Call global handlers
        for handler in self._handlers:
            try:
                await handler(event)
            except Exception as e:
                log_event("EVENT_HUB", "HANDLER_ERROR", {"error": str(e)})

        # Call type-specific handlers
        if event.event_type in self._type_handlers:
            for handler in self._type_handlers[event.event_type]:
                try:
                    await handler(event)
                except Exception as e:
                    log_event("EVENT_HUB", "HANDLER_ERROR", {"error": str(e)})

    async def subscribe(self, handler: EventHandler) -> None:
        self._handlers.append(handler)
        log_event("EVENT_HUB", "SUBSCRIBED", {"handler": handler.__name__})

    async def subscribe_to(self, event_type: str, handler: EventHandler) -> None:
        if event_type not in self._type_handlers:
            self._type_handlers[event_type] = []
        self._type_handlers[event_type].append(handler)
        log_event("EVENT_HUB", "SUBSCRIBED_TO", {"type": event_type})


class RedisStreamsHub(EventHub):
    """
    Implementação com Redis Streams.
    Mais robusta para produção - permite múltiplos workers e persistência.
    """

    def __init__(
        self,
        redis_url: str,
        stream_key: str = "f51_events",
        consumer_group: str = "f51_consumers",
    ):
        self.redis_url = redis_url
        self.stream_key = stream_key
        self.consumer_group = consumer_group
        self._redis = None
        self._handlers: List[EventHandler] = []
        self._type_handlers: Dict[str, List[EventHandler]] = {}
        self._consumer_task = None
        self._running = False

        log_event("EVENT_HUB", "INIT", {"type": "redis", "stream": stream_key})

    async def _get_redis(self):
        if self._redis is None:
            try:
                import redis.asyncio as aioredis

                self._redis = await aioredis.from_url(self.redis_url)

                # Create consumer group if not exists
                try:
                    await self._redis.xgroup_create(
                        self.stream_key, self.consumer_group, id="0", mkstream=True
                    )
                except Exception:
                    pass  # Group already exists

                log_event("EVENT_HUB", "REDIS_CONNECTED", {"url": self.redis_url})
            except Exception as e:
                log_event("EVENT_HUB", "REDIS_FAILED", {"error": str(e)})
                raise
        return self._redis

    async def publish(self, event: EventEnvelope) -> None:
        redis = await self._get_redis()

        await redis.xadd(self.stream_key, {"data": event.to_json()})

        log_event(
            "EVENT_HUB",
            "PUBLISHED_REDIS",
            {"type": event.event_type, "stream": self.stream_key},
        )

    async def subscribe(self, handler: EventHandler) -> None:
        self._handlers.append(handler)

        # Start consumer if not running
        if not self._running:
            self._running = True
            self._consumer_task = asyncio.create_task(self._consume_loop())

    async def subscribe_to(self, event_type: str, handler: EventHandler) -> None:
        if event_type not in self._type_handlers:
            self._type_handlers[event_type] = []
        self._type_handlers[event_type].append(handler)

        if not self._running:
            self._running = True
            self._consumer_task = asyncio.create_task(self._consume_loop())

    async def _consume_loop(self):
        """Consumer loop that reads from Redis Stream."""
        redis = await self._get_redis()
        consumer_name = f"consumer_{id(self)}"

        while self._running:
            try:
                messages = await redis.xreadgroup(
                    groupname=self.consumer_group,
                    consumername=consumer_name,
                    streams={self.stream_key: ">"},
                    count=10,
                    block=1000,
                )

                for stream, msgs in messages:
                    for msg_id, fields in msgs:
                        try:
                            data = json.loads(fields[b"data"])
                            event = EventEnvelope.from_dict(data)

                            await self._process_event(event)

                            # Acknowledge message
                            await redis.xack(
                                self.stream_key, self.consumer_group, msg_id
                            )
                        except Exception as e:
                            log_event("EVENT_HUB", "CONSUME_ERROR", {"error": str(e)})

            except Exception as e:
                log_event("EVENT_HUB", "CONSUME_LOOP_ERROR", {"error": str(e)})
                await asyncio.sleep(1)

    async def _process_event(self, event: EventEnvelope):
        for handler in self._handlers:
            try:
                await handler(event)
            except Exception as e:
                log_event("EVENT_HUB", "HANDLER_ERROR", {"error": str(e)})

        if event.event_type in self._type_handlers:
            for handler in self._type_handlers[event.event_type]:
                try:
                    await handler(event)
                except Exception as e:
                    log_event("EVENT_HUB", "HANDLER_ERROR", {"error": str(e)})

    async def close(self) -> None:
        self._running = False
        if self._consumer_task:
            self._consumer_task.cancel()
        if self._redis:
            await self._redis.close()


# ============================================
# FACTORY
# ============================================


def create_event_hub(hub_type: str = "memory", **kwargs) -> EventHub:
    """
    Factory para criar o EventHub correto.

    Args:
        hub_type: "memory" ou "redis"
        **kwargs: Argumentos adicionais (redis_url, stream_key, etc.)
    """
    if hub_type == "redis":
        return RedisStreamsHub(
            redis_url=kwargs.get("redis_url", "redis://localhost:6379"),
            stream_key=kwargs.get("stream_key", "f51_events"),
            consumer_group=kwargs.get("consumer_group", "f51_consumers"),
        )
    else:
        return InMemoryHub()


# Global hub instance (created lazily, thread-safe)
_global_hub: Optional[EventHub] = None
_global_hub_lock: _threading.Lock = _threading.Lock()


def get_event_hub() -> EventHub:
    """Get the global event hub instance."""
    global _global_hub
    if _global_hub is None:
        with _global_hub_lock:
            if _global_hub is None:
                _global_hub = InMemoryHub()
    return _global_hub


def set_event_hub(hub: EventHub) -> None:
    """Set the global event hub instance."""
    global _global_hub
    _global_hub = hub
