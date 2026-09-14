"""Testes da superficie HTTP do bridge: allowlist default-deny, estados, idempotencia.

Tudo hermetico: transporte falso no lugar do Ezio, nenhum socket real.
Sem credencial por decisao de projeto (12/09/2026): o portao da porta de comando
e a allowlist default-deny dos `kind`; a fronteira externa e o bind em loopback.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

import httpx

from bridge import config
from bridge.app import create_app
from bridge.commands import CommandSpec
from bridge.config import PollRoute, Settings


class EzioFake:
    """Ezio de mentira: devolve o que o teste mandar e conta as chamadas."""

    def __init__(self, status: int = 200, body: Any = None, exc: Exception | None = None) -> None:
        self.status = status
        self.body = body if body is not None else {"status": "ok"}
        self.exc = exc
        self.calls: list[dict[str, Any]] = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.calls.append(
            {
                "method": request.method,
                "path": request.url.path,
                "json": json.loads(request.content or b"{}"),
                "auth": request.headers.get("authorization"),
            }
        )
        if self.exc is not None:
            raise self.exc
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
    runtime.collector.last_poll_ok = True  # Ezio "vivo" conforme o ultimo ciclo
    return app, runtime


def post(app, path: str = "/commands", payload: Any = None, headers: dict | None = None):
    async def run():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://bridge") as client:
            return await client.post(path, json=payload, headers=headers or {})

    return asyncio.run(run())


def get(app, path: str = "/health"):
    async def run():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://bridge") as client:
            return await client.get(path)

    return asyncio.run(run())


def body(command_id: str = "cmd-1", kind: str = "task.submit", payload: Any = None) -> dict:
    return {"command_id": command_id, "kind": kind, "payload": payload or {"note": "teste"}}


# ------------------------------------------ porta de comando: bind + allowlist


def test_bind_e_sempre_loopback():
    assert config.HOST == "127.0.0.1"


def test_commands_aceita_requisicao_sem_header_nenhum():
    """Nao ha credencial a apresentar: a fronteira e o bind em loopback."""
    fake = EzioFake(status=200, body={"state": "applied"})
    app, runtime = build_app(fake)
    response = post(app, payload=body())
    assert response.status_code == 200
    assert response.json()["state"] == "applied"
    assert len(fake.calls) == 1
    assert runtime.store.get("cmd-1").state == "applied"


def test_header_de_credencial_qualquer_e_ignorado():
    """Nao ha auth para passar nem para falhar: nenhum header muda o desfecho."""
    fake = EzioFake(status=200, body={"state": "applied"})
    app, _ = build_app(fake)
    response = post(app, payload=body(), headers={"Authorization": "Bearer qualquer-coisa"})
    assert response.status_code == 200
    assert response.json()["detail"] != "nao_autorizado"


def test_kind_fora_da_allowlist_e_403_antes_de_falar_com_o_ezio():
    """O portao que sobra: default-deny do `kind`, sem tocar no Ezio."""
    fake = EzioFake()
    app, runtime = build_app(fake)
    response = post(app, payload=body(kind="shell.exec"))
    assert response.status_code == 403
    assert response.json()["detail"] == "kind_nao_permitido"
    assert fake.calls == []
    assert runtime.store.count() == 0


def test_kind_ausente_ou_vazio_tambem_e_403():
    fake = EzioFake()
    app, runtime = build_app(fake)
    assert post(app, payload={"command_id": "id-sem-kind"}).status_code == 403
    assert post(app, payload=body(kind="")).status_code == 403
    assert fake.calls == []
    assert runtime.store.count() == 0


def test_command_id_invalido_e_400():
    fake = EzioFake()
    app, _ = build_app(fake)
    response = post(app, payload=body(command_id="id com espaco"))
    assert response.status_code == 400
    assert response.json()["detail"] == "command_id_invalido"
    assert fake.calls == []


# ------------------------------------------------------------------ estados


def test_2xx_vira_applied():
    fake = EzioFake(status=200, body={"state": "applied"})
    app, runtime = build_app(fake)
    response = post(app, payload=body())
    assert response.status_code == 200
    assert response.json()["state"] == "applied"
    assert runtime.store.get("cmd-1").state == "applied"


def test_4xx_vira_rejected():
    fake = EzioFake(status=422, body={"state": "rejected", "detail": {"code": "bad_params"}})
    app, runtime = build_app(fake)
    response = post(app, payload=body())
    assert response.status_code == 400
    assert response.json()["state"] == "rejected"
    assert runtime.store.get("cmd-1").state == "rejected"


def test_5xx_vira_unknown_nunca_applied():
    fake = EzioFake(status=500, body={"detail": "boom"})
    app, runtime = build_app(fake)
    response = post(app, payload=body())
    assert response.status_code == 202  # unknown: 202, a convencao da Fase 2
    assert response.json()["state"] == "unknown"
    assert runtime.store.get("cmd-1").state == "unknown"


def test_timeout_vira_unknown_nunca_applied():
    fake = EzioFake(exc=httpx.ReadTimeout("sem resposta"))
    app, runtime = build_app(fake)
    response = post(app, payload=body())
    assert response.status_code == 202
    assert response.json()["state"] == "unknown"
    assert runtime.store.get("cmd-1").state == "unknown"


def test_503_do_ezio_e_denied_nao_duvida():
    """503 do Ezio = 'nada foi executado' (control_endpoints.py:26): e rejected, nao unknown."""
    fake = EzioFake(status=503, body={"state": "denied", "detail": {"code": "nada_executado"}})
    app, runtime = build_app(fake)
    response = post(app, payload=body())
    assert response.status_code == 400
    assert response.json()["state"] == "rejected"
    assert runtime.store.get("cmd-1").state == "rejected"


def test_estado_do_ezio_vence_o_http():
    """O Ezio e a autoridade: 200 com state=unknown continua unknown."""
    fake = EzioFake(status=200, body={"state": "unknown", "detail": {"code": "in_flight"}})
    app, runtime = build_app(fake)
    response = post(app, payload=body())
    assert response.status_code == 202
    assert runtime.store.get("cmd-1").state == "unknown"


def test_rota_de_comando_ausente_vira_503_e_nao_grava_estado():
    """Fase 2 ainda nao criou a rota: 503, e reenvio depois continua possivel."""
    fake = EzioFake(status=404, body={"detail": "Not Found"})
    app, runtime = build_app(fake)
    response = post(app, payload=body())
    assert response.status_code == 503
    assert response.json()["detail"] == "command_route_absent"
    assert runtime.store.count() == 0


def test_ezio_caido_e_503_sem_enfileirar_nada():
    fake = EzioFake()
    app, runtime = build_app(fake)
    runtime.collector.last_poll_ok = False
    response = post(app, payload=body())
    assert response.status_code == 503
    assert response.json()["detail"] == "ezio_unreachable"
    assert fake.calls == []
    assert runtime.store.count() == 0


# --------------------------------------------------------------- idempotencia


def test_mesmo_command_id_nao_reaplica():
    fake = EzioFake(status=200)
    app, _ = build_app(fake)
    first = post(app, payload=body(command_id="id-fixo"))
    second = post(app, payload=body(command_id="id-fixo"))
    assert first.status_code == 200 and first.json()["replayed"] is False
    assert second.status_code == 200 and second.json()["replayed"] is True
    assert second.json()["state"] == "applied"
    assert len(fake.calls) == 1  # o Ezio foi chamado uma vez so


def test_reenvio_de_unknown_com_o_mesmo_id_e_permitido():
    fake = EzioFake(status=500)
    app, _ = build_app(fake)
    assert post(app, payload=body(command_id="id-x")).json()["state"] == "unknown"
    assert post(app, payload=body(command_id="id-x")).json()["state"] == "unknown"
    assert len(fake.calls) == 2  # unknown pode ser reenviado, com o mesmo id


def test_payload_enviado_ao_ezio_tem_o_contrato_da_fase_2():
    """`extra="forbid"` do ControlCommand: campo a mais vira 422. Nada de `source`."""
    fake = EzioFake()
    app, _ = build_app(fake)
    post(app, payload=body(command_id="id-c"))
    sent = fake.calls[0]["json"]
    assert sent == {
        "command_id": "id-c",
        "kind": "task.submit",
        "params": {"note": "teste"},
        "issued_by": "mike",
    }


def test_params_payload_ttl_e_issued_by_sao_repassados():
    fake = EzioFake(body={"state": "applied"})
    app, _ = build_app(fake)
    post(
        app,
        payload={
            "command_id": "id-t",
            "kind": "task.submit",
            "params": {"a": 1},
            "issued_by": "operador",
            "ttl_s": 30,
        },
    )
    sent = fake.calls[0]["json"]
    assert sent["params"] == {"a": 1}
    assert sent["issued_by"] == "operador"
    assert sent["ttl_s"] == 30


def test_issued_by_invalido_e_400():
    fake = EzioFake()
    app, _ = build_app(fake)
    response = post(app, payload=body() | {"issued_by": "a"})
    assert response.status_code == 400
    assert response.json()["detail"] == "issued_by_invalido"
    assert fake.calls == []


def test_bridge_nunca_manda_authorization_ao_ezio():
    """Nao ha segredo para vazar: o Ezio nao exige credencial do bridge."""
    fake = EzioFake()
    app, _ = build_app(fake)
    post(app, payload=body())
    assert fake.calls[0]["auth"] is None


def test_health_nao_anuncia_credencial():
    """A superficie de saude nao expoe (nem anuncia) campo de credencial."""
    fake = EzioFake()
    app, _ = build_app(fake)
    payload = get(app, "/health").json()
    assert payload["bind"] == "127.0.0.1"
    assert "auth_configured" not in payload["commands"]


# ------------------------------------------------- vocabulario do events.toml


def test_recusa_emite_command_denied():
    fake = EzioFake()
    app, runtime = build_app(fake)
    post(app, payload=body(kind="shell.exec"))
    found = [e["event_type"] for e in runtime.events.recent(20)]
    assert "ezio.command.denied" in found


def test_ezio_caido_emite_command_denied_e_nao_settled():
    fake = EzioFake()
    app, runtime = build_app(fake)
    runtime.collector.last_poll_ok = False
    post(app, payload=body())
    found = [e["event_type"] for e in runtime.events.recent(20)]
    assert found == ["ezio.command.denied"]


def test_comando_aplicado_emite_command_settled():
    fake = EzioFake(status=200)
    app, runtime = build_app(fake)
    post(app, payload=body())
    found = [e["event_type"] for e in runtime.events.recent(20)]
    assert "ezio.command.settled" in found
    settled = next(
        e for e in runtime.events.recent(20) if e["event_type"] == "ezio.command.settled"
    )
    assert settled["payload"]["state"] == "applied"
    assert settled["payload"]["ezio_status"] == 200
