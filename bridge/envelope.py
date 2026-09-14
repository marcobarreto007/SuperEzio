"""Envelope de evento e log em memoria (ring buffer + assinantes).

Envelope: event_type, seq, ts, source, payload, snapshot_id.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
from collections import deque
from datetime import UTC, datetime
from typing import Any

MAX_PAYLOAD_BYTES = 4096
MAX_RECENT_EVENTS = 500


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


def canonical(payload: Any) -> str:
    """JSON canonico: mesma entrada => mesmo texto => mesmo hash."""
    return json.dumps(
        payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"), default=str
    )


def payload_hash(payload: Any) -> str:
    return hashlib.sha256(canonical(payload).encode("utf-8")).hexdigest()


def short_hash(text: str, size: int = 12) -> str:
    return text[:size]


def bound_payload(payload: Any, limit: int = MAX_PAYLOAD_BYTES) -> Any:
    """Corta payload grande: a fila do MIKE tem 32 slots e vira notificacao de browser."""
    text = canonical(payload)
    if len(text.encode("utf-8")) <= limit:
        return payload
    keys = sorted(payload) if isinstance(payload, dict) else []
    return {
        "truncated": True,
        "bytes": len(text.encode("utf-8")),
        "keys": keys[:40],
    }


class EventLog:
    """Sequencia global de eventos do bridge, com buffer limitado para inspecao."""

    def __init__(self, source: str = "bridge", maxlen: int = MAX_RECENT_EVENTS) -> None:
        self._source = source
        self._seq = 0
        self._recent: deque[dict[str, Any]] = deque(maxlen=maxlen)
        self._subscribers: list[asyncio.Queue] = []
        self._lock = asyncio.Lock()

    @property
    def seq(self) -> int:
        return self._seq

    @property
    def source(self) -> str:
        return self._source

    def snapshot_id(self) -> str:
        if not self._recent:
            return "000000000000"
        return short_hash(
            payload_hash([item["event_type"] + str(item["seq"]) for item in self._recent])
        )

    async def emit(
        self,
        event_type: str,
        payload: Any = None,
        snapshot_id: str = "000000000000",
        source: str | None = None,
    ) -> dict[str, Any]:
        async with self._lock:
            self._seq += 1
            event = {
                "event_type": event_type,
                "seq": self._seq,
                "ts": utc_now(),
                "source": source or self._source,
                "payload": bound_payload(payload if payload is not None else {}),
                "snapshot_id": snapshot_id,
            }
            self._recent.append(event)
            for queue in list(self._subscribers):
                try:
                    queue.put_nowait(event)
                except asyncio.QueueFull:
                    pass
        return event

    def recent(self, limit: int = 50) -> list[dict[str, Any]]:
        if limit <= 0:
            return []
        return list(self._recent)[-limit:]

    def subscribe(self, maxsize: int = 64) -> asyncio.Queue:
        queue: asyncio.Queue = asyncio.Queue(maxsize=maxsize)
        self._subscribers.append(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue) -> None:
        try:
            self._subscribers.remove(queue)
        except ValueError:
            pass
