"""Publicacao no MIKE pelo canal de notificacao que ja existe.

Rota: POST {MIKE}/v1/notifications/send  (autonomy.py:829)
      corpo {"message": <titulo>, "level": <corpo>}
O bridge e so mais um cliente desse canal — nenhum protocolo novo.

O MIKE pode estar fora do ar: nada aqui levanta excecao para o chamador,
a fila e limitada, a tentativa tem backoff e o descarte e contado.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

import httpx

from bridge.envelope import bound_payload, canonical, utc_now

log = logging.getLogger(__name__)

QUEUE_MAXSIZE = 32  # espelha a fila do MIKE (autonomy.py:801)
BASE_BACKOFF_S = 1.0
MAX_BACKOFF_S = 60.0
MAX_ATTEMPTS = 5  # depois disso o evento e descartado e contado


class MikePublisher:
    """Consome o EventLog e empurra para o MIKE com retry/backoff."""

    def __init__(
        self,
        base_url: str,
        send_path: str = "/v1/notifications/send",
        timeout_s: float = 5.0,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.send_path = send_path
        self.timeout_s = timeout_s
        self._client = client
        self._owns_client = client is None
        self._queue: asyncio.Queue = asyncio.Queue(maxsize=QUEUE_MAXSIZE)
        self._task: asyncio.Task | None = None
        self._running = False
        self._backoff = BASE_BACKOFF_S
        self.reachable: bool | None = None
        self.last_ok_ts: str | None = None
        self.last_error: str | None = None
        self.consecutive_failures = 0
        self.sent = 0
        self.dropped_full = 0
        self.dropped_failed = 0

    # ------------------------------------------------------------------ ciclo

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._worker(), name="bridge-mike-publisher")

    async def stop(self) -> None:
        self._running = False
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        if self._owns_client and self._client is not None:
            await self._client.aclose()
            self._client = None

    async def _ensure_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                timeout=httpx.Timeout(self.timeout_s),
                headers={"content-type": "application/json"},
            )
        return self._client

    # --------------------------------------------------------------- publicar

    def publish(self, event: dict[str, Any]) -> bool:
        """Enfileira um evento. Nunca bloqueia e nunca levanta. False = descartado."""
        try:
            self._queue.put_nowait(event)
            return True
        except asyncio.QueueFull:
            self.dropped_full += 1
            log.warning("fila do MIKE cheia: evento %s descartado", event.get("event_type"))
            return False

    def to_mike_body(self, event: dict[str, Any]) -> dict[str, str]:
        """Envelope inteiro vai no corpo da notificacao; o titulo e legivel para humano."""
        event_type = str(event.get("event_type", "evento"))
        summary = f"ezio: {event_type}"
        payload = bound_payload(event.get("payload"))
        body = canonical({"event": event_type, "seq": event.get("seq"), "payload": payload})
        return {"message": summary[:120], "level": body[:2000]}

    async def _worker(self) -> None:
        while self._running:
            # cancelamento se propaga sozinho: nao ha o que tratar aqui
            event = await self._queue.get()
            attempts = 0
            while self._running and attempts < MAX_ATTEMPTS:
                attempts += 1
                if await self._send(event):
                    self._backoff = BASE_BACKOFF_S
                    break
                await asyncio.sleep(min(self._backoff, MAX_BACKOFF_S))
                self._backoff = min(self._backoff * 2, MAX_BACKOFF_S)
            else:
                if self._running:
                    self.dropped_failed += 1
                    log.warning("MIKE inalcancavel: evento %s descartado", event.get("event_type"))

    async def _send(self, event: dict[str, Any]) -> bool:
        try:
            client = await self._ensure_client()
            response = await client.post(self.send_path, json=self.to_mike_body(event))
        except (httpx.HTTPError, OSError) as exc:
            self.reachable = False
            self.consecutive_failures += 1
            self.last_error = f"{type(exc).__name__}: {exc}"
            return False
        if response.status_code >= 400:
            self.reachable = False
            self.consecutive_failures += 1
            self.last_error = f"MIKE HTTP {response.status_code}"
            return False
        self.reachable = True
        self.consecutive_failures = 0
        self.last_error = None
        self.last_ok_ts = utc_now()
        self.sent += 1
        return True

    # ------------------------------------------------------------------ estado

    def stats(self) -> dict[str, Any]:
        return {
            "base_url": self.base_url,
            "send_path": self.send_path,
            "reachable": self.reachable,
            "last_ok_ts": self.last_ok_ts,
            "last_error": self.last_error,
            "consecutive_failures": self.consecutive_failures,
            "pending": self._queue.qsize(),
            "queue_maxsize": QUEUE_MAXSIZE,
            "sent": self.sent,
            "dropped_full": self.dropped_full,
            "dropped_failed": self.dropped_failed,
        }


def describe(event: dict[str, Any]) -> str:
    """Linha curta para log local (sem payload)."""
    return json.dumps(
        {"t": event.get("event_type"), "seq": event.get("seq"), "snap": event.get("snapshot_id")},
        ensure_ascii=False,
    )
