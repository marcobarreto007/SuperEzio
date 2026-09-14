"""Aplicacao do bridge: 127.0.0.1:8009.

Superficie (tudo loopback):
  GET  /health          estado do bridge, do Ezio e do MIKE
  GET  /snapshot        hashes por rota (sem despejar corpos)
  GET  /events/recent   ultimos eventos do envelope
  POST /poll            forca um ciclo de coleta agora (diagnostico)
  POST /commands        unico ponto de mutacao: allowlist default-deny
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from bridge import __version__
from bridge.collector import EzioCollector
from bridge.commands import (
    COMMAND_ID_RE,
    DEFAULT_ISSUED_BY,
    ISSUED_BY_RE,
    STATE_APPLIED,
    STATE_REJECTED,
    STATE_UNKNOWN,
    CommandRouter,
    CommandStore,
)
from bridge.config import HOST, Settings, load_settings
from bridge.console import register as register_console
from bridge.envelope import EventLog

# Origens liberadas a LER o console pelo navegador (CORS). Os dois paineis —
# o do Ezio (:8002) e o do MIKE (:8083) — sao origens diferentes do bridge
# (:8009), entao sem este cabecalho o navegador bloqueia a leitura de
# /console/state com "No 'Access-Control-Allow-Origin' header is present".
#
# Estreito de proposito: SO as duas origens locais dos paineis, e SO leitura.
# O console e somente leitura por desenho (nenhuma rota muta, nenhuma aceita
# corpo) e o bridge NAO tem credencial (decisao de 12/09/2026), entao nao ha o
# que vazar. Qualquer outra origem continua bloqueada, e o bind em 127.0.0.1
# segue sendo a fronteira.
CONSOLE_ALLOWED_ORIGINS = frozenset(
    {
        "http://127.0.0.1:8002",
        "http://localhost:8002",
        "http://127.0.0.1:8083",
        "http://localhost:8083",
    }
)
from bridge.publisher import MikePublisher

log = logging.getLogger(__name__)


class BridgeRuntime:
    """Estado do processo: coletor, publisher, roteador de comando e tarefas."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.events = EventLog()
        self.collector = EzioCollector(
            settings.ezio_base_url,
            settings.routes,
            self.events,
            timeout_s=settings.http_timeout_s,
            vocabulary=settings.vocabulary,
        )
        self.publisher = MikePublisher(
            settings.mike_base_url, settings.mike_send_path, timeout_s=settings.http_timeout_s
        )
        self.store = CommandStore()
        self.router = CommandRouter(
            settings.ezio_base_url,
            settings.commands,
            self.store,
            timeout_s=settings.command_timeout_s,
        )
        self._tasks: list[asyncio.Task] = []
        self.started_ts: str | None = None

    # ------------------------------------------------------------------ ciclo

    async def start(self) -> None:
        await self.publisher.start()
        queue = self.events.subscribe(maxsize=256)
        self._tasks = [
            asyncio.create_task(self._drain_events(queue)),
            asyncio.create_task(self._poll_loop()),
        ]
        # O primeiro ciclo bem-sucedido emite `ezio.boot` (vocabulario fechado do
        # events.toml). O ciclo de vida do proprio bridge aparece em GET /health.
        log.info(
            "bridge %s no ar em http://%s (rotas: %s)",
            __version__,
            HOST,
            len(self.settings.routes),
        )

    async def stop(self) -> None:
        for task in self._tasks:
            task.cancel()
        for task in self._tasks:
            with contextlib.suppress(asyncio.CancelledError):
                await task
        self._tasks = []
        await self.publisher.stop()
        await self.collector.aclose()
        await self.router.aclose()

    async def _drain_events(self, queue: asyncio.Queue) -> None:
        while True:
            event = await queue.get()
            self.publisher.publish(event)

    async def _poll_loop(self) -> None:
        while True:
            try:
                await self.collector.poll_once()
            except asyncio.CancelledError:
                raise
            except Exception:
                log.exception("ciclo de coleta falhou; seguindo")
            await asyncio.sleep(max(1.0, self.settings.poll_interval_s))

    # ------------------------------------------------------------------ estado

    def health(self) -> dict[str, Any]:
        ezio = self.collector.stats()
        mike = self.publisher.stats()
        if not ezio["ezio_up"] or mike["reachable"] is False:
            status = "degraded"
        else:
            status = "ok"
        return {
            "status": status,
            "version": __version__,
            "bind": HOST,
            "seq": self.events.seq,
            "snapshot_id": self.events.snapshot_id(),
            "config_errors": self.settings.config_errors,
            "ezio": ezio,
            "mike": mike,
            "commands": {
                "allowlist": sorted(self.settings.commands),
                "stored": self.store.count(),
                "by_state": self.store.counts_by_state(),
            },
        }


def create_app(settings: Settings | None = None, autostart: bool = True) -> FastAPI:
    resolved = settings or load_settings()
    runtime = BridgeRuntime(resolved)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        if autostart:
            await runtime.start()
        try:
            yield
        finally:
            if autostart:
                await runtime.stop()

    app = FastAPI(title="MIKE-Ezio bridge", version=__version__, lifespan=lifespan)
    # CORS estreito para o painel do Ezio poder LER o console (ver a constante).
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(CONSOLE_ALLOWED_ORIGINS),
        allow_methods=["GET"],
        allow_headers=["content-type"],
        allow_credentials=False,
    )
    app.state.runtime = runtime
    # Porta 2: painel de observacao do humano (so rotas GET). Ver bridge/console.py.
    register_console(app, runtime)

    @app.get("/health")
    async def health() -> JSONResponse:
        return JSONResponse(runtime.health())

    @app.get("/snapshot")
    async def snapshot() -> JSONResponse:
        return JSONResponse(
            {
                "snapshot_id": runtime.events.snapshot_id(),
                "poll_count": runtime.collector.poll_count,
                "routes": runtime.collector.stats()["routes"],
            }
        )

    @app.get("/events/recent")
    async def recent(limit: int = 50) -> JSONResponse:
        return JSONResponse({"events": runtime.events.recent(limit=max(0, min(limit, 500)))})

    @app.post("/poll")
    async def force_poll() -> JSONResponse:
        result = await runtime.collector.poll_once()
        return JSONResponse(result)

    @app.post("/commands")
    async def commands(request: Request):
        settings_now = runtime.settings

        async def denied(
            reason: str, status_code: int, kind: str = "", content: dict | None = None
        ) -> JSONResponse:
            """Toda recusa vira `ezio.command.denied` (vocabulario do events.toml)."""
            await runtime.events.emit(
                settings_now.vocabulary["command_denied"],
                {"reason": reason, "status": status_code, "kind": kind},
                source="bridge",
            )
            body_out = dict(content or {"detail": reason})
            if kind:
                body_out.setdefault("kind", kind)
            return JSONResponse(status_code=status_code, content=body_out)

        # Sem etapa de credencial por decisao de projeto (12/09/2026): a fronteira
        # e o bind em loopback (HOST constante em bridge/config.py) e o portao que
        # sobra e a allowlist default-deny logo abaixo.

        # 1) corpo
        try:
            body = await request.json()
        except ValueError:
            return await denied("corpo_nao_e_json", 400)
        if not isinstance(body, dict):
            return await denied("corpo_invalido", 400)

        kind = str(body.get("kind", "")).strip()
        command_id = str(body.get("command_id", "")).strip()
        # `params` e o nome do contrato da Fase 2; `payload` fica como apelido.
        raw_params = body.get("params", body.get("payload", {}))
        params = raw_params if isinstance(raw_params, dict) else {"value": raw_params}
        issued_by = str(body.get("issued_by", DEFAULT_ISSUED_BY)).strip()
        raw_ttl = body.get("ttl_s")
        ttl_s = raw_ttl if isinstance(raw_ttl, int) and not isinstance(raw_ttl, bool) else None

        # 2) default-deny ANTES de olhar o Ezio
        spec = runtime.router.spec_for(kind)
        if spec is None:
            return await denied("kind_nao_permitido", 403, kind=kind)

        # 3) idempotencia: mesmo command_id nunca reaplica um comando ja resolvido
        if not COMMAND_ID_RE.match(command_id):
            return await denied("command_id_invalido", 400, kind=kind)
        if not ISSUED_BY_RE.match(issued_by):
            return await denied("issued_by_invalido", 400, kind=kind)
        previous = runtime.store.get(command_id)
        if previous is not None and previous.state in (STATE_APPLIED, STATE_REJECTED):
            return JSONResponse(
                status_code=200,
                content={
                    "command_id": command_id,
                    "kind": previous.kind,
                    "state": previous.state,
                    "replayed": True,
                    "detail": "comando ja resolvido; nao foi reenviado",
                    "record": previous.to_dict(),
                },
            )

        # 4) sem fila: Ezio fora do ar => 503, nada guardado
        outcome = await runtime.router.dispatch(
            spec,
            command_id,
            params,
            runtime.collector.ezio_up,
            issued_by=issued_by,
            ttl_s=ttl_s,
        )
        if outcome.http_status == 503:
            return await denied(
                outcome.detail or "ezio_indisponivel", 503, kind=kind, content=outcome.body
            )
        await runtime.events.emit(
            settings_now.vocabulary["command_settled"],
            {
                "command_id": command_id,
                "kind": spec.kind,
                "state": outcome.state,
                "ezio_status": outcome.ezio_status,
                "retry_of_unknown": previous is not None and previous.state == STATE_UNKNOWN,
            },
            source="bridge",
        )
        content = dict(outcome.body)
        content.setdefault("state", outcome.state)
        content["replayed"] = False
        return JSONResponse(status_code=outcome.http_status, content=content)

    return app


app = create_app()
