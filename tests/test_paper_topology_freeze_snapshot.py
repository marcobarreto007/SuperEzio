"""Fase 1 do plano MIKE↔Ezio: a trava mede, e o paper é topologia.

Estes testes FALHAM no código anterior à Fase 1, que é o ponto deles:

- `execution_freeze` era literal `False` em `build_order_gate_metadata`
  (f51_trade_gate.py:423), então um ALLOW sem leitura de freeze nenhuma era
  aceito, e a checagem do adapter (`ibkr_adapter.py:92`) era inalcançável.
- `assert_paper_topology` não existia: a porta vinha de `os.getenv` no ponto
  de uso, e trocar `IBKR_PORT` para 7496 virava live sem nenhum guarda.
"""

from __future__ import annotations

import os
import socket
import sys
from datetime import datetime
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from adapters.broker.ibkr_adapter import InteractiveBrokersAdapter, _low_level_gate_check
from core.config.settings import (
    PAPER_IBKR_PORTS,
    PaperTopologyError,
    Settings,
    assert_paper_topology,
)
from core.pipeline.f51_trade_gate import (
    TradeGateDecision,
    build_order_gate_metadata,
    evaluate_trade_gate,
)

_NEURAL_GATE = {
    "allowed": True,
    "model_id": "neural-test-v1",
    "as_of": "2026-07-19T12:00:00+00:00",
    "horizon": 1,
}

_SAMPLED_AT = "2026-09-11T12:00:00+00:00"
_FREEZE_OFF_SNAPSHOT = {
    "frozen": False,
    "sampled_at": _SAMPLED_AT,
    "source": "env:F51_TRADING_EXECUTION_FREEZE=false",
}


def _allow_decision(**evidence_overrides) -> TradeGateDecision:
    evidence = {"validated_ticker": "AAPL", "run_id": "run-1"}
    evidence.update(evidence_overrides)
    return TradeGateDecision(status="ALLOW", evidence=evidence)


def _valid_gate_metadata(**overrides) -> dict:
    """Metadata completa como o produtor real a emite (medida + timestamp)."""
    metadata = {
        "gate_status": "ALLOW",
        "gate_trace_id": "run-1",
        "validated_ticker": "AAPL",
        "journal_ready": True,
        "execution_freeze": False,
        "freeze_sampled_at": _SAMPLED_AT,
        "freeze_source": _FREEZE_OFF_SNAPSHOT["source"],
        "pipeline_prepared": True,
        "adaptive_policy_applied": True,
        "approval_id": "apr-1",
        "consensus_decision": "SUPPORT",
        "neural_gate_status": "ALLOW",
        "neural_model_id": "neural-test-v1",
    }
    metadata.update(overrides)
    return metadata


def _order(metadata: dict) -> SimpleNamespace:
    return SimpleNamespace(symbol="AAPL", gate_metadata=metadata)


class _OpenSocket:
    def settimeout(self, _timeout):
        return None

    def connect(self, _address):
        return None

    def close(self):
        return None


@pytest.fixture
def _freeze_off(monkeypatch):
    """Freeze explicitamente desligado, família SUPEREZIO_* limpa."""
    monkeypatch.setenv("F51_TRADING_EXECUTION_FREEZE", "false")
    monkeypatch.delenv("SUPEREZIO_LIVE_TRADING_DISABLED", raising=False)
    monkeypatch.delenv("SUPEREZIO_RESEARCH_PAPER_ONLY", raising=False)
    monkeypatch.delenv("SUPEREZIO_DAYTRADE_PAPER_ONLY", raising=False)


@pytest.fixture
def _reachable_environment(monkeypatch, _freeze_off):
    """Neutraliza tudo que NÃO é objeto do teste (socket aberto, journal
    saudável), para que a decisão do low-level gate venha só do que se testa."""
    monkeypatch.setattr(socket, "socket", lambda *args, **kwargs: _OpenSocket())

    import core.pipeline.f51_trade_gate as gate_module

    monkeypatch.setattr(gate_module, "is_journal_healthy", lambda *args, **kwargs: True)


@pytest.fixture
def _gate_reaches_allow(monkeypatch, _freeze_off):
    """Faz evaluate_trade_gate chegar ao ALLOW sem depender do mundo externo."""
    monkeypatch.setenv("IBKR_PORT", "7497")

    import core.bob_consciousness as consciousness
    import core.pipeline.f51_trade_gate as gate_module

    class _FakeBody:
        def check_man_at_work_guard(self, operation="trading"):
            return True, ""

    monkeypatch.setattr(consciousness, "get_bobs_body", lambda: _FakeBody())
    monkeypatch.setattr(
        gate_module, "resolve_and_validate_ticker", lambda symbol: (symbol, 150.0, None)
    )
    monkeypatch.setattr(gate_module, "is_ibkr_connectable", lambda: True)
    monkeypatch.setattr(gate_module, "is_journal_healthy", lambda *args, **kwargs: True)


class TestFreezeIsMeasuredNotLiteral:
    """§3 do plano: nenhuma das três fontes escreve False por construção."""

    def test_allow_without_freeze_snapshot_is_refused(self):
        # O caso exato do achado: ALLOW "limpo", sem leitura de freeze.
        with pytest.raises(ValueError):
            build_order_gate_metadata(
                _allow_decision(),
                order_symbol="AAPL",
                approval_id="apr-1",
                consensus_decision="SUPPORT",
                neural_gate=_NEURAL_GATE,
            )

    def test_allow_sampled_while_frozen_is_refused(self):
        frozen = dict(
            _FREEZE_OFF_SNAPSHOT, frozen=True, source="env:F51_TRADING_EXECUTION_FREEZE=true"
        )
        with pytest.raises(ValueError):
            build_order_gate_metadata(
                _allow_decision(freeze_snapshot=frozen),
                order_symbol="AAPL",
                approval_id="apr-1",
                consensus_decision="SUPPORT",
                neural_gate=_NEURAL_GATE,
            )

    def test_snapshot_without_timestamp_is_refused(self):
        with pytest.raises(ValueError):
            build_order_gate_metadata(
                _allow_decision(freeze_snapshot={"frozen": False, "sampled_at": "", "source": "x"}),
                order_symbol="AAPL",
                approval_id="apr-1",
                consensus_decision="SUPPORT",
                neural_gate=_NEURAL_GATE,
            )

    def test_gate_stamps_the_freeze_reading_on_allow(self, _gate_reaches_allow):
        decision = evaluate_trade_gate(
            message="comprar 10 AAPL",
            ticker="AAPL",
            qty=10,
            limit_price=150.0,
            run_id="run-1",
        )
        assert decision.status == "ALLOW"
        snapshot = decision.evidence["freeze_snapshot"]
        assert snapshot["frozen"] is False
        assert datetime.fromisoformat(snapshot["sampled_at"])
        assert snapshot["source"]

    def test_gate_stamps_a_frozen_reading_when_frozen(self, monkeypatch, _gate_reaches_allow):
        monkeypatch.setenv("F51_TRADING_EXECUTION_FREEZE", "true")
        decision = evaluate_trade_gate(
            message="comprar 10 AAPL", ticker="AAPL", qty=10, limit_price=150.0
        )
        assert decision.reason_code == "EXECUTION_FREEZE"
        assert decision.evidence["freeze_snapshot"]["frozen"] is True

    def test_metadata_copies_the_measurement_taken_by_the_gate(self, _gate_reaches_allow):
        decision = evaluate_trade_gate(
            message="comprar 10 AAPL",
            ticker="AAPL",
            qty=10,
            limit_price=150.0,
            run_id="run-1",
        )
        metadata = build_order_gate_metadata(
            decision,
            order_symbol="AAPL",
            approval_id="apr-1",
            consensus_decision="SUPPORT",
            neural_gate=_NEURAL_GATE,
        )
        snapshot = decision.evidence["freeze_snapshot"]
        assert metadata["execution_freeze"] is snapshot["frozen"]
        assert metadata["freeze_sampled_at"] == snapshot["sampled_at"]
        assert metadata["freeze_source"] == snapshot["source"]


class TestLowLevelGateReSamples:
    """O adapter reamostra no connect — metadata não é a última palavra."""

    def test_complete_measured_order_passes(self, _reachable_environment):
        # Sanidade: sem isso, os testes abaixo passariam por outro motivo.
        assert _low_level_gate_check(_order(_valid_gate_metadata())) is True

    def test_unmeasured_execution_freeze_is_refused(self, _reachable_environment):
        # `execution_freeze: False` sem `freeze_sampled_at` é literal, não leitura.
        assert _low_level_gate_check(_order(_valid_gate_metadata(freeze_sampled_at=""))) is False

    def test_freeze_flipped_after_the_decision_is_re_sampled(
        self, monkeypatch, _reachable_environment
    ):
        assert _low_level_gate_check(_order(_valid_gate_metadata())) is True

        # Kill switch da família SUPEREZIO_*: o antigo teste do adapter olhava
        # só F51_TRADING_EXECUTION_FREEZE e deixava isto passar.
        monkeypatch.setenv("SUPEREZIO_LIVE_TRADING_DISABLED", "true")
        assert _low_level_gate_check(_order(_valid_gate_metadata())) is False

    def test_env_freeze_off_but_frozen_switch_is_refused(self, monkeypatch, _reachable_environment):
        monkeypatch.setenv("F51_TRADING_EXECUTION_FREEZE", "true")
        assert _low_level_gate_check(_order(_valid_gate_metadata())) is False


class TestPaperTopology:
    """§4: paper é topologia (porta + loopback), não permissão."""

    def test_paper_ports_are_accepted(self):
        assert assert_paper_topology("127.0.0.1", 7497) == ("127.0.0.1", 7497)
        assert assert_paper_topology("localhost", 4002) == ("localhost", 4002)

    def test_live_port_is_refused(self):
        with pytest.raises(PaperTopologyError):
            assert_paper_topology("127.0.0.1", 7496)
        with pytest.raises(PaperTopologyError):
            assert_paper_topology("127.0.0.1", 4001)

    def test_port_outside_the_paper_allowlist_is_refused(self):
        with pytest.raises(PaperTopologyError):
            assert_paper_topology("127.0.0.1", 8080)

    def test_non_loopback_host_is_refused(self):
        with pytest.raises(PaperTopologyError):
            assert_paper_topology("192.168.0.10", 7497)

    def test_settings_refuses_a_live_port_at_boot(self):
        with pytest.raises(ValidationError):
            Settings(ibkr_port=7496)

    def test_settings_refuses_a_port_outside_the_allowlist(self):
        with pytest.raises(ValidationError):
            Settings(ibkr_port=8080)

    def test_settings_accepts_paper_ports(self):
        assert Settings(ibkr_port=4002).ibkr_port in PAPER_IBKR_PORTS
        assert Settings(ibkr_port=7497).ibkr_port in PAPER_IBKR_PORTS

    def test_adapter_refuses_a_live_port(self):
        with pytest.raises(PaperTopologyError):
            InteractiveBrokersAdapter(port=7496)

    def test_adapter_refuses_a_non_allowlisted_port(self):
        with pytest.raises(PaperTopologyError):
            InteractiveBrokersAdapter(port=8080)

    def test_adapter_defaults_to_the_settings_topology(self):
        adapter = InteractiveBrokersAdapter()
        assert adapter._port in PAPER_IBKR_PORTS
        assert adapter._host in {"127.0.0.1", "localhost", "::1"}

    def test_low_level_gate_refuses_when_the_topology_is_not_paper(
        self, monkeypatch, _reachable_environment
    ):
        # Porta não-paper: o gate barra ANTES de construir o socket.
        import adapters.broker.ibkr_adapter as adapter_module

        def _refuse(*args, **kwargs):
            raise PaperTopologyError("IBKR port 7496 is a LIVE trading port")

        monkeypatch.setattr(adapter_module, "assert_paper_topology", _refuse)
        assert _low_level_gate_check(_order(_valid_gate_metadata())) is False
