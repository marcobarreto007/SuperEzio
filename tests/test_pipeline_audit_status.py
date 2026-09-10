"""Rótulo de auditoria do tier de arbitragem (juiz/auditor) — rotular, não bloquear.

Regressão 2026-09-10: num run real o juiz E o auditor falharam e o cliente
recebeu a resposta completa sem saber. Bloquear a resposta transformaria um 5xx
da DeepSeek em negação de serviço ao cliente (com dinheiro FROZEN), então o
pipeline segue entregando — mas o veredicto que Bob lê passa a carregar
AUDITED / NOT_AUDITED / NOT_RUN e uma resposta que omita a não-auditoria
reprova em :func:`validate_answer_against_verdict`.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

_SPY_TIP = (
    "me dá uma dica de investimento agora sobre SPY: tese, direção, "
    "invalidação, alvo e stop. Sem ordem."
)

# Uma resposta que fala dos módulos do pipeline SEM tocar em auditoria.
_ANSWER_WITHOUT_AUDIT = (
    "DADOS DO PIPELINE: RSI=70.0 MACD=1.2 F51=0.9 SDCA=ALLOW NEURAL=RISK_ON "
    "EXPERTS=NEUTRAL TRINITY=RAN PENNYLAB=N/A RAG=RAN GUARDRAIL=True"
)


def _auditor_gateway(*, with_auditor: bool = True) -> SimpleNamespace:
    providers = [SimpleNamespace(name="daytrade_judge")]
    if with_auditor:
        providers.append(SimpleNamespace(name="daytrade_auditor"))
    return SimpleNamespace(providers=providers)


def _ok_expert(state, *, verdict: str = "NEUTRAL") -> dict:
    role = state["role"]
    return {
        "expert_results": [
            {"role": role, "ok": True, "response": f'{{"verdict":"{verdict}","confidence":50}}'}
        ]
    }


async def _run_market_stack(
    monkeypatch,
    *,
    expert_behavior,
    collect_experts_behavior=None,
    arbitration: str = "1",
    auditor_model: str = "deepseek-v4-flash",
    with_auditor: bool = True,
):
    """Roda _auto_full_analysis com o comitê e a arbitragem ligados (fakes)."""
    from src.core.pipeline import graph as graph_module

    events: list = []
    monkeypatch.setattr(graph_module, "get_stream_writer", lambda: events.append)
    monkeypatch.setenv("SUPEREZIO_PIPELINE_ARBITRATION", arbitration)
    monkeypatch.setenv("SUPEREZIO_JUDGE_AGENTS", "1")
    monkeypatch.delenv("SUPEREZIO_RED_TEAM_AGENTS", raising=False)
    monkeypatch.setenv("SUPEREZIO_DAYTRADE_AUDITOR_MODEL", auditor_model)

    async def fake_collector(state, config=None):
        return {
            "data": {"ticker": "SPY", "price": {"latest": 770.19}},
            "ticker": "SPY",
            "data_context": "SPY PRICE=770.19",
        }

    async def fake_expert(state, gateway=None):
        return expert_behavior(state)

    async def fake_collect_experts(state):
        return {
            "expert_summary": "committee ran",
            "expert_consensus": {"decision": "NEUTRAL", "score": 0.0, "weight_coverage": 1.0},
        }

    async def fake_f51(state):
        return {"f51_verdict": {"passed": True, "decision_score": 0.9, "confidence": 0.9}}

    async def fake_neural(state):
        return {"neural_decision": {"regime": "RISK_ON", "confidence": 0.5}}

    async def fake_sdca(state):
        return {"sdca_firewall": {"decision": "ALLOW", "confidence": 0.9}}

    async def fake_rag(state):
        return {"rag_context": "none"}

    monkeypatch.setattr(graph_module, "node_collector", fake_collector)
    monkeypatch.setattr(graph_module, "node_expert", fake_expert)
    monkeypatch.setattr(
        graph_module, "node_collect_experts", collect_experts_behavior or fake_collect_experts
    )
    monkeypatch.setattr(graph_module, "node_f51_verdict", fake_f51)
    monkeypatch.setattr(graph_module, "node_neural_decision", fake_neural)
    monkeypatch.setattr(graph_module, "node_sdca_firewall", fake_sdca)
    monkeypatch.setattr(graph_module, "node_rag_forensics", fake_rag)

    result = await graph_module._auto_full_analysis(
        {
            "run_id": "audit-status-test",
            "route": "agent",
            "intent": "bob_decides",
            "ticker": "SPY",
            "message": _SPY_TIP,
            "errors": [],
        },
        gateway=_auditor_gateway(with_auditor=with_auditor),
    )
    return result, events


@pytest.mark.asyncio
async def test_auditor_success_labels_audited(monkeypatch):
    result, _ = await _run_market_stack(
        monkeypatch, expert_behavior=lambda state: _ok_expert(state)
    )

    assert result["expert_committee_status"] == "OK"
    assert result["audit_status"] == {"status": "AUDITED", "reason": None}
    assert result["auditor_result"]["role"] == "auditor_agent"
    assert result["auditor_result"]["ok"] is True


@pytest.mark.asyncio
async def test_auditor_exception_labels_not_audited_with_reason(monkeypatch):
    def behavior(state):
        if state["role"] == "auditor_agent":
            raise RuntimeError("auditor_provider_timeout")
        return _ok_expert(state)

    result, _ = await _run_market_stack(monkeypatch, expert_behavior=behavior)

    assert result["audit_status"]["status"] == "NOT_AUDITED"
    assert "auditor_provider_timeout" in result["audit_status"]["reason"]
    # Best effort still holds: the answer keeps flowing, only now it is labelled.
    assert result["expert_summary"] == "committee ran"
    assert result["audit_status"]["status"] != "AUDITED"


@pytest.mark.asyncio
async def test_auditor_ok_false_payload_labels_not_audited(monkeypatch):
    def behavior(state):
        if state["role"] == "auditor_agent":
            return {
                "expert_results": [
                    {
                        "role": "auditor_agent",
                        "ok": False,
                        "error": "strict_json_validation_failed",
                        "provider": "daytrade_auditor",
                    }
                ]
            }
        return _ok_expert(state)

    result, _ = await _run_market_stack(monkeypatch, expert_behavior=behavior)

    assert result["audit_status"] == {
        "status": "NOT_AUDITED",
        "reason": "strict_json_validation_failed",
    }


@pytest.mark.asyncio
async def test_judge_exception_is_recorded_and_does_not_fabricate_audit(monkeypatch):
    def behavior(state):
        if state["role"].startswith("judge_agent"):
            raise RuntimeError("judge_provider_unreachable")
        return _ok_expert(state)

    result, _ = await _run_market_stack(monkeypatch, expert_behavior=behavior)

    judge = result["judge_results"][0]
    assert judge["ok"] is False
    assert "judge_provider_unreachable" in judge["error"]
    # O juiz não é a auditoria: o auditor rodou, então o rótulo é AUDITED — o que
    # não pode acontecer é a falha do juiz desaparecer do payload do run.
    assert result["audit_status"] == {"status": "AUDITED", "reason": None}


@pytest.mark.asyncio
async def test_expert_committee_collapse_labels_failed(monkeypatch):
    async def collapsing_collector(state):
        raise RuntimeError("expert_collector_exploded")

    healthy, _ = await _run_market_stack(
        monkeypatch, expert_behavior=lambda state: _ok_expert(state)
    )
    assert healthy["expert_committee_status"] == "OK"

    result, _ = await _run_market_stack(
        monkeypatch,
        expert_behavior=lambda state: _ok_expert(state),
        collect_experts_behavior=collapsing_collector,
    )

    assert result["expert_committee_status"] == "FAILED"
    assert any("expert_collector_exploded" in err for err in result["errors"])


@pytest.mark.asyncio
async def test_disabled_arbitration_labels_not_run_and_never_calls_auditor(monkeypatch):
    called: list[str] = []

    def behavior(state):
        called.append(state["role"])
        return _ok_expert(state)

    result, _ = await _run_market_stack(monkeypatch, expert_behavior=behavior, arbitration="0")

    assert result["audit_status"] == {"status": "NOT_RUN", "reason": "arbitration_disabled"}
    assert "auditor_agent" not in called
    assert not [role for role in called if role.startswith("judge_agent")]


@pytest.mark.asyncio
async def test_auditor_kill_switch_off_labels_not_run(monkeypatch):
    called: list[str] = []

    def behavior(state):
        called.append(state["role"])
        return _ok_expert(state)

    result, _ = await _run_market_stack(monkeypatch, expert_behavior=behavior, auditor_model="off")

    assert result["audit_status"] == {"status": "NOT_RUN", "reason": "auditor_kill_switch_off"}
    assert "auditor_agent" not in called
    # O kill-switch é do auditor; o juiz continua rodando.
    assert any(role.startswith("judge_agent") for role in called)


@pytest.mark.asyncio
async def test_auditor_provider_absent_from_gateway_labels_not_run(monkeypatch):
    called: list[str] = []

    def behavior(state):
        called.append(state["role"])
        return _ok_expert(state)

    result, _ = await _run_market_stack(monkeypatch, expert_behavior=behavior, with_auditor=False)

    assert result["audit_status"] == {"status": "NOT_RUN", "reason": "auditor_provider_missing"}
    assert "auditor_agent" not in called


def test_not_audited_label_reaches_the_verdict_bob_reads():
    from src.core.pipeline.verdict import build_pipeline_verdict, build_verdict_dict

    state = {"audit_status": {"status": "NOT_AUDITED", "reason": "auditor_provider_timeout"}}

    assert build_verdict_dict(state)["audit"] == {
        "status": "NOT_AUDITED",
        "reason": "auditor_provider_timeout",
    }
    assert build_pipeline_verdict(state)["audit"] == {
        "status": "NOT_AUDITED",
        "reason": "auditor_provider_timeout",
    }


def test_missing_label_is_reported_as_not_run_never_as_audited():
    from src.core.pipeline.verdict import build_verdict_dict

    assert build_verdict_dict({})["audit"] == {
        "status": "NOT_RUN",
        "reason": "audit_status_missing",
    }


def test_answer_omitting_the_non_audit_reproves():
    from src.core.pipeline.verdict import build_verdict_dict, validate_answer_against_verdict

    not_audited = build_verdict_dict(
        {"audit_status": {"status": "NOT_AUDITED", "reason": "auditor_provider_timeout"}}
    )
    omitted = validate_answer_against_verdict(_ANSWER_WITHOUT_AUDIT, not_audited)
    assert omitted["passed"] is False
    assert "AUDIT" in omitted["reason"]

    audited = build_verdict_dict({"audit_status": {"status": "AUDITED", "reason": None}})
    assert "AUDIT" not in validate_answer_against_verdict(_ANSWER_WITHOUT_AUDIT, audited)["reason"]


@pytest.mark.asyncio
async def test_audit_label_survives_langgraph_state_schema():
    """Regressão: LangGraph descarta updates fora dos canais de PipelineState.

    Sem `audit_status` declarado em PipelineState, o rótulo gravado por
    _auto_full_analysis morria no nó e build_verdict_dict devolvia NOT_RUN
    (audit_status_missing) no veredicto que Bob lê — o mesmo modo de falha que
    engoliu expert_consensus (incidente T1, 2026-08-22).
    """
    from langgraph.graph import END, START, StateGraph

    from src.core.pipeline.contracts import PipelineState
    from src.core.pipeline.verdict import build_verdict_dict

    seen: dict = {}

    async def produce(state):
        return {
            "audit_status": {"status": "NOT_AUDITED", "reason": "auditor_provider_timeout"},
            "expert_committee_status": "FAILED",
        }

    async def consume(state):
        seen["audit_status"] = state.get("audit_status")
        seen["committee_status"] = state.get("expert_committee_status")
        seen["verdict"] = build_verdict_dict(state)["audit"]
        return {}

    builder = StateGraph(PipelineState)
    builder.add_node("produce", produce)
    builder.add_node("consume", consume)
    builder.add_edge(START, "produce")
    builder.add_edge("produce", "consume")
    builder.add_edge("consume", END)
    await builder.compile().ainvoke({})

    assert seen["audit_status"] == {
        "status": "NOT_AUDITED",
        "reason": "auditor_provider_timeout",
    }
    assert seen["committee_status"] == "FAILED"
    assert seen["verdict"]["status"] == "NOT_AUDITED"
