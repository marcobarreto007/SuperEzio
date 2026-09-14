"""Comando: allowlist default-deny, idempotencia e estados.

Regras duras:
- fila de comando NAO persiste comando: se o Ezio caiu, 503 e nada guardado;
- comando em voo quando algo morre = estado `unknown`, NUNCA "aplicado";
- reenvio so com o mesmo `command_id` (idempotente).
"""

from __future__ import annotations

import logging
import re
from collections import OrderedDict
from dataclasses import asdict, dataclass, field
from typing import Any

import httpx

from bridge.config import CommandSpec
from bridge.envelope import utc_now

log = logging.getLogger(__name__)

STORED_COMMANDS = 256
# Mesmo padrao do ControlCommand da Fase 2: o bridge recusa 400 antes de gastar
# uma ida ao Ezio para levar 422.
COMMAND_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
ISSUED_BY_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._@-]{1,63}$")

STATE_APPLIED = "applied"
STATE_REJECTED = "rejected"
STATE_UNKNOWN = "unknown"

# Estados do ControlCommand da Fase 2 (control_endpoints.py:75-79) traduzidos
# para os do bridge. `denied` = nada foi executado, entao e rejeicao, nao duvida.
EZIO_STATE_MAP = {
    "applied": STATE_APPLIED,
    "rejected": STATE_REJECTED,
    "denied": STATE_REJECTED,
    "unknown": STATE_UNKNOWN,
    "in_flight": STATE_UNKNOWN,
}

# HTTP que o bridge devolve ao chamador, por estado (a Fase 2 usa 202 para unknown).
HTTP_FOR_STATE = {STATE_APPLIED: 200, STATE_REJECTED: 400, STATE_UNKNOWN: 202}

DEFAULT_ISSUED_BY = "mike"


def _state_from_ezio(body: Any) -> str | None:
    """O Ezio e a autoridade sobre o desfecho: se ele diz o estado, vale o dele."""
    if isinstance(body, dict):
        state = body.get("state")
        if isinstance(state, str):
            return EZIO_STATE_MAP.get(state.strip().lower())
    return None


def _state_from_status(status_code: int) -> str:
    """Fallback quando o corpo nao traz estado."""
    if 200 <= status_code < 300:
        return STATE_APPLIED
    if status_code == 503:
        # 503 do Ezio = "nada foi executado" (control_endpoints.py:26), nao duvida.
        return STATE_REJECTED
    if status_code < 500:
        return STATE_REJECTED
    return STATE_UNKNOWN


@dataclass
class CommandRecord:
    command_id: str
    kind: str
    state: str
    ts: str
    ezio_status: int | None = None
    detail: str = ""
    replayed: bool = False
    attempts: int = 0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class DispatchOutcome:
    state: str
    http_status: int
    body: dict[str, Any]
    detail: str = ""
    ezio_status: int | None = None
    record: CommandRecord | None = field(default=None)


# Sem credencial por decisao de projeto (12/09/2026). A fronteira do bridge e
# o BIND: ``HOST = "127.0.0.1"`` e constante em bridge/config.py, entao origem
# externa nao consegue nem abrir o socket. O que sobra como portao e a allowlist
# default-deny dos ``kind`` (ver ALLOWED/FORBIDDEN abaixo e control_endpoints.py).
# Nao ha token a vazar, rotacionar ou esquecer.


class CommandStore:
    """Historico em memoria, limitado. Nada vai para disco — de proposito."""

    def __init__(self, maxlen: int = STORED_COMMANDS) -> None:
        self._items: OrderedDict[str, CommandRecord] = OrderedDict()
        self._maxlen = maxlen

    def get(self, command_id: str) -> CommandRecord | None:
        return self._items.get(command_id)

    def put(self, record: CommandRecord) -> CommandRecord:
        self._items[record.command_id] = record
        self._items.move_to_end(record.command_id)
        while len(self._items) > self._maxlen:
            self._items.popitem(last=False)
        return record

    def count(self) -> int:
        return len(self._items)

    def counts_by_state(self) -> dict[str, int]:
        result: dict[str, int] = {}
        for record in self._items.values():
            result[record.state] = result.get(record.state, 0) + 1
        return result

    def recent(self, limit: int = 50) -> list[CommandRecord]:
        """Ultimos comandos, **mais novo primeiro**. Somente leitura.

        Existe para o painel (`console.py`) nao precisar alcancar `_items`:
        atributo privado de outro modulo e acoplamento que quebra calado.
        """
        if limit <= 0:
            return []
        records = list(self._items.values())
        records.reverse()
        return records[:limit]


class CommandRouter:
    """Valida e despacha para a rota de comando do Ezio. Nao persiste nada."""

    def __init__(
        self,
        base_url: str,
        allowlist: dict[str, CommandSpec],
        store: CommandStore,
        timeout_s: float = 10.0,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.allowlist = allowlist
        self.store = store
        self.timeout_s = timeout_s
        self._client = client
        self._owns_client = client is None

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

    def spec_for(self, kind: str) -> CommandSpec | None:
        """Default-deny: so devolve spec se o kind estiver na allowlist e habilitado."""
        spec = self.allowlist.get(kind)
        if spec is None or not spec.enabled:
            return None
        return spec

    def headers(self) -> dict[str, str]:
        """Sem `authorization`: o Ezio nao exige credencial do bridge (12/09/2026)."""
        return {"content-type": "application/json", "x-bridge-source": "mike-ezio-bridge"}

    @staticmethod
    def payload_for(
        kind: str,
        command_id: str,
        params: Any,
        issued_by: str = DEFAULT_ISSUED_BY,
        ttl_s: int | None = None,
    ) -> dict[str, Any]:
        """Corpo do ControlCommand da Fase 2 (src/agent_server/control_endpoints.py:134).

        O modelo dele e `extra="forbid"`: campo a mais vira 422. Nada de
        `payload` nem `source` aqui — `params` e o nome do contrato.
        """
        body: dict[str, Any] = {
            "command_id": command_id,
            "kind": kind,
            "params": params if isinstance(params, dict) else {"value": params},
            "issued_by": issued_by or DEFAULT_ISSUED_BY,
        }
        if ttl_s is not None:
            body["ttl_s"] = ttl_s
        return body

    async def dispatch(
        self,
        spec: CommandSpec,
        command_id: str,
        params: Any,
        ezio_up: bool,
        issued_by: str = DEFAULT_ISSUED_BY,
        ttl_s: int | None = None,
    ) -> DispatchOutcome:
        """Despacha um comando. Sem fila: Ezio fora do ar => 503 e nada guardado."""
        if not ezio_up:
            return DispatchOutcome(
                state=STATE_UNKNOWN,
                http_status=503,
                body={
                    "detail": "ezio_unreachable",
                    "message": "Ezio nao esta respondendo ao polling; comando nao enfileirado.",
                    "command_id": command_id,
                    "kind": spec.kind,
                },
                detail="ezio_unreachable",
            )

        request_body = self.payload_for(spec.kind, command_id, params, issued_by, ttl_s)
        try:
            client = await self._ensure_client()
            response = await client.request(
                spec.method, spec.path, json=request_body, headers=self.headers()
            )
        except (httpx.HTTPError, OSError) as exc:
            # Saiu daqui sem resposta: pode ter sido aplicado la. Nunca "applied".
            return self._record(
                command_id,
                spec.kind,
                STATE_UNKNOWN,
                HTTP_FOR_STATE[STATE_UNKNOWN],
                {"detail": "ezio_sem_resposta", "message": str(exc)},
                detail=f"{type(exc).__name__}: {exc}",
            )

        if response.status_code in (404, 405):
            # Rota de comando da Fase 2 ausente: 503, e NAO grava estado
            # (nada foi aplicado, um reenvio depois que a rota existir e legitimo).
            return DispatchOutcome(
                state=STATE_UNKNOWN,
                http_status=503,
                body={
                    "detail": "command_route_absent",
                    "message": f"Rota {spec.path} ausente no Ezio (HTTP {response.status_code}).",
                    "command_id": command_id,
                    "kind": spec.kind,
                },
                detail="command_route_absent",
                ezio_status=response.status_code,
            )

        ezio_body = _safe_json(response)
        state = _state_from_ezio(ezio_body) or _state_from_status(response.status_code)
        body = {
            "detail": f"ezio_http_{response.status_code}",
            "command_id": command_id,
            "kind": spec.kind,
            "ezio_status": response.status_code,
            "ezio_body": ezio_body,
        }
        return self._record(
            command_id,
            spec.kind,
            state,
            HTTP_FOR_STATE.get(state, 400),
            body,
            detail=f"ezio_http_{response.status_code}",
            ezio_status=response.status_code,
        )

    def _record(
        self,
        command_id: str,
        kind: str,
        state: str,
        http_status: int,
        body: dict[str, Any],
        detail: str = "",
        ezio_status: int | None = None,
    ) -> DispatchOutcome:
        record = CommandRecord(
            command_id=command_id,
            kind=kind,
            state=state,
            ts=utc_now(),
            ezio_status=ezio_status,
            detail=detail,
            attempts=1,
        )
        self.store.put(record)
        return DispatchOutcome(
            state=state,
            http_status=http_status,
            body=body,
            detail=detail,
            ezio_status=ezio_status,
            record=record,
        )


def _safe_json(response: httpx.Response) -> Any:
    try:
        return response.json()
    except ValueError:
        return response.text[:500]
