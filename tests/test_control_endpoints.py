"""Contrato do plano de controle MIKE->Ezio (Fase 2 do bridge).

Cobre o que a spec exige, nesta ordem de importancia:

* ``kind`` fora da allowlist devolve 403 (default-deny);
* ``kind`` proibido (freeze, env, ``/trade/manual/*``, ``/trade/execute``,
  ``/paper/approve|reject``, ``/evidence/*``, shell/Python generico) devolve 403
  **mesmo se alguem o injetar na allowlist** — a checagem roda antes;
* comando valido e idempotente nao aplica duas vezes;
* "applied" so sai quando o efeito foi confirmado — comando em voo devolve
  ``unknown``, handler que estoura devolve ``unknown``, broker que nao
  reconecta devolve ``rejected``;
* ``bridge/events.toml`` classifica toda rota de ``src/agent_server/`` — rota
  nova sem classificacao deixa o MIKE cego e quebra este arquivo (§9 do plano).

Nao importa ``agent_server.main``: o app e montado aqui com o router isolado,
o que mantem o teste barato e imune a edicao de outros agentes no main.py.
"""

from __future__ import annotations

import asyncio
import re
import tomllib
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from agent_server import control_endpoints as cp
from core.pipeline.task_queue import get_task_queue

ROOT = Path(__file__).resolve().parents[1]
EVENTS_TOML = ROOT / "bridge" / "events.toml"

# ── Fixtures ────────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _isolated_control_state():
    """Ledger limpo e fila de tasks zerada por teste.

    Nao ha credencial a configurar (decisao de 12/09/2026): a fronteira do
    plano de controle e loopback + allowlist default-deny, nao token.
    """
    cp.reset_command_ledger_for_test()
    queue = get_task_queue()
    queue._active.clear()
    queue._by_session.clear()
    yield
    cp.reset_command_ledger_for_test()
    queue._active.clear()
    queue._by_session.clear()


@pytest.fixture
def app() -> FastAPI:
    application = FastAPI()
    application.router.routes.extend(cp.router.routes)
    return application


@pytest.fixture
def client(app: FastAPI) -> TestClient:
    # O bridge real e um cliente loopback (bridge/config.py fixa 127.0.0.1).
    # Sem o client= explicito o TestClient se apresenta como "testclient", que
    # a fronteira recusa — e o teste mediria outra coisa.
    return TestClient(app, client=("127.0.0.1", 12345))


# ── Helpers ─────────────────────────────────────────────────────────────────


def _body(kind: str, *, command_id: str = "cmd-0001", params: dict | None = None, **extra: Any):
    return {
        "command_id": command_id,
        "kind": kind,
        "params": params or {},
        "issued_by": "mike",
        "ttl_s": 60,
        **extra,
    }


def _post(
    client: TestClient,
    kind: str,
    *,
    command_id: str = "cmd-0001",
    params: dict | None = None,
    **extra: Any,
):
    return client.post(
        cp.CONTROL_COMMAND_PATH,
        json=_body(kind, command_id=command_id, params=params, **extra),
    )


# ── Allowlist e default-deny ────────────────────────────────────────────────


def test_allowlist_is_exactly_the_four_approved_kinds():
    assert cp.ALLOWED_COMMAND_KINDS == {
        "task.submit",
        "task.cancel",
        "feedback",
        "bob.ibkr.recover",
    }
    # A tabela de handlers nao pode divergir da allowlist (o import ja asserta;
    # aqui a garantia fica visivel para quem revisa a lista).
    assert set(cp._HANDLERS) == cp.ALLOWED_COMMAND_KINDS


def test_route_is_mounted_at_the_contract_path_without_router_prefix():
    """main.py registra com ``routes.extend`` — um prefix de router seria perdido."""
    assert [route.path for route in cp.router.routes] == [cp.CONTROL_COMMAND_PATH]
    assert cp.CONTROL_COMMAND_PATH == "/control/commands"


@pytest.mark.parametrize(
    "kind",
    [
        "trade.submit",
        "market.buy",
        "task.submit_extra",
        "TASK.SUBMIT",
        "task/cancel",
    ],
)
def test_kind_outside_allowlist_is_403(client, kind):
    response = _post(client, kind)

    assert response.status_code == 403, response.text
    payload = response.json()
    assert payload["state"] == cp.STATE_DENIED
    assert payload["applied"] is False
    assert payload["detail"]["code"] == "kind_not_allowed"
    assert cp.command_ledger_size() == 0, "comando negado nao pode entrar no ledger"


@pytest.mark.parametrize(
    "kind",
    [
        "freeze",
        "freeze.set",
        "freeze.set.v2",
        "env.set",
        "env.write",
        "environment.set",
        "trade.manual.entered",
        "/trade/manual/abc123/entered",
        "/trade/manual/abc123/approve/xyz",
        "trade.execute",
        "/trade/execute",
        "paper.approve",
        "paper.reject",
        "/paper/approve/req-1",
        "/paper/reject/req-1",
        "evidence.delete",
        "/evidence/run-1/decision.json",
        "shell.run",
        "subprocess.exec",
        "python.eval",
        "eval",
    ],
)
def test_forbidden_kind_is_403_even_if_someone_allowlists_it(client, monkeypatch, kind):
    """A trava nao pode depender de ninguem manter a allowlist limpa."""
    monkeypatch.setattr(cp, "ALLOWED_COMMAND_KINDS", cp.ALLOWED_COMMAND_KINDS | {kind})
    monkeypatch.setitem(cp._HANDLERS, kind, lambda *_: None)  # nem com handler ligado

    response = _post(client, kind)

    assert response.status_code == 403, response.text
    payload = response.json()
    assert payload["state"] == cp.STATE_DENIED
    assert payload["applied"] is False
    assert payload["detail"]["code"] in {"forbidden_kind", "forbidden_kind_family"}


def test_unknown_envelope_fields_are_rejected(client):
    payload = _body("task.cancel", params={"run_id": "r1"})
    payload["route"] = "/trade/execute"  # campo extra nao pode ser aceito

    response = client.post(cp.CONTROL_COMMAND_PATH, json=payload)

    assert response.status_code == 422


@pytest.mark.parametrize(
    "envelope",
    [
        _body(""),  # kind vazio
        _body("feedback", command_id=""),  # command_id vazio
        _body("feedback", issued_by="x"),  # issued_by curto demais
        {k: v for k, v in _body("feedback").items() if k != "issued_by"},  # sem issued_by
    ],
)
def test_malformed_envelope_is_422_and_changes_nothing(client, envelope):
    response = client.post(cp.CONTROL_COMMAND_PATH, json=envelope)

    assert response.status_code == 422, response.text
    assert cp.command_ledger_size() == 0


# ── Fronteira: loopback, sem credencial (decisao de 12/09/2026) ─────────────
# O segredo foi removido por decisao de projeto: o bridge e o unico cliente,
# roda na mesma maquina, e a fronteira e TOPOLOGICA (bind em 127.0.0.1 mais
# allowlist default-deny). Nao ha token a vazar, rotacionar ou esquecer.
# O que estes testes guardam e a propriedade que sobrou: origem externa nao
# executa e nao registra.


def test_control_plane_accepts_loopback_without_credential(client):
    """Origem loopback passa sem token nenhum — nao existe mais 'nao configurado'."""
    response = _post(client, "feedback", params={"msg_id": "m1", "rating": 5})

    assert response.status_code not in (401, 503), response.text


def test_control_plane_refuses_non_loopback_origin(app: FastAPI):
    """Trocar o bind por engano nao pode abrir a rota sozinho."""
    externo = TestClient(app, client=("203.0.113.7", 44444))

    response = _post(externo, "feedback", params={"msg_id": "m1", "rating": 5})

    assert response.status_code == 403
    assert response.json()["detail"]["code"].startswith("origem_nao_loopback")
    assert cp.command_ledger_size() == 0, "origem externa nao pode executar nem registrar"


# ── Idempotencia ────────────────────────────────────────────────────────────


@pytest.fixture
def feedback_sink(monkeypatch, tmp_path):
    """save_feedback falso que conta chamadas e grava um arquivo de verdade."""
    calls: list[dict[str, Any]] = []
    path = tmp_path / "feedback.jsonl"

    def fake_save_feedback(msg_id: str, rating: int, *, comment: str = "", trace=None):
        calls.append({"msg_id": msg_id, "rating": rating, "comment": comment})
        with path.open("a", encoding="utf-8") as handle:
            handle.write(f"{msg_id}:{rating}\n")
        return path

    import core.ml.feedback as feedback_module

    monkeypatch.setattr(feedback_module, "save_feedback", fake_save_feedback)
    return calls


def test_valid_idempotent_command_applies_exactly_once(client, feedback_sink):
    params = {"msg_id": "msg-1", "rating": 5, "comment": "util"}

    first = _post(client, "feedback", command_id="cmd-dup", params=params)
    second = _post(client, "feedback", command_id="cmd-dup", params=params)

    assert first.status_code == 200, first.text
    assert first.json()["state"] == cp.STATE_APPLIED
    assert first.json()["applied"] is True
    assert first.json()["idempotent_replay"] is False

    assert len(feedback_sink) == 1, "o mesmo command_id nao pode aplicar duas vezes"
    assert second.status_code == 200
    assert second.json() == {**first.json(), "idempotent_replay": True}


def test_distinct_command_ids_apply_twice(client, feedback_sink):
    params = {"msg_id": "msg-1", "rating": 5}

    first = _post(client, "feedback", command_id="cmd-a", params=params)
    second = _post(client, "feedback", command_id="cmd-b", params=params)

    assert (first.status_code, second.status_code) == (200, 200)
    assert len(feedback_sink) == 2


def test_command_id_expires_after_ttl_and_then_runs_again(client, monkeypatch, feedback_sink):
    clock = [1_000.0]
    monkeypatch.setattr(cp, "_now", lambda: clock[0])
    params = {"msg_id": "msg-ttl", "rating": 4}

    first = _post(client, "feedback", command_id="cmd-ttl", params=params, ttl_s=5)
    clock[0] += 1.0
    replay = _post(client, "feedback", command_id="cmd-ttl", params=params, ttl_s=5)
    clock[0] += 30.0
    after_ttl = _post(client, "feedback", command_id="cmd-ttl", params=params, ttl_s=5)

    assert first.json()["idempotent_replay"] is False
    assert replay.json()["idempotent_replay"] is True
    assert after_ttl.json()["idempotent_replay"] is False, "passado o ttl_s e comando novo"
    assert len(feedback_sink) == 2


# ── "applied" so com confirmacao ────────────────────────────────────────────


def test_task_submit_without_executor_is_rejected_and_leaves_no_phantom_task(app, client):
    response = _post(
        client,
        "task.submit",
        params={"message": "resuma a carteira", "session_id": "bridge:mike"},
    )

    assert response.status_code == 409, response.text
    payload = response.json()
    assert payload["state"] == cp.STATE_REJECTED
    assert payload["applied"] is False
    assert payload["detail"]["code"] == "executor_not_wired"
    assert get_task_queue().active_count == 0, "task enfileirada sem executor teria que rolar"


def test_task_submit_is_applied_when_the_executor_takes_it(app, client):
    seen: list[tuple[str, str, str]] = []
    app.state.task_executor = lambda run_id, message, session_id: seen.append(
        (run_id, message, session_id)
    )

    response = _post(
        client, "task.submit", params={"message": "oi bob", "session_id": "bridge:mike"}
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["state"] == cp.STATE_APPLIED
    assert payload["applied"] is True
    run_id = payload["detail"]["run_id"]
    assert seen == [(run_id, "oi bob", "bridge:mike")]
    assert get_task_queue().status(run_id)["status"] == "running"


def test_task_submit_is_unknown_when_the_executor_blows_up(app, client):
    def boom(_run_id, _message, _session_id):
        raise RuntimeError("pipeline offline")

    app.state.task_executor = boom

    response = _post(
        client, "task.submit", params={"message": "oi bob", "session_id": "bridge:mike"}
    )

    assert response.status_code == 500, response.text
    payload = response.json()
    assert payload["state"] == cp.STATE_UNKNOWN
    assert payload["applied"] is False, "execucao nao confirmada nunca vira applied"
    assert payload["retryable"] is True
    assert payload["detail"]["code"] == "executor_failed"


def test_task_cancel_is_rejected_when_run_id_is_not_active(client):
    response = _post(client, "task.cancel", params={"run_id": "nao-existe"})

    assert response.status_code == 409, response.text
    payload = response.json()
    assert payload["state"] == cp.STATE_REJECTED
    assert payload["applied"] is False
    assert payload["detail"]["code"] == "run_id_not_active"


def test_task_cancel_is_applied_when_the_task_really_stops(client):
    queue = get_task_queue()
    task = queue.submit(message="rodando", session_id="sess-cancel")

    response = _post(client, "task.cancel", params={"run_id": task.run_id})

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["state"] == cp.STATE_APPLIED
    assert payload["detail"] == {"run_id": task.run_id, "cancelled": True}
    assert queue.status(task.run_id)["status"] == "not_found"


def test_feedback_is_unknown_when_the_write_is_not_confirmed(client, monkeypatch, tmp_path):
    import core.ml.feedback as feedback_module

    monkeypatch.setattr(
        feedback_module, "save_feedback", lambda *_a, **_k: tmp_path / "nao-existe.jsonl"
    )

    response = _post(client, "feedback", params={"msg_id": "m1", "rating": 5})

    assert response.status_code == 500, response.text
    assert response.json()["state"] == cp.STATE_UNKNOWN
    assert response.json()["applied"] is False


class _FakeBroker:
    def __init__(self, result: dict[str, Any]):
        self._result = result
        self.calls = 0

    def force_recovery_attempt(self) -> dict[str, Any]:
        self.calls += 1
        return self._result


def test_bob_ibkr_recover_is_applied_only_when_the_broker_confirms(app, client, monkeypatch):
    service = _FakeBroker(
        {"success": True, "error": None, "failures_reset": 3, "timestamp": "2026-09-11T00:00:00Z"}
    )
    monkeypatch.setattr("adapters.broker.ibkr_service.get_ibkr_service", lambda: service)

    response = _post(client, "bob.ibkr.recover")

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["state"] == cp.STATE_APPLIED
    assert payload["detail"]["success"] is True
    assert service.calls == 1


def test_bob_ibkr_recover_is_rejected_when_the_broker_stays_offline(app, client, monkeypatch):
    service = _FakeBroker(
        {
            "success": False,
            "error": "TWS offline",
            "failures_reset": 0,
            "timestamp": "2026-09-11T00:00:00Z",
        }
    )
    monkeypatch.setattr("adapters.broker.ibkr_service.get_ibkr_service", lambda: service)

    response = _post(client, "bob.ibkr.recover")

    assert response.status_code == 409, response.text
    payload = response.json()
    assert payload["state"] == cp.STATE_REJECTED
    assert payload["applied"] is False, "tentativa sem reconexao nao e 'aplicado'"
    assert payload["detail"]["error"] == "TWS offline"


def test_bob_ibkr_recover_is_unknown_when_the_service_answers_nothing(app, client, monkeypatch):
    service = _FakeBroker({"unexpected": "shape"})
    monkeypatch.setattr("adapters.broker.ibkr_service.get_ibkr_service", lambda: service)

    response = _post(client, "bob.ibkr.recover")

    assert response.status_code == 500, response.text
    assert response.json()["state"] == cp.STATE_UNKNOWN
    assert response.json()["applied"] is False


def test_handler_crash_is_unknown_and_never_applied(client, monkeypatch):
    async def explode(_ctx, _params):
        raise RuntimeError("disco cheio")

    monkeypatch.setitem(cp._HANDLERS, "feedback", explode)

    response = _post(client, "feedback", params={"msg_id": "m1", "rating": 5})

    assert response.status_code == 500, response.text
    payload = response.json()
    assert payload["state"] == cp.STATE_UNKNOWN
    assert payload["applied"] is False
    assert payload["detail"]["code"] == "handler_error"


@pytest.mark.asyncio
async def test_command_in_flight_is_unknown_for_the_same_command_id(app, monkeypatch):
    started = asyncio.Event()
    gate = asyncio.Event()
    calls: list[str] = []

    async def slow_handler(ctx, _params):
        calls.append(ctx.command_id)
        started.set()
        await gate.wait()
        return cp.applied({"done": True})

    monkeypatch.setitem(cp._HANDLERS, "feedback", slow_handler)
    body = _body("feedback", command_id="cmd-in-flight")

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as async_client:
        first = asyncio.create_task(async_client.post(cp.CONTROL_COMMAND_PATH, json=body))
        await asyncio.wait_for(started.wait(), timeout=5.0)
        in_flight = await async_client.post(cp.CONTROL_COMMAND_PATH, json=body)
        gate.set()
        settled = await asyncio.wait_for(first, timeout=5.0)

    assert in_flight.status_code == cp.HTTP_IN_FLIGHT
    assert in_flight.json()["state"] == cp.STATE_UNKNOWN
    assert in_flight.json()["applied"] is False, "comando em voo nunca e 'aplicado'"
    assert settled.status_code == 200
    assert settled.json()["state"] == cp.STATE_APPLIED
    assert calls == ["cmd-in-flight"], "reenvio em voo nao pode executar de novo"


# ── bridge/events.toml (§9: rota nova sem classificacao = MIKE cego) ─────────

_ROUTE_DECORATOR = re.compile(
    r"""@\w+\.(api_route|get|post|put|delete|patch)\(\s*
        (?:"([^"]+)"|'([^']+)'|([A-Za-z_][A-Za-z0-9_]*))
        \s*(?:,\s*methods\s*=\s*\[([^\]]*)\])?""",
    re.VERBOSE,
)
_STRING_CONSTANT = re.compile(r"""^([A-Za-z_][A-Za-z0-9_]*)\s*=\s*["']([^"']+)["']""", re.MULTILINE)

_FAMILY_SAMPLES = {
    "freeze": "freeze.set",
    "env": "env.write",
    "trade/manual": "/trade/manual/t1/entered",
    "trade/execute": "trade.execute",
    "paper/approve|reject": "paper.approve",
    "evidence": "/evidence/run-1/decision.json",
    "shell|exec|eval|python|subprocess": "python.eval",
}


def _events_toml() -> dict[str, Any]:
    assert EVENTS_TOML.is_file(), f"inventario de rotas ausente: {EVENTS_TOML}"
    with EVENTS_TOML.open("rb") as handle:
        return tomllib.load(handle)


def _routes_in_source(relative_path: str) -> dict[str, str]:
    text = (ROOT / relative_path).read_text(encoding="utf-8")
    constants = dict(_STRING_CONSTANT.findall(text))
    routes: dict[str, str] = {}
    for match in _ROUTE_DECORATOR.finditer(text):
        path = match.group(2) or match.group(3) or constants.get(match.group(4) or "")
        assert path, f"path de rota nao resolvido em {relative_path}: {match.group(0)[:60]}"
        line = text[: match.start()].count("\n") + 1
        methods = (
            re.findall(r"""["'](\w+)["']""", match.group(5) or "")
            if match.group(1) == "api_route"
            else [match.group(1)]
        )
        for method in methods:
            routes[f"{method.upper()} {path}"] = f"{relative_path}:{line}"
    return routes


def test_events_toml_classifies_every_route_of_the_server():
    document = _events_toml()
    declared = document["routes"]
    in_code: dict[str, str] = {}
    for relative_path in document["meta"]["route_sources"]:
        in_code.update(_routes_in_source(relative_path))

    missing = sorted(set(in_code) - set(declared))
    assert not missing, (
        "rota nova sem classificacao em bridge/events.toml — sem isso o MIKE fica cego:\n"
        + "\n".join(
            f'  "{key}" = {{ class = "?", snapshot = false, mutable = false, '
            f'bridge_calls = false, emits = [], source = "{in_code[key]}", note = "" }}'
            for key in missing
        )
    )
    stale = sorted(set(declared) - set(in_code))
    assert not stale, f"events.toml classifica rota que nao existe mais: {stale}"


def test_events_toml_entries_are_well_formed():
    document = _events_toml()
    declared_events = set(document["events"])
    known_classes = set(document["meta"]["classes"])
    sources = set(document["meta"]["route_sources"])

    assert document["meta"]["default_policy"] == "unclassified"
    for key, entry in document["routes"].items():
        assert entry["class"] in known_classes, key
        assert isinstance(entry["snapshot"], bool), key
        assert isinstance(entry["mutable"], bool), key
        assert isinstance(entry["bridge_calls"], bool), key
        assert set(entry["emits"]) <= declared_events, f"{key} emite evento nao declarado"
        assert entry["source"].split(":")[0] in sources, key
        assert entry["note"].strip(), f"{key} sem nota"
    assert set(_FAMILY_SAMPLES) == set(document["commands"]["forbidden_families"])
    for sample in _FAMILY_SAMPLES.values():
        assert cp._forbidden_kind(sample), f"familia proibida nao barrada no codigo: {sample}"


def test_events_toml_command_contract_matches_the_code():
    document = _events_toml()

    assert document["commands"]["route"] == f"POST {cp.CONTROL_COMMAND_PATH}"
    assert document["commands"]["policy"] == "default-deny"
    assert document["commands"]["allowed"] == sorted(cp.ALLOWED_COMMAND_KINDS)

    command_route = document["routes"]["POST /control/commands"]
    assert command_route["class"] == "command"
    assert command_route["bridge_calls"] is True
    assert command_route["mutable"] is True

    # As rotas que o MIKE so pode tocar via /control/commands nao podem estar
    # marcadas como chamaveis pelo bridge.
    for key in (
        "POST /trade/execute",
        "POST /trade/td-draft",
        "POST /paper/approve/{request_id}",
        "POST /paper/reject/{request_id}",
        "GET /evidence",
        "GET /bob/heal",
        "POST /auth/register",
        "POST /auth/login",
    ):
        assert document["routes"][key]["class"] == "deny", key
        assert document["routes"][key]["bridge_calls"] is False, key
