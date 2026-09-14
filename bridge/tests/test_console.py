"""Testes da porta 2: painel de observacao em /console, /console/state e o stream.

Quatro coisas sao verificadas aqui, e sao as que importam:
1. a pagina e auto-contida (DISK ONLY: sem CDN, sem fonte externa, sem script
   remoto) e nao depende de JS moderno;
2. o que foi NEGADO aparece — inclusive a recusa por allowlist, que nao vira
   registro no CommandStore e so existe como evento `ezio.command.denied`;
3. o painel e SOMENTE LEITURA: nenhuma rota de mutacao, e ler o painel nao
   mexe em estado nenhum do bridge;
4. o /console/stream fala o contrato combinado (`poll`, `publish`, `command`,
   `state`) e o polling antigo continua funcionando ao lado dele.

Hermetico: transporte falso no lugar do Ezio, nenhum socket real.
"""

from __future__ import annotations

import asyncio
import json
import re
from typing import Any

import httpx

from bridge import console
from bridge.app import create_app
from bridge.commands import CommandSpec
from bridge.config import PollRoute, Settings
from bridge.console import CONSOLE_PATH, STATE_PATH, STREAM_PATH


class EzioFake:
    """Ezio de mentira: devolve o que o teste mandar e conta as chamadas."""

    def __init__(self, status: int = 200, body: Any = None) -> None:
        self.status = status
        self.body = body if body is not None else {"status": "ok"}
        self.calls: list[dict[str, Any]] = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.calls.append({"method": request.method, "path": request.url.path})
        return httpx.Response(self.status, json=self.body)


def make_settings(**overrides: Any) -> Settings:
    settings = Settings(
        ezio_base_url="http://ezio.test",
        mike_base_url="http://mike.test",
        routes=[PollRoute("/health", "ezio.health")],
        commands={"task.submit": CommandSpec("task.submit", "/control/command")},
    )
    for key, value in overrides.items():
        setattr(settings, key, value)
    return settings


def build_app(fake: EzioFake, settings: Settings | None = None):
    app = create_app(settings or make_settings(), autostart=False)
    runtime = app.state.runtime
    runtime.router._client = httpx.AsyncClient(
        transport=httpx.MockTransport(fake.handler), base_url="http://ezio.test"
    )
    runtime.collector.last_poll_ok = True
    return app, runtime


def get(app, path: str):
    async def run():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://bridge") as client:
            return await client.get(path)

    return asyncio.run(run())


def post(app, path: str, payload: Any):
    async def run():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://bridge") as client:
            return await client.post(path, json=payload)

    return asyncio.run(run())


def command(command_id: str = "cmd-1", kind: str = "task.submit") -> dict:
    return {"command_id": command_id, "kind": kind, "params": {"note": "teste"}}


def state(app) -> dict:
    return get(app, STATE_PATH).json()


# ------------------------------------------------------- pagina auto-contida


def test_console_e_html_auto_contido():
    """DISK ONLY: nada de CDN, nada de fonte externa, nada de script remoto."""
    app, _ = build_app(EzioFake())
    response = get(app, CONSOLE_PATH)
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    html = response.text.lower()
    assert "<script src" not in html
    assert "<iframe" not in html
    assert 'src="http' not in html and 'href="http' not in html
    # Unico <link> tolerado: o favicon embutido (mata o 404 do navegador).
    assert re.findall(r"<link[^>]*>", html) == ['<link rel="icon" href="data:,">']
    for externo in ("http://", "https://", "cdn.", "unpkg", "jsdelivr", "googleapis"):
        assert externo not in html, f"a pagina nao pode depender de {externo}"


def test_console_nao_depende_de_js_moderno():
    """ES5 + textContent: o dono pode abrir no celular velho, e payload e texto."""
    app, _ = build_app(EzioFake())
    html = get(app, CONSOLE_PATH).text
    assert "XMLHttpRequest" in html  # nao usa fetch()
    assert "fetch(" not in html
    assert "innerHTML" not in html  # todo valor entra por textContent
    assert "=>" not in html  # sem arrow function


def test_pagina_le_o_mesmo_endpoint_que_existe():
    """A pagina e o endpoint nao podem divergir de caminho em silencio."""
    app, _ = build_app(EzioFake())
    html = get(app, CONSOLE_PATH).text
    assert STATE_PATH in html
    assert get(app, STATE_PATH).status_code == 200


def test_pagina_nao_e_cacheada():
    app, _ = build_app(EzioFake())
    for path in (CONSOLE_PATH, STATE_PATH):
        assert get(app, path).headers["cache-control"] == "no-store"


# ------------------------------------------------------------- contrato do JSON


def test_state_tem_o_contrato_do_painel():
    fake = EzioFake(status=200, body={"state": "applied"})
    app, _ = build_app(fake)
    post(app, "/commands", command())
    payload = state(app)
    for chave in ("ts", "health", "counts", "blocked_total", "blocked", "commands", "events"):
        assert chave in payload, f"falta {chave} no estado do painel"
    registro = payload["commands"][0]
    for campo in ("command_id", "kind", "state", "ts", "detail", "ezio_status"):
        assert campo in registro, f"falta {campo} no comando do painel"
    assert registro["command_id"] == "cmd-1"
    assert registro["state"] == "applied"


def test_state_vazio_nao_quebra():
    app, _ = build_app(EzioFake())
    payload = state(app)
    assert payload["commands"] == []
    assert payload["blocked"] == []
    assert payload["blocked_total"] == 0
    assert payload["health"]["bind"] == "127.0.0.1"


def test_limit_fora_da_faixa_nao_quebra():
    app, _ = build_app(EzioFake())
    assert get(app, f"{STATE_PATH}?limit=0").status_code == 200
    assert get(app, f"{STATE_PATH}?limit=100000").status_code == 200
    assert get(app, f"{STATE_PATH}?limit=abc").status_code == 422  # FastAPI valida o tipo


def test_saude_do_painel_e_a_mesma_de_health():
    app, _ = build_app(EzioFake())
    assert state(app)["health"] == get(app, "/health").json()


# --------------------------------------------------------------- o que NEGADO


def test_barrado_pela_allowlist_aparece_no_painel():
    """403 kind_nao_permitido NAO vira registro no CommandStore.

    Se o painel so lesse o store, a coisa que o dono mais precisa ver — o MIKE
    pediu e foi barrado — sumiria. Por isso o painel junta o evento denied.
    """
    app, runtime = build_app(EzioFake())
    resposta = post(app, "/commands", command(kind="shell.exec"))
    assert resposta.status_code == 403
    assert runtime.store.count() == 0  # nada guardado: so existe o evento

    payload = state(app)
    assert payload["blocked_total"] == 1
    barrado = payload["blocked"][0]
    assert barrado["kind"] == "shell.exec"
    assert barrado["reason"] == "kind_nao_permitido"
    assert barrado["origin"] == "bridge"
    assert barrado["state"] == "denied"


def test_barrado_pela_allowlist_nao_vira_ruido_entre_aplicados():
    """O negado nao pode se perder no meio dos `applied` (requisito do painel)."""
    fake = EzioFake(status=200, body={"state": "applied"})
    app, _ = build_app(fake)
    for i in range(5):
        post(app, "/commands", command(command_id=f"ok-{i}"))
    post(app, "/commands", command(command_id="barrado-1", kind="shell.exec"))

    payload = state(app)
    assert len(payload["commands"]) == 5
    assert payload["counts"].get("applied") == 5
    assert payload["blocked_total"] == 1
    assert payload["blocked"][0]["kind"] == "shell.exec"


def test_recusado_pelo_ezio_aparece_marcado_como_blocked():
    fake = EzioFake(status=422, body={"state": "rejected", "detail": {"code": "bad_params"}})
    app, _ = build_app(fake)
    post(app, "/commands", command())
    payload = state(app)
    assert payload["commands"][0]["blocked"] is True
    assert payload["commands"][0]["ezio_status"] == 422
    assert payload["blocked_total"] == 1
    assert payload["blocked"][0]["origin"] == "ezio"


def test_aplicado_e_unknown_nao_entram_em_blocked():
    for status, esperado in ((200, "applied"), (500, "unknown")):
        fake = EzioFake(status=status, body={"detail": "x"})
        app, _ = build_app(fake)
        post(app, "/commands", command())
        payload = state(app)
        assert payload["commands"][0]["state"] == esperado
        assert payload["commands"][0]["blocked"] is False
        assert payload["blocked_total"] == 0


def test_ezio_caido_tambem_aparece_como_barrado():
    app, runtime = build_app(EzioFake())
    runtime.collector.last_poll_ok = False
    assert post(app, "/commands", command()).status_code == 503
    payload = state(app)
    assert payload["blocked_total"] == 1
    assert payload["blocked"][0]["reason"] == "ezio_unreachable"


def test_muitos_barrados_a_lista_nao_perde_nenhum():
    app, _ = build_app(EzioFake())
    for i in range(3):
        post(app, "/commands", command(command_id=f"x-{i}", kind="shell.exec"))
    assert state(app)["blocked_total"] == 3


def test_denials_traz_o_motivo_e_o_kind():
    app, _ = build_app(EzioFake())
    post(app, "/commands", command(command_id="id com espaco"))
    payload = state(app)
    assert payload["denials"][0]["reason"] == "command_id_invalido"
    assert payload["denials"][0]["status"] == 400


# ------------------------------------------------------------- somente leitura


def test_console_so_tem_rotas_get():
    app, _ = build_app(EzioFake())
    mutantes = []
    for route in app.routes:
        caminho = getattr(route, "path", "")
        if not caminho.startswith(CONSOLE_PATH):
            continue
        metodos = set(getattr(route, "methods", None) or set())
        if metodos - {"GET", "HEAD", "OPTIONS"}:
            mutantes.append((caminho, sorted(metodos)))
    assert mutantes == []


def test_console_recusa_post():
    app, _ = build_app(EzioFake())
    for path in (CONSOLE_PATH, STATE_PATH):
        resposta = post(app, path, {"qualquer": "coisa"})
        assert resposta.status_code == 405, f"{path} aceitou POST"


def test_as_unica_rotas_de_mutacao_continuam_sendo_poll_e_commands():
    """A porta 2 nao pode ter acrescentado nenhum caminho de escrita."""
    app, _ = build_app(EzioFake())
    mutantes = {
        getattr(route, "path", "")
        for route in app.routes
        if set(getattr(route, "methods", None) or set()) - {"GET", "HEAD", "OPTIONS"}
    }
    assert mutantes == {"/poll", "/commands"}


def test_ler_o_painel_nao_muta_estado():
    """Ler /console/state e observacao pura: nada muda no store nem no envelope."""
    fake = EzioFake(status=200, body={"state": "applied"})
    app, runtime = build_app(fake)
    post(app, "/commands", command())
    antes = (runtime.store.count(), runtime.events.seq, len(fake.calls))
    for _ in range(3):
        get(app, STATE_PATH)
        get(app, CONSOLE_PATH)
    depois = (runtime.store.count(), runtime.events.seq, len(fake.calls))
    assert antes == depois


def test_payload_hostil_sai_como_texto_e_a_pagina_nao_usa_innerhtml():
    """Payload de evento e texto de fora: entra por textContent, nunca por HTML."""
    hostil = "<img src=x onerror=alert(1)>"
    app, runtime = build_app(EzioFake())

    async def emitir():
        await runtime.events.emit("ezio.degraded", {"detalhe": hostil}, source="bridge")

    asyncio.run(emitir())
    payload = state(app)
    evento = next(e for e in payload["events"] if e["event_type"] == "ezio.degraded")
    assert evento["payload"]["detalhe"] == hostil  # JSON puro, sem escape de HTML
    assert "innerHTML" not in get(app, CONSOLE_PATH).text


def test_state_e_json_valido_e_serializavel():
    """O painel so consome JSON: nada de datetime ou objeto solto no corpo."""
    app, _ = build_app(EzioFake())
    response = get(app, STATE_PATH)
    assert response.headers["content-type"].startswith("application/json")
    json.loads(response.text)


# ------------------------------------------------------------- o stream (SSE)
#
# /console/stream e infinito: `get()` nele nunca volta. Por isso estes testes
# falam ASGI direto — abrem o escopo, juntam N quadros e fecham com
# http.disconnect, que e exatamente o que o navegador faz ao fechar a aba.
# Nenhum socket, e o encerramento prova que a fila do cliente e liberada.


def stream_scope(path: str) -> dict[str, Any]:
    return {
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": "2.3"},
        "http_version": "1.1",
        "method": "GET",
        "scheme": "http",
        "path": path,
        "raw_path": path.encode(),
        "query_string": b"",
        "root_path": "",
        "headers": [(b"host", b"bridge.test")],
        "client": ("127.0.0.1", 5555),
        "server": ("127.0.0.1", 8009),
    }


def read_stream(
    app, want: int = 1, after: Any = None, timeout: float = 5.0
) -> tuple[dict[str, Any], str]:
    """Abre o stream, junta `want` quadros e desconecta. Devolve (start, texto)."""

    async def run() -> tuple[dict[str, Any], str]:
        sent: list[dict[str, Any]] = []
        chunks: list[str] = []
        done = asyncio.Event()

        async def send(message: dict[str, Any]) -> None:
            sent.append(message)
            if message["type"] == "http.response.body":
                chunks.append(message.get("body", b"").decode("utf-8"))
                if len(chunks) >= want:
                    done.set()

        async def receive() -> dict[str, Any]:
            await done.wait()
            return {"type": "http.disconnect"}

        task = asyncio.create_task(app(stream_scope(STREAM_PATH), receive, send))
        if after is not None:
            await asyncio.sleep(0.05)  # conexao aberta: o vigia ja assinou
            await after()
        await asyncio.wait_for(task, timeout)
        start = next(m for m in sent if m["type"] == "http.response.start")
        return start, "".join(chunks)

    return asyncio.run(run())


def frames(body: str) -> list[dict[str, Any]]:
    """Quebra o texto SSE em quadros; `data` tem que ser JSON de uma linha so."""
    quadros: list[dict[str, Any]] = []
    for bloco in body.split("\n\n"):
        linhas = [linha for linha in bloco.splitlines() if linha]
        evento = next((linha[7:] for linha in linhas if linha.startswith("event: ")), "")
        if not evento:
            continue
        dados = next(linha[6:] for linha in linhas if linha.startswith("data: "))
        quadros.append({"event": evento, "data": json.loads(dados)})
    return quadros


def post_dentro(app, payload: Any) -> Any:
    """Corrotina de POST com o stream aberto.

    O `post()` do topo deste arquivo chama asyncio.run() e nao serve aqui (ja ha
    loop rodando); esta e a mesma chamada, feita de dentro dele.
    """

    async def run() -> httpx.Response:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://bridge") as client:
            return await client.post("/commands", json=payload)

    return run


def quadro_de(body: str, kind: str) -> dict[str, Any]:
    achados = [quadro for quadro in frames(body) if quadro["event"] == kind]
    assert achados, f"nenhum evento {kind} no fluxo: {body!r}"
    return achados[0]


def test_stream_e_text_event_stream_e_nao_e_cacheado():
    app, _ = build_app(EzioFake())
    start, _ = read_stream(app)
    headers = {chave.decode(): valor.decode() for chave, valor in start["headers"]}
    assert start["status"] == 200
    assert headers["content-type"].startswith("text/event-stream")
    assert headers["cache-control"] == "no-store"


def test_stream_abre_com_estado_no_envelope_do_contrato():
    """Primeiro quadro = saude agora. Sem ele a tela so pintaria na proxima BORDA."""
    app, _ = build_app(EzioFake())
    _, body = read_stream(app)
    quadro = quadro_de(body, "state")
    assert set(quadro["data"]) == {"ts", "source", "kind", "detail"}
    assert quadro["data"]["source"] == "bridge"
    assert quadro["data"]["kind"] == "state"
    assert set(quadro["data"]["detail"]) == {"status", "ezio_up", "snapshot_id"}
    assert quadro["data"]["detail"]["ezio_up"] is True  # build_app deixa o Ezio vivo
    assert quadro["data"]["detail"]["status"] == "ok"


def test_ciclo_de_poll_do_bridge_vira_evento_poll():
    """O ciclo real de coleta tem que aparecer no fluxo, rota por rota."""
    fake = EzioFake(status=200, body={"status": "ok"})
    app, runtime = build_app(fake)
    # Mesmo transporte falso que build_app instala no roteador, agora no coletor:
    # assim o ciclo de poll e de verdade e o status do quadro e o HTTP real.
    runtime.collector._client = httpx.AsyncClient(
        transport=httpx.MockTransport(fake.handler), base_url="http://ezio.test"
    )

    async def ciclo() -> None:
        await runtime.collector.poll_once()

    _, body = read_stream(app, want=2, after=ciclo)
    quadro = quadro_de(body, "poll")
    assert quadro["data"]["source"] == "bridge"
    assert set(quadro["data"]["detail"]) == {"route", "status", "seq"}
    assert quadro["data"]["detail"]["route"] == "/health"
    assert quadro["data"]["detail"]["status"] == 200


def test_publicacao_no_mike_vira_evento_publish():
    app, runtime = build_app(EzioFake())

    async def publica() -> None:
        runtime.publisher.publish({"event_type": "ezio.health", "seq": 7, "payload": {}})

    _, body = read_stream(app, want=2, after=publica)
    quadro = quadro_de(body, "publish")
    assert set(quadro["data"]["detail"]) == {"event_type", "seq", "ok"}
    assert quadro["data"]["detail"] == {"event_type": "ezio.health", "seq": 7, "ok": True}


def test_publicacao_descartada_sai_com_ok_falso():
    """ok=False = a fila do MIKE estava cheia e o evento nao entrou (publisher.py:89)."""
    app, runtime = build_app(EzioFake())

    async def enche() -> None:
        for seq in range(33):  # a fila do publisher tem 32
            runtime.publisher.publish({"event_type": "ezio.boot", "seq": seq})

    _, body = read_stream(app, want=34, after=enche)
    publicados = [q for q in frames(body) if q["event"] == "publish"]
    assert len(publicados) == 33
    assert publicados[-1]["data"]["detail"]["ok"] is False


def test_comando_barrado_pelo_bridge_vira_evento_command():
    app, runtime = build_app(EzioFake())

    async def nega() -> None:
        resposta = await post_dentro(app, command(kind="shell.exec"))()
        assert resposta.status_code == 403

    _, body = read_stream(app, want=2, after=nega)
    quadro = quadro_de(body, "command")
    assert set(quadro["data"]["detail"]) == {
        "command_id",
        "kind",
        "state",
        "origin",
        "reason",
    }
    assert quadro["data"]["detail"]["kind"] == "shell.exec"
    assert quadro["data"]["detail"]["state"] == "denied"
    assert quadro["data"]["detail"]["origin"] == "bridge"
    assert quadro["data"]["detail"]["reason"] == "kind_nao_permitido"
    assert runtime.store.count() == 0  # barrado nao vira registro, so evento


def test_comando_aplicado_vira_evento_command_com_o_veredito_do_ezio():
    app, _ = build_app(EzioFake(status=200, body={"state": "applied"}))

    async def envia() -> None:
        resposta = await post_dentro(app, command())()
        assert resposta.status_code == 200

    _, body = read_stream(app, want=2, after=envia)
    detalhe = quadro_de(body, "command")["data"]["detail"]
    assert detalhe["command_id"] == "cmd-1"
    assert detalhe["kind"] == "task.submit"
    assert detalhe["state"] == "applied"
    assert detalhe["origin"] == "ezio"
    assert detalhe["reason"] == ""


def test_mudanca_de_saude_vira_evento_state(monkeypatch):
    """`state` e mudanca, nao batida: o fluxo nao repete a mesma saude a cada 2s."""
    monkeypatch.setattr(console, "HEALTH_WATCH_S", 0.05)
    app, runtime = build_app(EzioFake())
    runtime.collector.last_poll_ok = False  # comeca degradado

    async def cura() -> None:
        await asyncio.sleep(0.3)  # deixa o vigia marcar a referencia
        runtime.collector.last_poll_ok = True

    _, body = read_stream(app, want=2, after=cura, timeout=8.0)
    quadros = frames(body)
    assert [q["event"] for q in quadros] == ["state", "state"]
    assert quadros[0]["data"]["detail"]["status"] == "degraded"
    assert quadros[1]["data"]["detail"]["status"] == "ok"
    assert quadros[1]["data"]["detail"]["ezio_up"] is True


def test_conexao_ociosa_recebe_keepalive(monkeypatch):
    """30s sem evento => `: ping`. O ping e comentario: nao e evento do contrato."""
    monkeypatch.setattr(console, "KEEPALIVE_S", 0.05)
    app, _ = build_app(EzioFake())
    _, body = read_stream(app, want=2)
    assert ": ping" in body
    assert [q["event"] for q in frames(body)] == ["state"]  # ping nao vira evento


def test_ao_fechar_a_conexao_o_painel_solta_a_fila():
    """Aba fechada = fila liberada e vigia desligado. Nada fica pendurado."""
    app, _ = build_app(EzioFake())
    feed = app.state.activity
    read_stream(app)
    assert feed.subscribers == 0


async def test_cliente_lento_perde_o_mais_antigo():
    """Fila limitada por cliente: o novo entra e o MAIS ANTIGO cai."""
    app, _ = build_app(EzioFake())
    feed = app.state.activity
    queue = feed.subscribe(maxsize=3)
    try:
        for indice in range(5):
            feed.emit("poll", {"route": f"/r{indice}", "status": 200, "seq": indice})
        assert queue.qsize() == 3
        rotas = [queue.get_nowait()["detail"]["route"] for _ in range(3)]
        assert rotas == ["/r2", "/r3", "/r4"]  # /r0 e /r1 caíram
    finally:
        feed.unsubscribe(queue)
        await asyncio.sleep(0)  # deixa o vigia terminar de sair


def test_sem_cliente_conectado_nada_e_guardado():
    """Sem assinante, emitir e no-op: nao ha historico, nao ha fila, nao ha disco."""
    app, _ = build_app(EzioFake())
    feed = app.state.activity
    feed.on_poll({"routes": {"/health": {"status": 200, "ok": True}}})
    assert feed.subscribers == 0


def test_abrir_o_stream_nao_muta_estado_do_bridge():
    """O stream e janela, nao volante: ler nao mexe em store, envelope nem Ezio."""
    fake = EzioFake(status=200, body={"state": "applied"})
    app, runtime = build_app(fake)
    post(app, "/commands", command())
    antes = (runtime.store.count(), runtime.events.seq, len(fake.calls))
    read_stream(app)
    depois = (runtime.store.count(), runtime.events.seq, len(fake.calls))
    assert antes == depois


def test_stream_recusa_post():
    app, _ = build_app(EzioFake())
    assert post(app, STREAM_PATH, {"qualquer": "coisa"}).status_code == 405


def test_polling_antigo_continua_intacto_com_o_stream_no_ar():
    """O /console/state e a pagina nao podem depender do stream para funcionar."""
    app, _ = build_app(EzioFake(status=200, body={"state": "applied"}))
    post(app, "/commands", command())
    antes = state(app)
    read_stream(app)  # stream abriu, viu e fechou
    depois = state(app)
    assert [c["command_id"] for c in antes["commands"]] == ["cmd-1"]
    assert [c["command_id"] for c in depois["commands"]] == ["cmd-1"]
    assert get(app, CONSOLE_PATH).status_code == 200
