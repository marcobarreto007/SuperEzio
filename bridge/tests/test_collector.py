"""Testes da coleta por polling + diff, e do alinhamento com o inventario.

A forma dos corpos do Ezio nao foi verificada: por isso ha teste para corpo
inesperado, corpo nao-JSON e rota que responde erro.
"""

from __future__ import annotations

import ast
import asyncio
from pathlib import Path
from typing import Any

import httpx
import pytest

from bridge.collector import EzioCollector
from bridge.commands import EZIO_STATE_MAP, CommandRouter
from bridge.config import HOST, PollRoute, load_settings
from bridge.envelope import EventLog

# Contrato real da Fase 2 — lido, nunca escrito por este diretorio.
CONTROL_ENDPOINTS = (
    Path(__file__).resolve().parents[2] / "src" / "agent_server" / "control_endpoints.py"
)

# Espelha o inventario real (bridge/events.toml): /health e /health/details sao
# rotas de ciclo de vida (sem evento proprio); as outras tem evento declarado.
HEALTH = PollRoute("/health", "", "state")
HEALTH_DETAILS = PollRoute("/health/details", "", "state")
COCKPIT = PollRoute("/cockpit/summary", "ezio.cockpit.changed", "state")
TRADES = PollRoute("/trades/history", "ezio.trade.journal_changed", "list", {"limit": "50"})
SENTIMENT = PollRoute("/sentiment/alerts", "ezio.sentiment.alert", "list")


class EzioFake:
    def __init__(self, responses: dict[str, object]) -> None:
        self.responses = responses

    def handler(self, request: httpx.Request) -> httpx.Response:
        value = self.responses.get(request.url.path, {"erro": "rota nao mapeada"})
        if isinstance(value, Exception):
            raise value
        if isinstance(value, httpx.Response):
            return value
        if isinstance(value, str):
            return httpx.Response(200, text=value)
        return httpx.Response(200, json=value)


def make_collector(responses: dict[str, object], events: EventLog, routes) -> EzioCollector:
    return EzioCollector(
        "http://ezio.test",
        routes,
        events,
        client=httpx.AsyncClient(
            transport=httpx.MockTransport(EzioFake(responses).handler), base_url="http://ezio.test"
        ),
    )


def collect(responses: dict[str, object], polls: int = 1, routes=(HEALTH, COCKPIT, TRADES)):
    events = EventLog()
    collector = make_collector(responses, events, list(routes))

    async def run():
        for _ in range(polls):
            await collector.poll_once()

    asyncio.run(run())
    return collector, events


def types_of(events: EventLog) -> list[str]:
    return [event["event_type"] for event in events.recent(200)]


def test_primeiro_ciclo_emite_boot_e_nao_ruido():
    _, events = collect(
        {
            "/health": {"status": "ok"},
            "/cockpit/summary": {"equity": 1},
            "/trades/history": {"items": []},
        }
    )
    found = types_of(events)
    assert found == ["ezio.boot"]
    boot = events.recent(1)[0]
    assert boot["payload"]["routes"] == ["/cockpit/summary", "/health", "/trades/history"]
    assert boot["snapshot_id"] != "000000000000"


def test_corpo_igual_no_segundo_ciclo_nao_gera_evento():
    responses = {
        "/health": {"status": "ok"},
        "/cockpit/summary": {"equity": 1},
        "/trades/history": {"items": []},
    }
    _, events = collect(responses, polls=2)
    assert types_of(events) == ["ezio.boot"]


def test_corpo_mudado_emite_o_evento_declarado_no_inventario():
    events = EventLog()
    responses: dict[str, object] = {"/cockpit/summary": {"equity": 1}}

    async def run():
        collector = make_collector(responses, events, [COCKPIT])
        await collector.poll_once()
        responses["/cockpit/summary"] = {"equity": 2}
        await collector.poll_once()

    asyncio.run(run())
    changed = [e for e in events.recent(50) if e["event_type"] == "ezio.cockpit.changed"]
    assert len(changed) == 1
    assert changed[0]["payload"]["before_hash"] != changed[0]["payload"]["after_hash"]
    assert changed[0]["payload"]["keys"] == ["equity"]


def test_item_novo_em_lista_aparece_no_payload():
    events = EventLog()
    responses: dict[str, object] = {"/trades/history": {"items": [{"id": 1}]}}

    async def run():
        collector = make_collector(responses, events, [TRADES])
        await collector.poll_once()
        responses["/trades/history"] = {"items": [{"id": 1}, {"id": 2}]}
        await collector.poll_once()

    asyncio.run(run())
    changed = [e for e in events.recent(50) if e["event_type"] == "ezio.trade.journal_changed"]
    assert len(changed) == 1
    assert changed[0]["payload"]["new_count"] == 1
    assert changed[0]["payload"]["new_items"] == [{"id": 2}]


def test_rota_de_ciclo_de_vida_nao_emite_evento_proprio():
    events = EventLog()
    responses: dict[str, object] = {"/health": {"status": "ok"}, "/health/details": {"gpu": "ok"}}

    async def run():
        collector = make_collector(responses, events, [HEALTH, HEALTH_DETAILS])
        await collector.poll_once()
        responses["/health/details"] = {"gpu": "quente"}
        await collector.poll_once()

    asyncio.run(run())
    assert [e for e in events.recent(50) if ".changed" in e["event_type"]] == []


def test_health_que_piora_emite_degraded_e_volta_emite_recovered():
    events = EventLog()
    responses: dict[str, object] = {"/health": {"status": "ok"}}

    async def run():
        collector = make_collector(responses, events, [HEALTH])
        await collector.poll_once()
        responses["/health"] = {"status": "degraded"}
        await collector.poll_once()
        responses["/health"] = {"status": "ok"}
        await collector.poll_once()
        return collector

    collector = asyncio.run(run())
    found = types_of(events)
    assert found.count("ezio.degraded") == 1
    assert found.count("ezio.recovered") == 1
    assert collector.health_ok is True


def test_corpo_nao_json_vira_degradacao_e_nao_excecao():
    collector, events = collect({"/health": "<html>nao e json</html>"}, routes=[HEALTH])
    found = types_of(events)
    assert "ezio.degraded" in found
    assert collector.ezio_up is False
    assert collector.degraded is True
    degraded = next(e for e in events.recent(50) if e["event_type"] == "ezio.degraded")
    assert degraded["payload"]["error"] == "corpo nao e JSON"


def test_falha_repetida_nao_repete_o_evento_a_cada_ciclo():
    collector, events = collect({"/health": "nao e json"}, polls=3, routes=[HEALTH])
    assert types_of(events).count("ezio.degraded") == 1  # so na borda
    assert collector.failures["/health"] == 3


def test_http_de_erro_degrada_sem_derrubar_as_outras_rotas():
    collector, events = collect(
        {
            "/health": {"status": "ok"},
            "/cockpit/summary": httpx.Response(500, text="boom"),
            "/trades/history": {"items": []},
        }
    )
    found = types_of(events)
    assert "ezio.boot" in found
    assert "ezio.degraded" in found
    assert collector.ezio_up is True  # o Ezio respondeu; uma rota falhou


def test_rota_que_se_recupera_emite_recovered():
    events = EventLog()
    responses: dict[str, object] = {"/cockpit/summary": httpx.Response(500, text="boom")}

    async def run():
        collector = make_collector(responses, events, [COCKPIT])
        await collector.poll_once()
        responses["/cockpit/summary"] = {"equity": 1}
        await collector.poll_once()

    asyncio.run(run())
    found = types_of(events)
    assert "ezio.recovered" in found


def test_ezio_fora_do_ar_nao_levanta():
    collector, events = collect(
        {"/health": httpx.ConnectError("conexao recusada")}, routes=[HEALTH]
    )
    assert collector.poll_count == 1
    assert collector.ezio_up is False
    degraded = next(e for e in events.recent(50) if e["event_type"] == "ezio.degraded")
    assert "ConnectError" in degraded["payload"]["error"]


def test_boot_novo_emite_restarted_e_rebaseia():
    events = EventLog()
    responses: dict[str, object] = {"/health": {"status": "ok", "boot_id": "b1"}}

    async def run():
        collector = make_collector(responses, events, [HEALTH])
        await collector.poll_once()
        responses["/health"] = {"status": "ok", "boot_id": "b2"}
        await collector.poll_once()
        await collector.poll_once()  # ciclo seguinte ja re-baseado
        return collector

    collector = asyncio.run(run())
    found = types_of(events)
    assert found.count("ezio.restarted") == 1
    assert collector.restarts_detected == 1
    assert found.count("ezio.boot") == 1  # boot e do processo, nao de cada re-base


def test_snapshot_id_e_o_mesmo_para_o_ciclo_inteiro():
    _, events = collect(
        {
            "/health": {"status": "ok"},
            "/cockpit/summary": {"equity": 1},
            "/trades/history": {"items": []},
        }
    )
    cycle = [e for e in events.recent(50) if e["seq"] <= 3]
    assert len({e["snapshot_id"] for e in cycle}) == 1


# ------------------------------------- alinhamento com o inventario da Fase 2


def test_conjunto_pollado_e_exatamente_o_snapshot_do_inventario():
    """O bridge polla o que o events.toml marca snapshot = true — nem mais, nem menos."""
    settings = load_settings()
    assert settings.config_errors == []
    declared = {
        key.split(" ", 1)[1]
        for key, entry in settings.inventory.items()
        if isinstance(entry, dict) and entry.get("snapshot") and key.startswith("GET ")
    }
    assert set(settings.snapshot_paths()) == declared
    assert set(settings.snapshot_paths()) == {
        "/health",
        "/health/details",
        "/cockpit/summary",
        "/trades/history",
        "/sentiment/alerts",
    }


def test_toda_rota_pollada_esta_declarada_no_inventario():
    settings = load_settings()
    for path in settings.snapshot_paths():
        assert settings.is_declared("GET", path), f"{path} nao esta no inventario do events.toml"


def test_allowlist_espelha_o_contrato_da_fase_2():
    settings = load_settings()
    assert sorted(settings.commands) == [
        "bob.ibkr.recover",
        "feedback",
        "task.cancel",
        "task.submit",
    ]
    assert settings.command_path == "/control/commands"


def test_vocabulario_usado_existe_no_inventario():
    settings = load_settings()
    assert settings.vocabulary["boot"] == "ezio.boot"
    assert settings.vocabulary["command_denied"] == "ezio.command.denied"
    assert settings.config_errors == []


# ---------------------------------------- contrato real da Fase 2 (so leitura)


def _fase_2() -> ast.Module | None:
    """AST de src/agent_server/control_endpoints.py, se ele ja existir.

    Leitura pura: se a Fase 2 ainda nao escreveu o arquivo, os testes que
    dependem dele sao pulados em vez de falharem.
    """
    if not CONTROL_ENDPOINTS.exists():
        return None
    return ast.parse(CONTROL_ENDPOINTS.read_text(encoding="utf-8"))


def _literal(node: ast.AST) -> Any:
    """Valor literal do no, entendendo `frozenset({...})`/`set(...)`/`tuple(...)`."""
    if isinstance(node, ast.Call) and getattr(node.func, "id", "") in {"frozenset", "set", "tuple"}:
        if len(node.args) == 1 and not node.keywords:
            return _literal(node.args[0])
        return None
    try:
        return ast.literal_eval(node)
    except ValueError:
        return None


def _assigned_names(tree: ast.Module, name: str) -> Any:
    """Valor da constante de modulo `name`, se ele for literal."""
    for node in tree.body:
        if isinstance(node, ast.AnnAssign) and getattr(node.target, "id", "") == name:
            return _literal(node.value)
        if isinstance(node, ast.Assign) and any(
            getattr(target, "id", "") == name for target in node.targets
        ):
            return _literal(node.value)
    return None


def test_allowlist_do_bridge_nao_diverge_da_do_ezio():
    """Se o Ezio recusar um kind por 403, o bridge nao deve aceita-lo em silencio."""
    tree = _fase_2()
    if tree is None:
        pytest.skip("Fase 2 ainda nao criou control_endpoints.py")
    allowed = _assigned_names(tree, "ALLOWED_COMMAND_KINDS")
    if allowed is None:
        pytest.skip("ALLOWED_COMMAND_KINDS ilegivel")
    assert set(load_settings().commands) == set(allowed)


def test_campos_do_bridge_cabem_no_ControlCommand_do_ezio():
    """O `extra="forbid"` da Fase 2 transforma campo a mais em 422."""
    tree = _fase_2()
    if tree is None:
        pytest.skip("Fase 2 ainda nao criou control_endpoints.py")
    model = next(
        (
            node
            for node in tree.body
            if isinstance(node, ast.ClassDef) and node.name == "ControlCommand"
        ),
        None,
    )
    if model is None:
        pytest.skip("ControlCommand nao encontrado")
    fields = {n.target.id for n in model.body if isinstance(n, ast.AnnAssign)}
    sent = CommandRouter.payload_for("task.submit", "id-1", {"a": 1}, "mike", 30)
    assert set(sent) <= fields, f"campos a mais viram 422: {set(sent) - fields}"
    assert {"command_id", "kind", "params", "issued_by"} <= fields


def test_caminho_do_comando_bate_com_a_fase_2():
    tree = _fase_2()
    if tree is None:
        pytest.skip("Fase 2 ainda nao criou control_endpoints.py")
    assert _assigned_names(tree, "CONTROL_COMMAND_PATH") == load_settings().command_path


def test_fase_2_nao_declara_env_de_token():
    """Sem segredo dos dois lados (12/09/2026): a rota do Ezio nao le env de token."""
    tree = _fase_2()
    if tree is None:
        pytest.skip("Fase 2 ainda nao criou control_endpoints.py")
    assert _assigned_names(tree, "BRIDGE_TOKEN_ENV") is None


def test_fronteira_dos_dois_lados_e_loopback():
    """O que substitui o token: o Ezio so aceita origem loopback e o bridge so
    abre socket em loopback. Se um dos dois lados relaxar, este teste cai."""
    tree = _fase_2()
    if tree is None:
        pytest.skip("Fase 2 ainda nao criou control_endpoints.py")
    hosts = _assigned_names(tree, "_LOOPBACK_HOSTS")
    if hosts is None:
        pytest.skip("_LOOPBACK_HOSTS ilegivel")
    assert HOST in hosts, f"o Ezio so aceita {sorted(hosts)}, mas o bridge binda em {HOST}"


def test_estados_do_ezio_tem_todos_traducao_no_bridge():
    tree = _fase_2()
    if tree is None:
        pytest.skip("Fase 2 ainda nao criou control_endpoints.py")
    for name in (
        "STATE_APPLIED",
        "STATE_REJECTED",
        "STATE_UNKNOWN",
        "STATE_DENIED",
        "STATE_IN_FLIGHT",
    ):
        value = _assigned_names(tree, name)
        assert value in EZIO_STATE_MAP, f"{name}={value!r} sem traducao no bridge"
