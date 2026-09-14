"""Porta 2: painel de observacao do bridge (o plano de controle), em /console.

POR QUE ESTE ARQUIVO PERTENCE AO NUCLEO CONFIAVEL
-------------------------------------------------
O painel e a janela pela qual o humano vigia o MIKE. Se o vigiado puder editar a
janela, nao ha vigilancia: ele ajusta o que o dono ve e o dono perde o unico
lugar onde enxergaria a recusa. Por isso o MIKE nao tem — e nao pode ganhar —
permissao de escrita aqui: o painel e somente leitura (so rotas GET, zero
mutacao, zero POST), mora no mesmo processo do bridge (loopback 127.0.0.1) e
nenhuma rota dele aceita corpo. Quem age e o MIKE por POST /commands; a porta 2
so mostra o que foi pedido, o que foi NEGADO e qual foi o veredito.

Fonte dos dados (nada e inventado aqui):
- comandos: CommandStore (bridge/commands.py:103), que ja tem counts_by_state();
- eventos: EventLog.recent() (bridge/envelope.py:101);
- saude: o mesmo dicionario que GET /health devolve.

Detalhe que importa ao dono: recusa por allowlist (403 kind_nao_permitido) e
recusa por corpo/id invalido NAO viram registro no CommandStore — so existem
como evento `ezio.command.denied`. Sem juntar as duas fontes, o "o MIKE pediu e
foi barrado" desapareceria do painel. Por isso `blocked` e a lista unificada.

O STREAM (SSE) — GET /console/stream
------------------------------------
O painel tambem le o fluxo em tempo real, em `text/event-stream`, com o MESMO
envelope do lado do MIKE (`{"ts","source","kind","detail"}`): o painel consome os
dois streams, entao divergir de formato seria criar dois protocolos para a mesma
janela — duas coisas para manter e uma para divergir calada.

  poll     {"route","status","seq"}                        o bridge consultou o Ezio
  publish  {"event_type","seq","ok"}                       o bridge publicou no MIKE
  command  {"command_id","kind","state","origin","reason"}  comando aceito/negado
  state    {"status","ezio_up","snapshot_id"}               a saude mudou
  (keepalive: `: ping`, sem dado, quando a conexao fica ~30s sem evento)

As fontes sao as MESMAS do polling — nada e inventado aqui:
- `poll` e `publish` sao observados envolvendo `EzioCollector.poll_once` e
  `MikePublisher.publish`. O envoltorio so OLHA o resultado e devolve o mesmo
  valor: se o observador quebrar, o bridge nem fica sabendo (ver _guarded_call);
- `command` vem da assinatura do EventLog — que e de onde `_blocked_view` ja tira
  os negados (evento `ezio.command.denied`) e os vereditos (`ezio.command.settled`);
- `state` e o mesmo `runtime.health()` que GET /health devolve.

A fila e POR CLIENTE, limitada e SEM persistencia: sem cliente conectado nada e
guardado, nada vai a disco, e cliente lento (aba travada, celular dormindo)
perde o mais ANTIGO — o bridge nunca fica preso por causa de quem esta assistindo.
O vigia de saude so roda enquanto ha ao menos um cliente conectado.
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import AsyncIterator
from typing import Any

from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse

from bridge.envelope import utc_now

log = logging.getLogger(__name__)

CONSOLE_PATH = "/console"
STATE_PATH = "/console/state"
STREAM_PATH = "/console/stream"
DEFAULT_LIMIT = 50
MAX_LIMIT = 200

# SSE: fila limitada por cliente. Cliente lento perde o mais ANTIGO (o painel
# vive do presente; o passado dele ja esta em /console/state e /events/recent).
STREAM_QUEUE_MAXSIZE = 128
# Keepalive: comentario `: ping` para proxy/navegador nao matarem conexao ociosa.
KEEPALIVE_S = 30.0
# Intervalo do vigia de saude. Barato: runtime.health() so LE contadores.
HEALTH_WATCH_S = 2.0
# Todo evento do stream e do lado do bridge, por definicao.
STREAM_SOURCE = "bridge"
STREAM_HEADERS = {
    "cache-control": "no-store",
    "x-accel-buffering": "no",  # proxy nenhum pode segurar o fluxo em buffer
}


def _guarded_call(function: Any, *args: Any) -> Any:
    """Roda um observador do painel sem deixar a excecao vazar para o bridge.

    O painel e acessorio; o bridge nao e. Se a contabilidade da janela quebrar,
    o ciclo de poll, a publicacao no MIKE e o despacho de comando seguem como se
    nada houvesse — e o `except` largo e de proposito: a fronteira e exatamente
    aqui, entre o observador e o observado.
    """
    try:
        return function(*args)
    except Exception:
        log.exception("observador do painel falhou; o bridge segue")
        return None


def _envelope(kind: str, detail: dict[str, Any]) -> dict[str, Any]:
    """Envelope do contrato — o MESMO `{"ts","source","kind","detail"}` do MIKE."""
    return {"ts": utc_now(), "source": STREAM_SOURCE, "kind": kind, "detail": detail}


def _sse_frame(message: dict[str, Any]) -> str:
    """Quadro SSE: nome do evento = kind, corpo = envelope. Uma linha de cada."""
    return f"event: {message['kind']}\ndata: {json.dumps(message, default=str)}\n\n"


def _log_task_failure(task: asyncio.Task) -> None:
    """Fim anormal do vigia nao pode virar excecao nao lida — nem silencio."""
    if task.cancelled():
        return
    error = task.exception()
    if error is not None:
        log.warning("vigia do painel caiu: %s", error)


class ActivityFeed:
    """Barramento de atividade do lado do bridge: as fontes empurram, o SSE le.

    Sem historico e sem disco: quem nao esta conectado nao perde nada que lhe
    fosse devido — o passado do painel esta em /console/state.
    """

    def __init__(self, runtime: Any) -> None:
        self._runtime = runtime
        self._subscribers: list[asyncio.Queue] = []
        self._task: asyncio.Task | None = None

    # ------------------------------------------------------------- assinatura

    @property
    def subscribers(self) -> int:
        return len(self._subscribers)

    def subscribe(self, maxsize: int = STREAM_QUEUE_MAXSIZE) -> asyncio.Queue:
        """Fila nova, limitada, so deste cliente. Liga o vigia se for o primeiro."""
        queue: asyncio.Queue = asyncio.Queue(maxsize=maxsize)
        self._subscribers.append(queue)
        self._ensure_runner()
        return queue

    def unsubscribe(self, queue: asyncio.Queue) -> None:
        """Cliente foi embora: solta a fila e, se era o ultimo, desliga o vigia."""
        try:
            self._subscribers.remove(queue)
        except ValueError:
            pass
        if not self._subscribers:
            self._stop_runner()

    # ---------------------------------------------------------------- emissao

    def emit(self, kind: str, detail: dict[str, Any]) -> None:
        """Envelope do contrato + fanout. Sem assinante, nao faz nada (sem fila)."""
        if not self._subscribers:
            return
        message = _envelope(kind, detail)
        for queue in list(self._subscribers):
            if queue.full():
                # Cliente lento (aba travada, celular dormindo): derruba o MAIS
                # ANTIGO para o novo entrar. O put_nowait sozinho faria o
                # contrario — perderia justamente o evento que acabou de chegar.
                try:
                    queue.get_nowait()
                except asyncio.QueueEmpty:
                    pass
            try:
                queue.put_nowait(message)
            except asyncio.QueueFull:
                log.warning("fila do painel cheia: evento %s descartado", kind)

    # ------------------------------------------------------------ observadores

    def on_poll(self, result: Any) -> None:
        """Um ciclo de coleta terminou: um `poll` por rota consultada.

        A forma vem de EzioCollector.poll_once(): {"routes": {path: {status, ok}}}.
        """
        routes = result.get("routes") if isinstance(result, dict) else None
        if not isinstance(routes, dict):
            return
        seq = getattr(self._runtime.events, "seq", None)
        for path, info in routes.items():
            status = info.get("status") if isinstance(info, dict) else None
            self.emit("poll", {"route": str(path), "status": status, "seq": seq})

    def on_publish(self, event: Any, ok: bool) -> None:
        """O bridge empurrou um evento para o MIKE. ok=False = fila cheia, descartado.

        `publish()` (bridge/publisher.py:89) so enfileira: quem fala com o MIKE e
        o worker. Entao `ok` e "entrou na fila", nao "o MIKE recebeu" — a entrega
        esta em GET /health (sent/dropped/reachable).
        """
        if not isinstance(event, dict):
            return
        self.emit(
            "publish",
            {
                "event_type": str(event.get("event_type", "")),
                "seq": event.get("seq"),
                "ok": bool(ok),
            },
        )

    def on_event(self, event: Any) -> None:
        """Evento do envelope: so os de comando viram atividade do painel.

        Mesma origem do `blocked` do polling: `ezio.command.denied` (barrado pelo
        bridge, nem chegou ao Ezio) e `ezio.command.settled` (veredito do Ezio).
        """
        if not isinstance(event, dict):
            return
        payload = event.get("payload")
        payload = payload if isinstance(payload, dict) else {}
        vocabulary = getattr(self._runtime.settings, "vocabulary", None) or {}
        if event.get("event_type") == vocabulary.get("command_denied", "ezio.command.denied"):
            self.emit(
                "command",
                {
                    "command_id": "",
                    "kind": str(payload.get("kind", "")),
                    "state": "denied",
                    "origin": "bridge",
                    "reason": str(payload.get("reason", "")),
                },
            )
        elif event.get("event_type") == vocabulary.get("command_settled", "ezio.command.settled"):
            state = str(payload.get("state", ""))
            self.emit(
                "command",
                {
                    "command_id": str(payload.get("command_id", "")),
                    "kind": str(payload.get("kind", "")),
                    "state": state,
                    "origin": "ezio",
                    "reason": _settled_reason(state, payload.get("ezio_status")),
                },
            )

    def current_state(self) -> dict[str, Any] | None:
        """Saude agora, no formato do contrato. None se nem isso da para ler."""
        health = _guarded_call(self._runtime.health)
        if not isinstance(health, dict):
            return None
        ezio = health.get("ezio")
        ezio = ezio if isinstance(ezio, dict) else {}
        return {
            "status": str(health.get("status", "")),
            "ezio_up": bool(ezio.get("ezio_up")),
            "snapshot_id": str(health.get("snapshot_id", "")),
        }

    # ------------------------------------------------------- observacao das fontes

    def install(self) -> ActivityFeed:
        """Passa a observar as fontes que ja existem. SOMENTE LEITURA.

        Os envoltorios devolvem exatamente o que a fonte devolveu: quem chama (o
        ciclo de poll e o dreno do envelope, em bridge/app.py) nao ve diferenca
        nenhuma. Nao ha rota nova de escrita, nem estado novo no bridge — so
        olhar. Se o observador quebrar, `_guarded_call` engole e o bridge segue.
        """
        collector = self._runtime.collector
        original_poll = collector.poll_once

        async def observed_poll() -> Any:
            result = await original_poll()
            _guarded_call(self.on_poll, result)
            return result

        collector.poll_once = observed_poll

        publisher = self._runtime.publisher
        original_publish = publisher.publish

        def observed_publish(event: Any) -> bool:
            ok = original_publish(event)
            _guarded_call(self.on_publish, event, ok)
            return ok

        publisher.publish = observed_publish
        return self

    # ------------------------------------------------------------------- vigia

    def _ensure_runner(self) -> None:
        if self._task is not None and not self._task.done():
            return
        self._task = asyncio.create_task(self._run(), name="bridge-console-stream")
        self._task.add_done_callback(_log_task_failure)

    def _stop_runner(self) -> None:
        task, self._task = self._task, None
        if task is not None:
            task.cancel()  # o vigia termina sozinho no proximo await

    async def _run(self) -> None:
        """Assina o envelope e vigia a saude — so enquanto ha cliente conectado."""
        queue = self._runtime.events.subscribe(maxsize=STREAM_QUEUE_MAXSIZE)
        baseline: tuple[str, bool] | None = None
        try:
            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=HEALTH_WATCH_S)
                except TimeoutError:
                    event = None
                if event is not None:
                    _guarded_call(self.on_event, event)
                current = self.current_state()
                if current is None:
                    continue
                signature = (current["status"], current["ezio_up"])
                if baseline is None:
                    baseline = signature  # primeira leitura so marca a referencia
                elif signature != baseline:
                    baseline = signature
                    self.emit("state", current)
        finally:
            self._runtime.events.unsubscribe(queue)


def _settled_reason(state: str, ezio_status: Any) -> str:
    """Mesmo texto que o CommandStore gravaria (commands.py: `ezio_http_NNN`)."""
    if state in BLOCKED_STATES and isinstance(ezio_status, int):
        return f"ezio_http_{ezio_status}"
    return ""


async def _stream_frames(feed: ActivityFeed) -> AsyncIterator[str]:
    """Gerador do /console/stream. Termina quando o cliente vai embora."""
    queue = feed.subscribe()
    try:
        current = feed.current_state()
        if current is not None:
            # Pintura inicial: sem isso a primeira tela so sairia na proxima
            # MUDANCA de saude, que pode levar horas.
            yield _sse_frame(_envelope("state", current))
        while True:
            try:
                message = await asyncio.wait_for(queue.get(), timeout=KEEPALIVE_S)
            except TimeoutError:
                yield ": ping\n\n"  # keepalive: comentario, o painel ignora
                continue
            yield _sse_frame(message)
    finally:
        feed.unsubscribe(queue)


# Estados que significam "barrado" (ver EZIO_STATE_MAP em bridge/commands.py:36:
# o `denied` do Ezio ja chega traduzido para `rejected`, mas os dois contam).
BLOCKED_STATES = frozenset({"rejected", "denied"})

# Polling de 2s da PAGINA (a que ja existia, e que nao pode parar de funcionar).
# Ele continua sendo o caminho principal de /console: le ~1 KB a cada 2s em
# loopback, nao depende de conexao aberta e se recupera sozinho de qualquer
# queda. O /console/stream e um SEGUNDO caminho, ao lado deste — nao no lugar
# dele — para quem quiser o fluxo em tempo real (ver o docstring do modulo).
REFRESH_MS = 2000


def _recent_command_records(store: Any, limit: int) -> list[dict[str, Any]]:
    """Ultimos comandos do CommandStore, mais novo primeiro.

    Le pelo metodo publico ``recent()`` (bridge/commands.py). O peek em
    ``_items`` que existia aqui foi removido quando o store ganhou listagem:
    alcancar atributo privado de outro modulo e acoplamento que quebra calado.
    """
    recent = getattr(store, "recent", None)
    if recent is None:
        return []
    try:
        records = recent(limit)
    except (AttributeError, TypeError):  # formato inesperado: nao derruba o painel
        log.warning("CommandStore sem recent() utilizavel; painel segue sem comandos")
        return []
    return [record.to_dict() for record in records]


def _denials_from_events(runtime: Any, limit: int) -> list[dict[str, Any]]:
    """Recusas registradas como evento `ezio.command.denied`, mais nova primeiro."""
    wanted = str(runtime.settings.vocabulary.get("command_denied", "ezio.command.denied"))
    found: list[dict[str, Any]] = []
    for event in runtime.events.recent(limit=MAX_LIMIT):
        if event.get("event_type") != wanted:
            continue
        payload = event.get("payload")
        payload = payload if isinstance(payload, dict) else {}
        reason = str(payload.get("reason", ""))
        found.append(
            {
                "ts": event.get("ts", ""),
                "seq": event.get("seq"),
                "kind": str(payload.get("kind", "")),
                "state": "denied",
                "reason": reason,
                "detail": reason,
                "status": payload.get("status"),
            }
        )
    found.reverse()
    return found[:limit]


def _blocked_view(commands: list[dict[str, Any]], denials: list[dict[str, Any]]) -> list[dict]:
    """Lista unica do que foi barrado, das duas origens, mais recente primeiro.

    `origin` diz quem barrou: `bridge` = allowlist default-deny (nem chegou ao
    Ezio); `ezio` = o Ezio recebeu e recusou.
    """
    items: list[dict[str, Any]] = []
    for record in commands:
        if not record.get("blocked"):
            continue
        items.append(
            {
                "ts": record.get("ts", ""),
                "kind": record.get("kind", ""),
                "state": record.get("state", ""),
                "command_id": record.get("command_id", ""),
                "reason": record.get("detail", ""),
                "ezio_status": record.get("ezio_status"),
                "origin": "ezio",
            }
        )
    for denial in denials:
        items.append(
            {
                "ts": denial.get("ts", ""),
                "kind": denial.get("kind", ""),
                "state": "denied",
                "command_id": "",
                "reason": denial.get("reason", ""),
                "ezio_status": denial.get("status"),
                "origin": "bridge",
            }
        )
    items.sort(key=lambda item: str(item.get("ts") or ""), reverse=True)
    return items


def build_state(runtime: Any, limit: int = DEFAULT_LIMIT) -> dict[str, Any]:
    """JSON do painel. Somente leitura: nada aqui muda estado do bridge."""
    limit = max(1, min(int(limit), MAX_LIMIT))
    commands = _recent_command_records(runtime.store, limit)
    for record in commands:
        record["blocked"] = record.get("state") in BLOCKED_STATES
    denials = _denials_from_events(runtime, limit)
    blocked = _blocked_view(commands, denials)
    return {
        "ts": utc_now(),
        "health": runtime.health(),
        "counts": runtime.store.counts_by_state(),
        "stored": runtime.store.count(),
        "blocked_total": len(blocked),
        "blocked": blocked,
        "commands": commands,
        "denials": denials,
        "events": runtime.events.recent(limit=limit),
        "seq": runtime.events.seq,
        "snapshot_id": runtime.events.snapshot_id(),
    }


# Página auto-contida: DISK ONLY, sem CDN, sem fonte externa, sem script remoto.
# CSS e JS inline. JS em ES5 (var/XMLHttpRequest/textContent) para nao depender
# de navegador moderno, e todo valor entra por textContent — nunca innerHTML —
# porque payload de evento e texto de fora.
CONSOLE_HTML = """<!doctype html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<link rel="icon" href="data:,">
<title>Porta 2 - bridge MIKE / Ezio</title>
<style>
  :root {
    --bg: #f5f6f8; --fg: #14161a; --muted: #5b6270; --card: #ffffff;
    --line: #d7dbe2; --ok: #1b7f3b; --warn: #a15c00; --bad: #b00020;
    --bad-bg: #fdecef; --bad-fg: #7a0016;
  }
  @media (prefers-color-scheme: dark) {
    :root {
      --bg: #14161a; --fg: #eef1f5; --muted: #a2aab8; --card: #1d2027;
      --line: #2c313a; --ok: #57d07d; --warn: #e0a951; --bad: #ff6b81;
      --bad-bg: #3a1620; --bad-fg: #ffd7de;
    }
  }
  * { box-sizing: border-box; }
  body {
    margin: 0; padding: 12px;
    background: var(--bg); color: var(--fg);
    font: 15px/1.45 system-ui, -apple-system, "Segoe UI", Roboto, Arial, sans-serif;
  }
  header { margin-bottom: 12px; }
  h1 { font-size: 19px; margin: 0 0 4px; }
  h2 { font-size: 16px; margin: 0 0 8px; display: flex; align-items: center; gap: 8px; }
  .sub, .hint { color: var(--muted); font-size: 13px; margin: 0; }
  .panel {
    background: var(--card); border: 1px solid var(--line); border-radius: 10px;
    padding: 12px; margin-bottom: 12px;
  }
  .panel.blocked { border: 2px solid var(--bad); background: var(--bad-bg); color: var(--bad-fg); }
  .panel.blocked h2 { color: var(--bad-fg); }
  .count {
    background: var(--line); color: var(--fg); border-radius: 999px;
    padding: 1px 9px; font-size: 13px; font-weight: 700;
  }
  .panel.blocked .count { background: var(--bad); color: #fff; }
  #status-line { margin-top: 6px; font-size: 13px; }
  .pill {
    display: inline-block; border-radius: 999px; padding: 1px 9px;
    font-weight: 700; font-size: 13px; color: #fff;
  }
  .pill.ok { background: var(--ok); }
  .pill.degraded { background: var(--bad); }
  .pill.stale { background: var(--warn); }
  .cards { display: flex; flex-direction: column; gap: 8px; }
  .card {
    border: 1px solid var(--line); border-left: 5px solid var(--muted);
    border-radius: 8px; padding: 8px 10px; background: var(--card);
  }
  .card.applied { border-left-color: var(--ok); }
  .card.unknown { border-left-color: var(--warn); }
  .card.rejected, .card.denied { border-left-color: var(--bad); background: var(--bad-bg); }
  .card .top { display: flex; flex-wrap: wrap; gap: 8px; align-items: baseline; }
  .card .kind { font-weight: 700; word-break: break-word; }
  .card .when { color: var(--muted); font-size: 12px; margin-left: auto; }
  .card .meta { color: var(--muted); font-size: 13px; margin-top: 3px; word-break: break-word; }
  .card .detail { margin-top: 4px; font-size: 13px; word-break: break-word; }
  .tag {
    font-size: 11px; text-transform: uppercase; letter-spacing: .4px;
    border: 1px solid currentColor; border-radius: 4px; padding: 0 5px;
  }
  .kv { display: flex; flex-wrap: wrap; gap: 8px; }
  .kv .item {
    border: 1px solid var(--line); border-radius: 8px; padding: 6px 9px; min-width: 130px;
  }
  .kv .k { color: var(--muted); font-size: 12px; display: block; }
  .kv .v { font-weight: 700; word-break: break-word; }
  code { font-family: ui-monospace, Consolas, "Courier New", monospace; font-size: 12px; }
  footer { color: var(--muted); font-size: 12px; padding: 4px 2px 20px; }
  @media (max-width: 420px) {
    body { padding: 8px; }
    .card .when { margin-left: 0; width: 100%; }
    .kv .item { min-width: 100%; }
  }
</style>
</head>
<body>
<header>
  <h1>Porta 2 &mdash; bridge MIKE / Ezio</h1>
  <p class="sub">Somente leitura. Quem age e o MIKE; aqui so se ve o que foi pedido,
  o que foi negado e qual foi o veredito.</p>
  <div id="status-line">carregando...</div>
</header>

<section class="panel blocked">
  <h2>NEGADOS <span class="count" id="blocked-count">0</span></h2>
  <p class="hint" id="blocked-hint">o MIKE pediu e foi barrado</p>
  <div class="cards" id="blocked-list"></div>
</section>

<section class="panel">
  <h2>Saude do sistema</h2>
  <div class="kv" id="health"></div>
</section>

<section class="panel">
  <h2>Comandos recentes <span class="count" id="cmd-count">0</span></h2>
  <div class="cards" id="commands"></div>
</section>

<section class="panel">
  <h2>Eventos recentes <span class="count" id="ev-count">0</span></h2>
  <div class="cards" id="events"></div>
</section>

<footer id="footer">bridge :8009 &middot; leitura a cada 2s de /console/state</footer>

<script>
var REFRESH_MS = %REFRESH_MS%;
var failures = 0;
var lastOk = null;

function byId(id) { return document.getElementById(id); }

function clear(node) { while (node.firstChild) { node.removeChild(node.firstChild); } }

function node(tag, cls, value) {
  var element = document.createElement(tag);
  if (cls) { element.className = cls; }
  if (value !== undefined && value !== null) { element.textContent = String(value); }
  return element;
}

function add(parent, tag, cls, value) { parent.appendChild(node(tag, cls, value)); }

function shortTime(ts) {
  if (!ts) { return "-"; }
  var text = String(ts);
  return text.length > 19 ? text.slice(11, 19) : text;
}

function card(state) {
  return node("div", "card " + (state || "unknown"));
}

function renderBlocked(items) {
  byId("blocked-count").textContent = String(items.length);
  byId("blocked-hint").textContent = items.length
    ? "o MIKE pediu e foi barrado - " + items.length + " registro(s)"
    : "nada barrado desde o boot do bridge";
  var host = byId("blocked-list");
  clear(host);
  for (var i = 0; i < items.length; i++) {
    var item = items[i];
    var box = card(item.state);
    var top = node("div", "top");
    add(top, "span", "kind", item.kind || "(sem kind)");
    add(top, "span", "tag", item.origin === "bridge" ? "barrado pelo bridge" : "recusado pelo ezio");
    add(top, "span", "when", shortTime(item.ts));
    box.appendChild(top);
    var meta = node("div", "meta");
    meta.textContent = "estado: " + (item.state || "-")
      + " | motivo: " + (item.reason || "-")
      + (item.ezio_status ? " | http ezio: " + item.ezio_status : "")
      + (item.command_id ? " | id: " + item.command_id : "");
    box.appendChild(meta);
    host.appendChild(box);
  }
}

function renderCommands(items) {
  byId("cmd-count").textContent = String(items.length);
  var host = byId("commands");
  clear(host);
  if (!items.length) { add(host, "p", "hint", "nenhum comando despachado ainda"); return; }
  for (var i = 0; i < items.length; i++) {
    var item = items[i];
    var box = card(item.blocked ? "rejected" : item.state);
    var top = node("div", "top");
    add(top, "span", "kind", item.kind || "(sem kind)");
    add(top, "span", "tag", item.state || "-");
    if (item.replayed) { add(top, "span", "tag", "replay"); }
    add(top, "span", "when", shortTime(item.ts));
    box.appendChild(top);
    var meta = node("div", "meta");
    meta.textContent = "id: " + (item.command_id || "-")
      + " | ezio http: " + (item.ezio_status === null || item.ezio_status === undefined
        ? "-" : item.ezio_status)
      + " | tentativas: " + (item.attempts === undefined ? "-" : item.attempts);
    box.appendChild(meta);
    if (item.detail) { add(box, "div", "detail", item.detail); }
    host.appendChild(box);
  }
}

function renderEvents(items) {
  byId("ev-count").textContent = String(items.length);
  var host = byId("events");
  clear(host);
  if (!items.length) { add(host, "p", "hint", "nenhum evento no envelope ainda"); return; }
  for (var i = items.length - 1; i >= 0; i--) {
    var event = items[i];
    var box = card("event");
    var top = node("div", "top");
    add(top, "span", "kind", event.event_type || "(sem tipo)");
    add(top, "span", "tag", event.source || "bridge");
    add(top, "span", "when", shortTime(event.ts));
    box.appendChild(top);
    var meta = node("div", "meta");
    meta.textContent = "seq: " + event.seq + " | snapshot: " + (event.snapshot_id || "-");
    box.appendChild(meta);
    var payload = node("div", "detail");
    payload.appendChild(node("code", null, JSON.stringify(event.payload)));
    box.appendChild(payload);
    host.appendChild(box);
  }
}

function renderHealth(health) {
  var ezio = health.ezio || {};
  var mike = health.mike || {};
  var rows = [
    ["bridge", health.status || "-"],
    ["versao", health.version || "-"],
    ["bind", health.bind || "-"],
    ["seq eventos", health.seq],
    ["snapshot", health.snapshot_id || "-"],
    ["ezio no ar", ezio.ezio_up ? "sim" : "NAO"],
    ["ezio degradado", ezio.degraded ? "sim" : "nao"],
    ["ciclos de poll", ezio.poll_count],
    ["ultimo poll", shortTime(ezio.last_poll_ts)],
    ["reinicios do ezio", ezio.restarts_detected],
    ["mike alcancavel", mike.reachable === false ? "NAO" : "sim"],
    ["fila do mike", (mike.pending === undefined ? "-" : mike.pending)
      + "/" + (mike.queue_maxsize === undefined ? "-" : mike.queue_maxsize)],
    ["eventos enviados", mike.sent],
    ["descartados", (mike.dropped_full || 0) + (mike.dropped_failed || 0)]
  ];
  var host = byId("health");
  clear(host);
  for (var i = 0; i < rows.length; i++) {
    var item = node("div", "item");
    add(item, "span", "k", rows[i][0]);
    var value = rows[i][1];
    add(item, "span", "v", value === undefined || value === null ? "-" : value);
    host.appendChild(item);
  }
}

function statusLine(state) {
  var host = byId("status-line");
  clear(host);
  var health = state.health || {};
  var pill = node("span", "pill " + (health.status === "ok" ? "ok" : "degraded"),
    health.status || "?");
  host.appendChild(pill);
  host.appendChild(node("span", null, "  lido do bridge as " + shortTime(state.ts)
    + "  |  comandos guardados: " + state.stored
    + "  |  barrados: " + state.blocked_total
    + "  |  eventos: " + state.seq));
}

function render(state) {
  failures = 0;
  lastOk = new Date();
  renderBlocked(state.blocked || []);
  renderHealth(state.health || {});
  renderCommands(state.commands || []);
  renderEvents(state.events || []);
  statusLine(state);
}

function showFailure() {
  failures = failures + 1;
  var host = byId("status-line");
  clear(host);
  host.appendChild(node("span", "pill stale", "sem contato"));
  host.appendChild(node("span", null,
    "  /console/state nao respondeu (" + failures + "x). O painel continua tentando."));
}

function load() {
  var xhr = new XMLHttpRequest();
  xhr.open("GET", "/console/state?limit=50", true);
  xhr.onreadystatechange = function () {
    if (xhr.readyState !== 4) { return; }
    if (xhr.status !== 200) { showFailure(); return; }
    try { render(JSON.parse(xhr.responseText)); } catch (err) { showFailure(); }
  };
  xhr.send(null);
}

function tick() {
  if (!lastOk) { return; }
  var seconds = Math.round((new Date() - lastOk) / 1000);
  byId("footer").textContent = "bridge :8009 - ultima leitura bem-sucedida ha "
    + seconds + "s - somente leitura";
}

load();
setInterval(load, REFRESH_MS);
setInterval(tick, 1000);
</script>
</body>
</html>
"""


def register(app: FastAPI, runtime: Any) -> None:
    """Registra as rotas GET do painel: pagina, estado e stream. Zero mutacao."""
    activity = getattr(runtime, "_activity_feed", None)
    if activity is None:
        # Uma vez por runtime: registrar duas vezes nao pode envolver as fontes
        # duas vezes (cada poll viraria dois `poll` no fluxo).
        activity = ActivityFeed(runtime).install()
        runtime._activity_feed = activity
    app.state.activity = activity

    @app.get(CONSOLE_PATH, response_class=HTMLResponse)
    async def console_page() -> HTMLResponse:
        html = CONSOLE_HTML.replace("%REFRESH_MS%", str(REFRESH_MS))
        return HTMLResponse(content=html, headers={"cache-control": "no-store"})

    @app.get(STATE_PATH)
    async def console_state(limit: int = DEFAULT_LIMIT) -> JSONResponse:
        return JSONResponse(build_state(runtime, limit), headers={"cache-control": "no-store"})

    @app.get(STREAM_PATH)
    async def console_stream() -> StreamingResponse:
        """Fluxo SSE. Somente leitura e sem corpo: nao aceita nada de fora."""
        return StreamingResponse(
            _stream_frames(activity),
            media_type="text/event-stream",
            headers=dict(STREAM_HEADERS),
        )
