"""Plano de controle MIKE -> Ezio: rota de comando com allowlist e default-deny.

Fase 2 de ``docs/architecture/MIKE_EZIO_BRIDGE.md`` (secoes 2, 5 e 8). Hoje o
Ezio nao tem rota de comando — as rotas sao leitura + ``/task/submit`` +
``/paper/approve|reject`` (``endpoints.py:2388-2402``). Este modulo entrega o
contrato que o bridge (``:8009``) usa para mandar comando.

**Allowlist explicita, default-deny.** Qualquer ``kind`` fora de
``ALLOWED_COMMAND_KINDS`` devolve 403. Nada de shell/Python generico, nada de
freeze, env var, ``/trade/manual/*``, ``/trade/execute``,
``/paper/approve|reject``, ``/evidence/*``. ``FORBIDDEN_*`` roda **antes** da
allowlist: um kind proibido nao passa nem se alguem editar a allowlist por
engano (teste cobre exatamente isso).

Envelope unico para todo desfecho::

    {command_id, kind, issued_by, state, applied, detail, evidence,
     retryable, idempotent_replay}

``state``      HTTP        significado
-------------  ----------  ----------------------------------------------------
``applied``    200         efeito confirmado pelo retorno do proprio produtor
``rejected``   409         allowlist ok, mas nada mudou (nao foi aplicado)
``unknown``    202         comando em voo; reenvio so com o mesmo command_id
``unknown``    500         efeito indeterminado (handler estourou) — nunca "applied"
``denied``     401/403/503 nada foi executado (token, allowlist ou kind proibido)

Idempotencia: ``command_id`` e a chave do ledger em memoria. O mesmo
``command_id`` devolve a **mesma** resposta dentro de ``ttl_s`` e **nao**
reexecuta o efeito. Reenvio enquanto o primeiro esta em voo devolve ``unknown``.

Integracao (nao feito aqui — ``main.py`` e de outro agente)::

    from .control_endpoints import router as control_router
    app.router.routes.extend(control_router.routes)  # padrao do a2a_router (main.py:569)
    app.state.task_executor = <callable(run_id, message, session_id)>

Sem ``app.state.task_executor`` o ``kind`` ``task.submit`` e recusado (409,
``executor_not_wired``) em vez de enfileirar uma task que nunca roda.
"""

from __future__ import annotations

import asyncio
import inspect
import re
import threading
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from core.config.logging_config import get_logger

logger = get_logger(__name__)

# ── Contrato ────────────────────────────────────────────────────────────────

CONTROL_COMMAND_PATH = "/control/commands"
# Sem credencial por decisao de projeto (12/09/2026): a fronteira do plano de
# controle e topologica (loopback) + allowlist default-deny. Ver _require_loopback.

DEFAULT_TTL_S = 60
MAX_TTL_S = 3600
MAX_MESSAGE_CHARS = 8_000  # espelha _MAX_MESSAGE_CHARS de endpoints.py:1210
MAX_COMMENT_CHARS = 1_000  # espelha /feedback (endpoints.py:2083)
LEDGER_MAX_ENTRIES = 512

STATE_APPLIED = "applied"
STATE_REJECTED = "rejected"
STATE_UNKNOWN = "unknown"
STATE_DENIED = "denied"
STATE_IN_FLIGHT = "in_flight"  # interno do ledger: nenhuma resposta sai com esse estado

HTTP_APPLIED = 200
HTTP_IN_FLIGHT = 202
HTTP_REJECTED = 409
HTTP_INDETERMINATE = 500
HTTP_DENIED = 403
HTTP_UNAUTHORIZED = 401
HTTP_UNAVAILABLE = 503

# Unicos kinds que o arquiteto aprovou (secao 5 do plano). Default-deny: tudo
# que nao esta aqui e 403, inclusive qualquer rota nova que apareca no Ezio.
ALLOWED_COMMAND_KINDS: frozenset[str] = frozenset(
    {"task.submit", "task.cancel", "feedback", "bob.ibkr.recover"}
)

# Lista explicita (secao 5: "read-only explicito"). Serve de documentacao
# executavel: mesmo que alguem acrescente um destes a allowlist, o 403 sai antes.
FORBIDDEN_COMMAND_KINDS: frozenset[str] = frozenset(
    {
        "freeze",
        "freeze.set",
        "freeze.clear",
        "env.set",
        "env.write",
        "environment.set",
        "trade.execute",
        "paper.approve",
        "paper.reject",
        "evidence.delete",
        "evidence.write",
        "shell",
        "exec",
        "eval",
        "python",
        "subprocess",
    }
)

# Familias inteiras, por regex — cobre variacao de nomeacao ("/trade/manual/x",
# "trade.manual.x", "TradeManual"). Nao ha shell/Python generico em lugar nenhum.
FORBIDDEN_COMMAND_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"freeze", re.IGNORECASE),
    re.compile(r"\benv(?:ironment)?\b", re.IGNORECASE),
    re.compile(r"trade[/.]manual", re.IGNORECASE),
    re.compile(r"trade[/.]execute", re.IGNORECASE),
    re.compile(r"paper[/.](?:approve|reject)", re.IGNORECASE),
    re.compile(r"evidence", re.IGNORECASE),
    re.compile(r"\b(?:shell|exec|eval|python|subprocess|bash|powershell)\b", re.IGNORECASE),
)

_COMMAND_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_ISSUED_BY_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._@-]{1,63}$")


class ControlCommand(BaseModel):
    """Corpo do comando. ``extra="forbid"``: nada de campo extra escondido."""

    model_config = ConfigDict(extra="forbid")

    command_id: str = Field(min_length=1, max_length=128, pattern=_COMMAND_ID_RE.pattern)
    kind: str = Field(min_length=1, max_length=120)
    params: dict[str, Any] = Field(default_factory=dict)
    issued_by: str = Field(min_length=2, max_length=64, pattern=_ISSUED_BY_RE.pattern)
    ttl_s: int = Field(default=DEFAULT_TTL_S, ge=1, le=MAX_TTL_S)


@dataclass(frozen=True)
class CommandContext:
    """O que o handler precisa saber sobre o comando que o chamou."""

    command_id: str
    kind: str
    issued_by: str
    request: Request


@dataclass(frozen=True)
class Outcome:
    """Desfecho de um comando. ``applied`` so existe quando o efeito foi confirmado."""

    state: str
    status_code: int
    detail: dict[str, Any] = field(default_factory=dict)
    evidence: dict[str, Any] = field(default_factory=dict)
    retryable: bool = False

    @property
    def applied(self) -> bool:
        return self.state == STATE_APPLIED


def applied(detail: dict[str, Any] | None = None) -> Outcome:
    """Efeito confirmado: o produtor devolveu/gravou aquilo de fato."""
    return Outcome(state=STATE_APPLIED, status_code=HTTP_APPLIED, detail=detail or {})


def rejected(code: str, message: str, **extra: Any) -> Outcome:
    """Allowlist ok, mas nada mudou. ``applied`` nunca e True aqui."""
    return Outcome(
        state=STATE_REJECTED,
        status_code=HTTP_REJECTED,
        detail={"code": code, "message": message, **extra},
    )


def unknown(
    code: str,
    message: str,
    *,
    status_code: int = HTTP_INDETERMINATE,
    retryable: bool = True,
    **extra: Any,
) -> Outcome:
    """Em voo ou efeito indeterminado. Nunca reportado como aplicado."""
    return Outcome(
        state=STATE_UNKNOWN,
        status_code=status_code,
        detail={"code": code, "message": message, **extra},
        retryable=retryable,
    )


Handler = Callable[[CommandContext, dict[str, Any]], Awaitable[Outcome]]


# ── Handlers (allowlist) ────────────────────────────────────────────────────


async def _handle_task_submit(ctx: CommandContext, params: dict[str, Any]) -> Outcome:
    """Enfileira a task E entrega a execucao ao executor do app.

    Sem ``app.state.task_executor`` a task e desenfileirada (rollback) e o
    comando e recusado: melhor 409 do que uma task fantasma segurando a sessao
    por 10 minutos sem nunca rodar.
    """
    message = str(params.get("message") or "").strip()
    if not message:
        return rejected("invalid_params", "params.message is required")
    if len(message) > MAX_MESSAGE_CHARS:
        return rejected(
            "message_too_large",
            f"params.message exceeds {MAX_MESSAGE_CHARS} characters",
        )

    session_id = str(params.get("session_id") or f"bridge:{ctx.issued_by}").strip()

    from core.pipeline.task_queue import get_task_queue

    tq = get_task_queue()
    task = tq.submit(message=message, session_id=session_id)
    if task is None:
        active = tq.active_for_session(session_id)
        return rejected(
            "session_busy",
            "session already has an active task",
            session_id=session_id,
            run_id=active.run_id if active else "",
        )

    executor = getattr(ctx.request.app.state, "task_executor", None)
    if not callable(executor):
        tq.complete(task.run_id)  # rollback: nada ficou aplicado
        return rejected(
            "executor_not_wired",
            "app.state.task_executor is not registered: task was rolled back",
            run_id=task.run_id,
        )

    try:
        pending = executor(task.run_id, message, session_id)
        if inspect.isawaitable(pending):
            await pending
    # Executor e de terceiro (main.py): pode estourar qualquer coisa e pode ter
    # comecado antes de falhar. Efeito indeterminado = unknown, nunca applied.
    # catch amplo deliberado.
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "control_command_executor_failed",
            command_id=ctx.command_id,
            kind=ctx.kind,
            run_id=task.run_id,
            error=str(exc)[:200],
        )
        return unknown(
            "executor_failed",
            "task was queued but its execution could not be confirmed",
            run_id=task.run_id,
            status_url=f"/task/status/{task.run_id}",
        )

    return applied(
        {
            "run_id": task.run_id,
            "session_id": session_id,
            "status_url": f"/task/status/{task.run_id}",
        }
    )


async def _handle_task_cancel(ctx: CommandContext, params: dict[str, Any]) -> Outcome:
    """Cancela uma task ativa. So aplica quando o cancelamento aconteceu de fato."""
    run_id = str(params.get("run_id") or "").strip()
    if not run_id:
        return rejected("invalid_params", "params.run_id is required")

    from core.pipeline.task_queue import get_task_queue

    # Sem thread: Task.cancel()/asyncio.Event.set() nao sao thread-safe — isso
    # tem que rodar no loop de eventos.
    cancelled = get_task_queue().cancel(run_id)
    if not cancelled:
        return rejected(
            "run_id_not_active",
            "no active task with this run_id; nothing was cancelled",
            run_id=run_id,
        )
    return applied({"run_id": run_id, "cancelled": True})


async def _handle_feedback(ctx: CommandContext, params: dict[str, Any]) -> Outcome:
    """Registra feedback. Aplicado so quando o arquivo existe em disco."""
    msg_id = str(params.get("msg_id") or "").strip()
    comment = str(params.get("comment") or "").strip()
    try:
        rating = int(params.get("rating", 0))
    except (TypeError, ValueError):
        return rejected("invalid_params", "params.rating must be an integer 0-5")

    if not msg_id:
        return rejected("invalid_params", "params.msg_id is required")
    if len(msg_id) > 120:
        return rejected("invalid_params", "params.msg_id is too long")
    if rating not in (0, 1, 2, 3, 4, 5):
        return rejected("invalid_params", "params.rating must be 0-5")
    if len(comment) > MAX_COMMENT_CHARS:
        return rejected("invalid_params", "params.comment is too long")

    from core.ml.feedback import save_feedback

    path = await asyncio.to_thread(save_feedback, msg_id, rating, comment=comment)
    if not getattr(path, "is_file", lambda: False)():
        return unknown(
            "feedback_not_confirmed",
            "save_feedback returned without a readable file on disk",
            msg_id=msg_id,
        )
    return applied({"msg_id": msg_id, "rating": rating, "file": path.name})


async def _handle_bob_ibkr_recover(ctx: CommandContext, params: dict[str, Any]) -> Outcome:
    """Pede reconexao do IBKR (espelha main.py:638). So aplica se ``success``."""
    from adapters.broker.ibkr_service import get_ibkr_service

    service = get_ibkr_service()
    # force_recovery_attempt() faz disconnect + sleep(1s) + connect: bloqueia,
    # entao sai do loop de eventos.
    result = await asyncio.to_thread(service.force_recovery_attempt)
    if not isinstance(result, dict) or "success" not in result:
        return unknown(
            "recovery_not_confirmed",
            "IBKR recovery returned no success flag; broker state is undetermined",
        )
    if result.get("success") is not True:
        return rejected(
            "recovery_not_confirmed",
            "IBKR recovery ran but the broker did not reconnect",
            error=str(result.get("error") or "")[:200],
        )
    return applied(
        {
            "success": True,
            "failures_reset": result.get("failures_reset", 0),
            "broker_timestamp": result.get("timestamp", ""),
        }
    )


_HANDLERS: dict[str, Handler] = {
    "task.submit": _handle_task_submit,
    "task.cancel": _handle_task_cancel,
    "feedback": _handle_feedback,
    "bob.ibkr.recover": _handle_bob_ibkr_recover,
}

# Sanidade de import: allowlist e tabela de handlers nao podem divergir.
assert set(_HANDLERS) == ALLOWED_COMMAND_KINDS, "allowlist e handlers divergiram"


def _forbidden_kind(kind: str) -> str:
    """Devolve o motivo do 403, ou '' se o kind nao for proibido."""
    if kind in FORBIDDEN_COMMAND_KINDS:
        return "forbidden_kind"
    for pattern in FORBIDDEN_COMMAND_PATTERNS:
        if pattern.search(kind):
            return "forbidden_kind_family"
    return ""


# ── Ledger de idempotencia ──────────────────────────────────────────────────

_LEDGER: dict[str, _LedgerEntry] = {}
_LEDGER_LOCK = threading.Lock()


def _now() -> float:
    """Relogio do ledger. Seam unico: o teste de TTL avanca o tempo sem dormir."""
    return time.time()


@dataclass
class _LedgerEntry:
    state: str
    status_code: int
    body: dict[str, Any]
    stored_at: float
    expires_at: float


def _prune_locked(now: float) -> None:
    for command_id in [k for k, v in _LEDGER.items() if v.expires_at <= now]:
        del _LEDGER[command_id]
    overflow = len(_LEDGER) - LEDGER_MAX_ENTRIES
    if overflow > 0:
        oldest = sorted(_LEDGER, key=lambda k: _LEDGER[k].stored_at)[:overflow]
        for command_id in oldest:
            del _LEDGER[command_id]


def reset_command_ledger_for_test() -> None:
    """Limpa o ledger — mesmo espirito de ``reset_approval_gate_for_test``."""
    with _LEDGER_LOCK:
        _LEDGER.clear()


def command_ledger_size() -> int:
    with _LEDGER_LOCK:
        return len(_LEDGER)


# ── Envelope ────────────────────────────────────────────────────────────────


def _envelope(
    command: ControlCommand,
    state: str,
    outcome: Outcome | None = None,
    *,
    idempotent_replay: bool = False,
) -> dict[str, Any]:
    detail = dict(outcome.detail) if outcome else {}
    evidence = dict(outcome.evidence) if outcome else {}
    return {
        "command_id": command.command_id,
        "kind": command.kind,
        "issued_by": command.issued_by,
        "state": state,
        "applied": state == STATE_APPLIED,
        "retryable": bool(outcome.retryable) if outcome else False,
        "detail": detail,
        "evidence": evidence,
        "idempotent_replay": idempotent_replay,
    }


def _denied(
    command: ControlCommand,
    *,
    status_code: int,
    code: str,
    message: str,
    **extra: Any,
) -> JSONResponse:
    outcome = Outcome(
        state=STATE_DENIED,
        status_code=status_code,
        detail={"code": code, "message": message, **extra},
    )
    return JSONResponse(status_code=status_code, content=_envelope(command, STATE_DENIED, outcome))


# Hosts aceitos como origem. O bind do bridge ja e loopback (constante em
# bridge/config.py), entao na pratica todo cliente cai aqui; a checagem existe
# para que trocar o bind por engano NAO abra a rota sozinho.
_LOOPBACK_HOSTS = frozenset({"127.0.0.1", "::1", "localhost"})


def _require_loopback(request: Request) -> str | None:
    """So aceita conexao de loopback. Devolve o motivo da recusa, ou ``None``.

    Sem segredo por decisao de projeto (12/09/2026): o bridge e o unico
    cliente, roda na mesma maquina, e a fronteira e **topologica** — bind em
    127.0.0.1 mais allowlist default-deny. Nao ha token a vazar, rotacionar
    ou esquecer.

    Defesa em profundidade: se alguem trocar o bind por engano, a rota
    continua recusando origem externa.
    """
    client = getattr(request, "client", None)
    host = getattr(client, "host", "") if client is not None else ""
    if host in _LOOPBACK_HOSTS:
        return None
    return f"origem_nao_loopback:{host or 'desconhecida'}"


# ── Rota ────────────────────────────────────────────────────────────────────

router = APIRouter(tags=["control"])
# Sem prefix de router: main.py registra com ``app.router.routes.extend(...)``
# (padrao do a2a_router, main.py:560-569) e o prefix seria descartado.


async def _dispatch(ctx: CommandContext, params: dict[str, Any]) -> Outcome:
    handler = _HANDLERS.get(ctx.kind)
    if handler is None:
        # Pre-check defensivo: so chega aqui se a allowlist mudar sem a tabela.
        return rejected("kind_not_allowed", f"command kind not in allowlist: {ctx.kind}")
    return await handler(ctx, params)


@router.post(CONTROL_COMMAND_PATH, response_model=None)
async def post_control_command(command: ControlCommand, request: Request) -> JSONResponse:
    """Comando do controlador externo (MIKE/bridge). Allowlist + default-deny."""
    refusal = _require_loopback(request)
    if refusal:
        logger.warning(
            "control_command_refused",
            command_id=command.command_id,
            kind=command.kind,
            reason=refusal,
        )
        return _denied(
            command,
            status_code=HTTP_DENIED,
            code=refusal,
            message="control plane aceita apenas origem loopback",
        )

    # 1) kind proibido: 403 antes de qualquer allowlist/ledger/efeito.
    forbidden = _forbidden_kind(command.kind)
    if forbidden:
        logger.warning(
            "control_command_denied",
            command_id=command.command_id,
            kind=command.kind,
            issued_by=command.issued_by,
            reason=forbidden,
        )
        return _denied(
            command,
            status_code=HTTP_DENIED,
            code=forbidden,
            message="command kind is explicitly forbidden to the control plane",
        )

    # 2) allowlist: default-deny.
    if command.kind not in ALLOWED_COMMAND_KINDS:
        logger.warning(
            "control_command_denied",
            command_id=command.command_id,
            kind=command.kind,
            issued_by=command.issued_by,
            reason="kind_not_allowed",
        )
        return _denied(
            command,
            status_code=HTTP_DENIED,
            code="kind_not_allowed",
            message="command kind is not in the control plane allowlist",
            allowed=sorted(ALLOWED_COMMAND_KINDS),
        )

    # 3) ledger de idempotencia.
    now = _now()
    with _LEDGER_LOCK:
        _prune_locked(now)
        entry = _LEDGER.get(command.command_id)
        if entry is not None and entry.state == STATE_IN_FLIGHT:
            return JSONResponse(
                status_code=HTTP_IN_FLIGHT,
                content=_envelope(
                    command,
                    STATE_UNKNOWN,
                    unknown(
                        "in_flight",
                        "command is still in flight; resend with the same command_id",
                        status_code=HTTP_IN_FLIGHT,
                    ),
                ),
            )
        if entry is not None:
            return JSONResponse(
                status_code=entry.status_code,
                content={**entry.body, "idempotent_replay": True},
            )
        _LEDGER[command.command_id] = _LedgerEntry(
            state=STATE_IN_FLIGHT,
            status_code=HTTP_IN_FLIGHT,
            body={},
            stored_at=now,
            expires_at=now + command.ttl_s,
        )

    ctx = CommandContext(
        command_id=command.command_id,
        kind=command.kind,
        issued_by=command.issued_by,
        request=request,
    )
    try:
        outcome = await _dispatch(ctx, command.params)
    # Handler pode levantar tipos variados (servico externo, disco, biblioteca).
    # O efeito fica indeterminado: unknown, nunca applied.
    except Exception as exc:
        logger.exception(
            "control_command_failed",
            command_id=command.command_id,
            kind=command.kind,
            error=str(exc)[:200],
        )
        outcome = unknown(
            "handler_error",
            f"command handler raised {type(exc).__name__}; effect is undetermined",
        )

    body = _envelope(command, outcome.state, outcome)
    settled_at = _now()
    with _LEDGER_LOCK:
        _LEDGER[command.command_id] = _LedgerEntry(
            state=outcome.state,
            status_code=outcome.status_code,
            body=body,
            stored_at=settled_at,
            expires_at=settled_at + command.ttl_s,
        )

    logger.info(
        "control_command_settled",
        command_id=command.command_id,
        kind=command.kind,
        issued_by=command.issued_by,
        state=outcome.state,
        status_code=outcome.status_code,
        ts=datetime.now(UTC).isoformat(),
    )
    return JSONResponse(status_code=outcome.status_code, content=body)


__all__ = [
    "ALLOWED_COMMAND_KINDS",
    "CONTROL_COMMAND_PATH",
    "FORBIDDEN_COMMAND_KINDS",
    "FORBIDDEN_COMMAND_PATTERNS",
    "ControlCommand",
    "Outcome",
    "command_ledger_size",
    "reset_command_ledger_for_test",
    "router",
]
