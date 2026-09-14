"""A justificativa do fail-open de autenticação de trading — verificada, não afirmada.

``_require_trading_auth`` (``src/agent_server/endpoints.py``) pula o segundo fator
quando ``SUPEREZIO_API_KEY`` não está configurada, ou com
``SUPEREZIO_OPEN_ACCESS=1``, e a docstring justificava o buraco com uma frase:

    "Live broker transmission remains independently frozen."

Frase assim envelhece mentindo — e mentiu. Até 11/09/2026 o gate era tautológico
(``f51_trade_gate`` gravava ``execution_freeze: False`` como único produtor, sem
leitura nenhuma): a frase era FALSA enquanto justificava a porta aberta.

Este arquivo é a sonda dessa frase. Ele deve FALHAR — não avisar — no dia em que
o gate deixar de ser real:

- ``execution_freeze`` voltar a ser literal escrito por construção;
- um ALLOW sem ``freeze_snapshot`` medido e datado voltar a ser aceito;
- o adapter voltar a confiar no metadata em vez de reamostrar o freeze.

Enquanto os testes desta classe passarem, o fail-open é defensável; quando um
deles ficar vermelho, o ``return ""`` de ``_require_trading_auth`` vira porta
aberta sem a única proteção que o justificava. É esse o recado do nome.
"""

from __future__ import annotations

import ast
import os
import socket
import sys
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import core.pipeline.f51_trade_gate as gate_module
from adapters.broker.ibkr_adapter import _low_level_gate_check
from agent_server import endpoints
from core.pipeline.f51_trade_gate import (
    TradeGateDecision,
    build_order_gate_metadata,
    evaluate_trade_gate,
    snapshot_execution_freeze,
)

_NEURAL_GATE = {
    "allowed": True,
    "model_id": "neural-test-v1",
    "as_of": "2026-09-11T12:00:00+00:00",
    "horizon": 1,
}
_DATED_SNAPSHOT = {
    "frozen": False,
    "sampled_at": "2026-09-11T12:00:00+00:00",
    "source": "env:F51_TRADING_EXECUTION_FREEZE=false",
}


def _request(path: str = "/trade/execute") -> SimpleNamespace:
    return SimpleNamespace(url=SimpleNamespace(path=path), headers={})


def _allow_decision(**evidence_overrides) -> TradeGateDecision:
    evidence = {"validated_ticker": "AAPL", "run_id": "run-1"}
    evidence.update(evidence_overrides)
    return TradeGateDecision(status="ALLOW", evidence=evidence)


def _bind(decision: TradeGateDecision) -> dict:
    return build_order_gate_metadata(
        decision,
        order_symbol="AAPL",
        approval_id="apr-1",
        consensus_decision="SUPPORT",
        neural_gate=_NEURAL_GATE,
    )


@pytest.fixture
def _unfrozen(monkeypatch):
    """Freeze explicitamente desligado e família SUPEREZIO_* limpa."""
    monkeypatch.setenv("F51_TRADING_EXECUTION_FREEZE", "false")
    monkeypatch.delenv("SUPEREZIO_LIVE_TRADING_DISABLED", raising=False)
    monkeypatch.delenv("SUPEREZIO_RESEARCH_PAPER_ONLY", raising=False)
    monkeypatch.delenv("SUPEREZIO_DAYTRADE_PAPER_ONLY", raising=False)


@pytest.fixture
def _frozen(monkeypatch):
    monkeypatch.setenv("F51_TRADING_EXECUTION_FREEZE", "true")
    monkeypatch.delenv("SUPEREZIO_LIVE_TRADING_DISABLED", raising=False)
    monkeypatch.delenv("SUPEREZIO_RESEARCH_PAPER_ONLY", raising=False)
    monkeypatch.delenv("SUPEREZIO_DAYTRADE_PAPER_ONLY", raising=False)


@pytest.fixture
def _fail_open_env(monkeypatch):
    """O ambiente exato em que as rotas de trading ficam sem segundo fator."""
    monkeypatch.setenv("SUPEREZIO_OPEN_ACCESS", "1")
    monkeypatch.delenv("SUPEREZIO_API_KEY", raising=False)
    monkeypatch.setattr(endpoints, "_TRADING_AUTH_BYPASS_LOGGED", set())


class _LogRecorder:
    """Substitui o logger do módulo para inspecionar evento, nível e campos."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, str, dict]] = []

    def __getattr__(self, level: str):
        def _record(event: str, **fields):
            self.calls.append((level, event, fields))

        return _record


# ═══════════════════════════════════════════════════════════════════════════
# A frase da docstring: "live broker transmission remains independently frozen"
# ═══════════════════════════════════════════════════════════════════════════


class TestFailOpenNeedsARealFreezeGate:
    """O fail-open da autenticação só é defensável enquanto ESTES testes passarem."""

    def test_the_fail_open_environment_really_skips_the_second_factor(self, _fail_open_env):
        # Sanidade: sem isto, os testes abaixo poderiam passar por outro motivo.
        assert endpoints._require_trading_auth(_request()) == ""

    def test_a_hand_built_allow_is_refused_in_the_environment_that_skips_auth(self, _fail_open_env):
        # O caso exato de 11/09/2026: ALLOW "limpo", sem leitura de freeze nenhuma.
        with pytest.raises(ValueError):
            _bind(_allow_decision())

    def test_an_allow_sampled_while_frozen_is_refused_in_the_environment_that_skips_auth(
        self, _fail_open_env
    ):
        frozen = dict(_DATED_SNAPSHOT, frozen=True, source="env:F51_TRADING_EXECUTION_FREEZE=true")
        with pytest.raises(ValueError):
            _bind(_allow_decision(freeze_snapshot=frozen))

    def test_a_snapshot_without_a_timestamp_is_refused_in_the_environment_that_skips_auth(
        self, _fail_open_env
    ):
        with pytest.raises(ValueError):
            _bind(_allow_decision(freeze_snapshot=dict(_DATED_SNAPSHOT, sampled_at="")))

    def test_the_freeze_is_measured_and_dated_in_the_environment_that_skips_auth(
        self, _fail_open_env, _frozen
    ):
        # A proteção real, medida no mesmo processo em que a auth é pulada.
        snapshot = snapshot_execution_freeze()
        assert snapshot["frozen"] is True
        assert datetime.fromisoformat(snapshot["sampled_at"])
        assert snapshot["source"]

    def test_the_gate_blocks_the_order_while_frozen_in_the_environment_that_skips_auth(
        self, _fail_open_env, _frozen
    ):
        decision = evaluate_trade_gate(
            message="comprar 10 AAPL", ticker="AAPL", qty=10, limit_price=150.0
        )
        assert decision.status == "BLOCK"
        assert decision.reason_code == "EXECUTION_FREEZE"
        assert decision.evidence["freeze_snapshot"]["frozen"] is True

    def test_the_adapter_refuses_a_literal_false_without_a_measurement(
        self, monkeypatch, _fail_open_env, _unfrozen
    ):
        # Última milha: `execution_freeze: False` sem `freeze_sampled_at` é
        # literal, não leitura — o adapter recusa antes de tocar na corretora.
        monkeypatch.setattr(socket, "socket", lambda *args, **kwargs: _OpenSocket())
        monkeypatch.setattr(gate_module, "is_journal_healthy", lambda *args, **kwargs: True)
        order = SimpleNamespace(
            symbol="AAPL",
            gate_metadata={
                "gate_status": "ALLOW",
                "gate_trace_id": "run-1",
                "validated_ticker": "AAPL",
                "journal_ready": True,
                "execution_freeze": False,
                "freeze_sampled_at": "",
                "pipeline_prepared": True,
                "adaptive_policy_applied": True,
                "approval_id": "apr-1",
                "consensus_decision": "SUPPORT",
                "neural_gate_status": "ALLOW",
                "neural_model_id": "neural-test-v1",
            },
        )
        assert _low_level_gate_check(order) is False

    def test_the_adapter_re_samples_a_freeze_flipped_after_the_decision(
        self, monkeypatch, _fail_open_env, _unfrozen
    ):
        monkeypatch.setattr(socket, "socket", lambda *args, **kwargs: _OpenSocket())
        monkeypatch.setattr(gate_module, "is_journal_healthy", lambda *args, **kwargs: True)
        monkeypatch.setenv("SUPEREZIO_LIVE_TRADING_DISABLED", "true")
        order = SimpleNamespace(
            symbol="AAPL",
            gate_metadata={
                "gate_status": "ALLOW",
                "gate_trace_id": "run-1",
                "validated_ticker": "AAPL",
                "journal_ready": True,
                "execution_freeze": False,
                "freeze_sampled_at": _DATED_SNAPSHOT["sampled_at"],
                "pipeline_prepared": True,
                "adaptive_policy_applied": True,
                "approval_id": "apr-1",
                "consensus_decision": "SUPPORT",
                "neural_gate_status": "ALLOW",
                "neural_model_id": "neural-test-v1",
            },
        )
        assert _low_level_gate_check(order) is False


class _OpenSocket:
    def settimeout(self, _timeout):
        return None

    def connect(self, _address):
        return None

    def close(self):
        return None


# ═══════════════════════════════════════════════════════════════════════════
# O detector estático da tautologia: o produtor não pode ESCREVER esse valor
# ═══════════════════════════════════════════════════════════════════════════


def _dict_bindings(source_path: Path, key: str) -> list[ast.expr]:
    """Todo `"<key>": <valor>` dentro de um dict literal no arquivo."""
    tree = ast.parse(source_path.read_text(encoding="utf-8"))
    bindings: list[ast.expr] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Dict):
            for dict_key, value in zip(node.keys, node.values):
                if isinstance(dict_key, ast.Constant) and dict_key.value == key:
                    bindings.append(value)
    return bindings


def _called_names(source_path: Path) -> set[str]:
    tree = ast.parse(source_path.read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            target = node.func
            if isinstance(target, ast.Attribute):
                names.add(target.attr)
            elif isinstance(target, ast.Name):
                names.add(target.id)
    return names


class TestFreezeIsNeverAConstructionLiteral:
    """Comportamento sozinho não pega tudo: um produtor que valida o snapshot e
    depois grava `False` na mão ainda passa nos testes de comportamento e volta
    a ser literal. Este teste lê o produtor."""

    def test_the_gate_module_still_binds_execution_freeze(self):
        # Sanidade: sem produtor, o teste abaixo passaria por vacuidade.
        assert _dict_bindings(Path(gate_module.__file__), "execution_freeze")

    def test_no_module_writes_execution_freeze_as_a_boolean_literal(self):
        for value in _dict_bindings(Path(gate_module.__file__), "execution_freeze"):
            assert not isinstance(value, ast.Constant), (
                "execution_freeze voltou a ser literal escrito por construção — "
                "é a tautologia de 11/09/2026. Ele tem de vir de "
                "snapshot_execution_freeze()['frozen']."
            )

    def test_the_gate_module_still_refuses_an_allow_without_the_snapshot(self):
        assert "_require_freeze_snapshot" in _called_names(Path(gate_module.__file__))

    def test_the_adapter_still_re_samples_the_freeze_at_connect(self):
        adapter_path = Path(gate_module.__file__).parents[2] / "adapters" / "broker"
        assert "is_execution_frozen" in _called_names(adapter_path / "ibkr_adapter.py")

    def test_a_producer_that_validates_then_writes_false_is_caught(self, tmp_path):
        # Prova do detector: o produtor "consertado" só na aparência, que valida
        # o snapshot e depois grava False na mão, ainda é pego por este teste.
        fake = tmp_path / "f51_trade_gate.py"
        fake.write_text(
            "def build():\n    return {'execution_freeze': False}\n",
            encoding="utf-8",
        )
        with pytest.raises(AssertionError):
            for value in _dict_bindings(fake, "execution_freeze"):
                assert not isinstance(value, ast.Constant)
        fake.write_text(
            "def build(snapshot):\n    return {'execution_freeze': snapshot['frozen']}\n",
            encoding="utf-8",
        )
        for value in _dict_bindings(fake, "execution_freeze"):
            assert not isinstance(value, ast.Constant)


# ═══════════════════════════════════════════════════════════════════════════
# O fail-open é decidido e anunciado, não mudo
# ═══════════════════════════════════════════════════════════════════════════


_AUTH_HELPERS = {"_require_trading_auth", "_require_td_ticket_auth"}


def _routes_calling_auth_helpers(source_path: Path) -> tuple[set[str], set[str]]:
    """(rotas com fator de chave de API, rotas com fator de ticket TD)."""
    tree = ast.parse(source_path.read_text(encoding="utf-8"))
    apikey_routes: set[str] = set()
    td_routes: set[str] = set()
    for node in tree.body:
        if not isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            continue
        route = None
        for decorator in node.decorator_list:
            if (
                isinstance(decorator, ast.Call)
                and isinstance(decorator.func, ast.Attribute)
                and decorator.func.attr in {"get", "post", "put", "delete", "patch"}
                and decorator.args
                and isinstance(decorator.args[0], ast.Constant)
            ):
                route = f"{decorator.func.attr.upper()} {decorator.args[0].value}"
        if route is None:
            continue
        called = {
            call.func.id
            for call in ast.walk(node)
            if isinstance(call, ast.Call) and isinstance(call.func, ast.Name)
        }
        if "_require_td_ticket_auth" in called:
            td_routes.add(route)
        elif "_require_trading_auth" in called:
            apikey_routes.add(route)
    return apikey_routes, td_routes


class TestTheBypassIsAnnouncedNotSilent:
    """`return ""` mudo vira banner de boot: motivo + onde está a proteção real."""

    def test_the_banner_inventory_matches_every_route_that_skips_the_second_factor(self):
        apikey_routes, td_routes = _routes_calling_auth_helpers(Path(endpoints.__file__))
        assert apikey_routes == set(endpoints._TRADING_AUTH_APIKEY_ROUTES)
        assert td_routes == set(endpoints._TRADING_AUTH_TD_ROUTES)

    def test_the_banner_names_the_reason_the_routes_and_the_real_protection(
        self, monkeypatch, _frozen
    ):
        monkeypatch.setenv("SUPEREZIO_OPEN_ACCESS", "0")
        monkeypatch.delenv("SUPEREZIO_API_KEY", raising=False)
        recorder = _LogRecorder()
        monkeypatch.setattr(endpoints, "logger", recorder)

        posture = endpoints.log_trading_auth_posture()

        level, event, fields = recorder.calls[-1]
        assert level == "warning"
        assert event == "trading_auth_second_factor_bypassed"
        assert fields["bypass_reason"] == "SUPEREZIO_API_KEY is unset"
        assert "POST /trade/execute" in fields["unauthenticated_routes"]
        # Sem chave de API as rotas TD não pulam: elas recusam com 503.
        assert "POST /trade/td-draft" in fields["refused_routes"]
        assert "freeze" in fields["real_protection"]
        assert "test_trading_failopen_freeze_anchor" in fields["probe"]
        assert posture["second_factor"] == "bypassed"

    def test_open_access_names_itself_and_opens_both_route_families(self, monkeypatch, _frozen):
        monkeypatch.setenv("SUPEREZIO_OPEN_ACCESS", "1")
        monkeypatch.delenv("SUPEREZIO_API_KEY", raising=False)
        recorder = _LogRecorder()
        monkeypatch.setattr(endpoints, "logger", recorder)

        endpoints.log_trading_auth_posture()

        _level, _event, fields = recorder.calls[-1]
        assert fields["bypass_reason"] == "SUPEREZIO_OPEN_ACCESS=1"
        assert "POST /trade/td-draft" in fields["unauthenticated_routes"]
        assert fields["refused_routes"] == []

    def test_the_banner_escalates_to_critical_when_the_bypass_is_unfrozen(
        self, monkeypatch, _unfrozen
    ):
        monkeypatch.setenv("SUPEREZIO_OPEN_ACCESS", "1")
        recorder = _LogRecorder()
        monkeypatch.setattr(endpoints, "logger", recorder)

        endpoints.log_trading_auth_posture()

        level, event, fields = recorder.calls[-1]
        assert level == "critical"
        assert event == "trading_auth_second_factor_bypassed_unfrozen"
        assert fields["execution_frozen"] is False

    def test_the_banner_measures_the_freeze_instead_of_assuming_it(self, monkeypatch, _frozen):
        monkeypatch.setenv("SUPEREZIO_OPEN_ACCESS", "1")
        recorder = _LogRecorder()
        monkeypatch.setattr(endpoints, "logger", recorder)

        posture = endpoints.log_trading_auth_posture()

        measured = snapshot_execution_freeze()
        assert posture["execution_frozen"] is measured["frozen"]
        assert posture["freeze_source"] == measured["source"]
        posture_dt = datetime.fromisoformat(posture["freeze_sampled_at"])
        measured_dt = datetime.fromisoformat(measured["sampled_at"])
        assert abs((posture_dt - measured_dt).total_seconds()) < 2.0

    def test_the_banner_reports_unknown_rather_than_frozen_when_the_gate_is_unreadable(
        self, monkeypatch
    ):
        def _explode():
            raise RuntimeError("gate unreadable")

        monkeypatch.setattr(gate_module, "snapshot_execution_freeze", _explode)
        monkeypatch.setenv("SUPEREZIO_OPEN_ACCESS", "1")
        recorder = _LogRecorder()
        monkeypatch.setattr(endpoints, "logger", recorder)

        posture = endpoints.log_trading_auth_posture()

        level, _event, fields = recorder.calls[-1]
        assert level == "critical"
        assert posture["execution_frozen"] is None
        assert fields["freeze_source"].startswith("unreadable:")
        assert "gate unreadable" in fields["freeze_source"]

    def test_the_first_bypassed_request_is_logged_and_the_next_one_is_not_repeated(
        self, monkeypatch, _fail_open_env, _frozen
    ):
        recorder = _LogRecorder()
        monkeypatch.setattr(endpoints, "logger", recorder)

        assert endpoints._require_trading_auth(_request("/paper/approve/req-1")) == ""
        assert endpoints._require_trading_auth(_request("/paper/approve/req-2")) == ""

        events = [(level, event, fields) for level, event, fields in recorder.calls]
        assert [event for _l, event, _f in events] == [
            "trading_auth_bypassed",
            "trading_auth_bypassed",
        ]
        assert [level for level, _e, _f in events] == ["warning", "debug"]
        assert events[0][2]["path"] == "/paper/approve/req-1"
        assert events[0][2]["reason"] == "SUPEREZIO_OPEN_ACCESS=1"
        assert "freeze" in events[0][2]["real_protection"]

    def test_the_second_factor_is_still_enforced_when_the_api_key_is_configured(self, monkeypatch):
        # O banner não pode virar desculpa para afrouxar o caminho autenticado.
        monkeypatch.setenv("SUPEREZIO_OPEN_ACCESS", "0")
        monkeypatch.setenv("SUPEREZIO_API_KEY", "configured-for-test")
        recorder = _LogRecorder()
        monkeypatch.setattr(endpoints, "logger", recorder)

        posture = endpoints.log_trading_auth_posture()

        level, event, fields = recorder.calls[-1]
        assert level == "info"
        assert event == "trading_auth_posture_enforced"
        assert posture["second_factor"] == "enforced"
        assert fields["unauthenticated_routes"] == []
        assert endpoint_raises_401(_request())

    def test_the_enforced_bypass_helper_is_not_used_when_a_key_is_configured(self, monkeypatch):
        monkeypatch.setenv("SUPEREZIO_OPEN_ACCESS", "0")
        monkeypatch.setenv("SUPEREZIO_API_KEY", "configured-for-test")
        assert endpoints._trading_auth_bypass_reason() == ""


def endpoint_raises_401(request: SimpleNamespace) -> bool:
    from fastapi import HTTPException

    try:
        endpoints._require_trading_auth(request)
    except HTTPException as exc:
        return exc.status_code == 401
    return False
