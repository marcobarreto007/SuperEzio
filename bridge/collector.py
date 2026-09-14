"""Coleta no Ezio por polling + diff.

A FORMA dos corpos das rotas NAO foi verificada. Regra: nada aqui levanta por
causa de corpo inesperado — se nao parsear, sai evento de degradacao e o bridge
segue vivo.

Vocabulario de eventos: o de `bridge/events.toml` ([events]). Nada de nome novo.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from bridge.config import DEFAULT_VOCABULARY, PollRoute
from bridge.envelope import EventLog, payload_hash, short_hash, utc_now

log = logging.getLogger(__name__)

MAX_NEW_ITEMS = 20  # itens novos por evento; o resto vira contagem
LIST_KEYS = ("items", "data", "results", "trades", "alerts", "history", "rows", "entries")
BOOT_ID_KEYS = ("boot_id", "bootId", "instance_id", "instanceId")
START_KEYS = ("started_at", "start_time", "startTime", "startedAt")
BAD_HEALTH_VALUES = frozenset({"error", "degraded", "unhealthy", "down", "failed", "false", "0"})
HEALTH_ROUTE = "/health"


def _find_list(body: Any) -> list | None:
    if isinstance(body, list):
        return body
    if isinstance(body, dict):
        for key in LIST_KEYS:
            value = body.get(key)
            if isinstance(value, list):
                return value
    return None


def _boot_identity(body: Any) -> str | None:
    """Identidade de boot do Ezio, se o corpo oferecer alguma. Sem forma conhecida, None."""
    candidates: list[dict] = []
    if isinstance(body, dict):
        candidates.append(body)
        for key in ("data", "health", "details", "status", "uptime"):
            nested = body.get(key)
            if isinstance(nested, dict):
                candidates.append(nested)
    for mapping in candidates:
        for key in BOOT_ID_KEYS:
            value = mapping.get(key)
            if isinstance(value, (str, int)) and str(value):
                return f"boot_id:{value}"
        started = next((mapping[k] for k in START_KEYS if k in mapping), None)
        if started is not None and str(started):
            return f"start:{started}|pid:{mapping.get('pid', '?')}"
    return None


def _health_ok(body: Any) -> bool:
    """Leitura TOLERANTE de /health: so reprova em sinal explicito de doenca.

    A forma do corpo nao foi verificada. Preferimos nao gritar falso positivo a
    inventar um contrato de saude.
    """
    if body is None:
        return False
    if isinstance(body, str):
        return body.strip().lower() not in BAD_HEALTH_VALUES
    if isinstance(body, dict):
        for key in ("status", "state", "health", "result"):
            value = body.get(key)
            if isinstance(value, str) and value.strip().lower() in BAD_HEALTH_VALUES:
                return False
            if value is False:
                return False
        if body.get("ok") is False:
            return False
    return True


class EzioCollector:
    """Um ciclo = GET em cada rota, hash do corpo, diff contra o snapshot anterior."""

    def __init__(
        self,
        base_url: str,
        routes: list[PollRoute],
        events: EventLog,
        timeout_s: float = 5.0,
        vocabulary: dict[str, str] | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.routes = routes
        self.events = events
        self.timeout_s = timeout_s
        self.vocabulary = dict(vocabulary or DEFAULT_VOCABULARY)
        self._client = client
        self._owns_client = client is None
        self.hashes: dict[str, str] = {}
        self.bodies: dict[str, Any] = {}
        self.failures: dict[str, int] = {}
        self.last_poll_ts: str | None = None
        self.last_poll_ok = False
        self.last_snapshot_id = "000000000000"
        self.boot_identity: str | None = None
        self.health_ok: bool | None = None
        self.poll_count = 0
        self.degraded = False
        self.restarts_detected = 0
        self._booted = False

    @property
    def ezio_up(self) -> bool:
        """Baseado na ultima coleta observada — nao faz chamada nova."""
        return self.last_poll_ok

    def _event(self, key: str) -> str:
        return self.vocabulary.get(key, DEFAULT_VOCABULARY[key])

    async def _ensure_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self.base_url, timeout=httpx.Timeout(self.timeout_s)
            )
        return self._client

    async def aclose(self) -> None:
        if self._owns_client and self._client is not None:
            await self._client.aclose()
            self._client = None

    # ------------------------------------------------------------------ ciclo

    async def poll_once(self) -> dict[str, Any]:
        """Um ciclo completo. Nunca levanta: falha de rota vira evento de degradacao."""
        self.poll_count += 1
        self.last_poll_ts = utc_now()
        results: dict[str, Any] = {}
        cycle: dict[str, str] = {}
        pending: list[tuple[str, Any, str]] = []
        any_ok = False
        health_body: Any = None

        for route in self.routes:
            status, body, error = await self._fetch(route)
            if error is not None:
                self.failures[route.path] = self.failures.get(route.path, 0) + 1
                cycle[route.path] = f"error:{error}"
                results[route.path] = {
                    "status": status,
                    "ok": False,
                    "error": error,
                    "consecutive_failures": self.failures[route.path],
                }
                if self.failures[route.path] == 1:  # so na borda: nao repete a cada 30s
                    pending.append(
                        (
                            self._event("degraded"),
                            self._degraded_payload(route, status, error),
                            "bridge",
                        )
                    )
                continue

            any_ok = True
            if route.path == HEALTH_ROUTE:
                health_body = body
            digest = payload_hash(body)
            cycle[route.path] = digest
            results[route.path] = {"status": status, "hash": short_hash(digest), "ok": True}
            pending.extend(self._diff(route, body, digest))

        if health_body is not None:
            pending.extend(self._health_edges(health_body))

        snapshot_id = short_hash(payload_hash(cycle))
        self.last_snapshot_id = snapshot_id
        if any_ok and not self._booted:
            self._booted = True
            pending.insert(
                0,
                (
                    self._event("boot"),
                    {"routes": sorted(cycle), "snapshot_id": snapshot_id},
                    "bridge",
                ),
            )
        for event_type, payload, source in pending:
            if not event_type:
                continue
            await self.events.emit(event_type, payload, snapshot_id=snapshot_id, source=source)

        self.last_poll_ok = any_ok
        self.degraded = not any_ok
        return {"snapshot_id": snapshot_id, "poll_count": self.poll_count, "routes": results}

    async def _fetch(self, route: PollRoute) -> tuple[int | None, Any, str | None]:
        try:
            client = await self._ensure_client()
            response = await client.get(route.path, params=route.params or None)
        except (httpx.HTTPError, OSError) as exc:
            return None, None, f"{type(exc).__name__}: {exc}"
        if response.status_code != 200:
            return response.status_code, None, f"HTTP {response.status_code}"
        try:
            return response.status_code, response.json(), None
        except ValueError:
            return response.status_code, None, "corpo nao e JSON"

    # ------------------------------------------------------------------- diff

    def _diff(self, route: PollRoute, body: Any, digest: str) -> list[tuple[str, Any, str]]:
        """Eventos desta rota. Re-baseia o snapshot inteiro se detectar restart."""
        events: list[tuple[str, Any, str]] = []
        previous_digest = self.hashes.get(route.path)
        previous_body = self.bodies.get(route.path)
        first_seen = route.path not in self.bodies
        recovered = self.failures.get(route.path, 0) > 0

        self.hashes[route.path] = digest
        self.bodies[route.path] = body
        self.failures[route.path] = 0

        if recovered:
            events.append((self._event("recovered"), {"route": route.path}, "bridge"))
        if not first_seen and previous_digest is not None and previous_digest != digest:
            change = self._change_payload(route, body, previous_body, previous_digest, digest)
            if route.event_type:
                events.append((route.event_type, change, "ezio"))
            else:
                log.debug("rota %s mudou sem evento proprio (ciclo de vida)", route.path)

        if route.path == HEALTH_ROUTE:
            identity = _boot_identity(body)
            if identity and self.boot_identity is None:
                self.boot_identity = identity
            elif identity and identity != self.boot_identity:
                self.boot_identity = identity
                self.restarts_detected += 1
                self.hashes.clear()
                self.bodies.clear()
                events.append(
                    (
                        self._event("restarted"),
                        {"identity": identity, "route": route.path},
                        "ezio",
                    )
                )
        return events

    def _health_edges(self, body: Any) -> list[tuple[str, Any, str]]:
        """ezio.degraded / ezio.recovered na borda do /health."""
        current = _health_ok(body)
        previous = self.health_ok
        self.health_ok = current
        if previous is None or previous == current:
            return []
        payload = {"route": HEALTH_ROUTE, "health_ok": current, "snapshot": bound_health(body)}
        return [(self._event("recovered" if current else "degraded"), payload, "bridge")]

    def _change_payload(
        self,
        route: PollRoute,
        body: Any,
        previous_body: Any,
        previous_digest: str,
        digest: str,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "route": route.path,
            "before_hash": short_hash(previous_digest),
            "after_hash": short_hash(digest),
        }
        if route.mode == "list":
            current_items = _find_list(body)
            previous_items = _find_list(previous_body)
            if current_items is not None and previous_items is not None:
                seen = {payload_hash(item) for item in previous_items}
                added = [item for item in current_items if payload_hash(item) not in seen]
                payload["count_before"] = len(previous_items)
                payload["count_after"] = len(current_items)
                payload["new_count"] = len(added)
                if added:
                    payload["new_items"] = added[:MAX_NEW_ITEMS]
                    payload["new_items_truncated"] = len(added) > MAX_NEW_ITEMS
        if isinstance(body, dict):
            payload["keys"] = sorted(body)[:40]
        return payload

    def _degraded_payload(self, route: PollRoute, status: int | None, error: str) -> dict[str, Any]:
        return {
            "route": route.path,
            "status": status,
            "error": error,
            "consecutive_failures": self.failures.get(route.path, 1),
        }

    # ------------------------------------------------------------------ estado

    def stats(self) -> dict[str, Any]:
        return {
            "base_url": self.base_url,
            "ezio_up": self.ezio_up,
            "degraded": self.degraded,
            "health_ok": self.health_ok,
            "last_poll_ts": self.last_poll_ts,
            "poll_count": self.poll_count,
            "snapshot_id": self.last_snapshot_id,
            "boot_identity": self.boot_identity,
            "restarts_detected": self.restarts_detected,
            "routes": [
                {
                    "path": route.path,
                    "event_type": route.event_type,
                    "hash": short_hash(self.hashes[route.path])
                    if route.path in self.hashes
                    else None,
                    "consecutive_failures": self.failures.get(route.path, 0),
                }
                for route in self.routes
            ],
        }


def bound_health(body: Any) -> Any:
    """Resumo de saude para o payload, sem despejar o corpo inteiro."""
    if isinstance(body, dict):
        keep = ("status", "state", "ok", "auth_required", "boot_id", "version", "uptime")
        return {key: body[key] for key in keep if key in body} or {"keys": sorted(body)[:20]}
    return {"type": type(body).__name__}
