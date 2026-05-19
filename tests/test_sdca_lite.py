import builtins
import json
from pathlib import Path

from core.risk_firewall import (
    DecisionCandidate,
    evaluate_decision_with_sdca,
    run_rumination,
)
from core.risk_firewall.experience_memory import (
    _cosine,
    _hashed_embedding,
    load_experience_memory,
    retrieve_experiences,
)


def _fomo_candidate() -> DecisionCandidate:
    return DecisionCandidate(
        id="test-fomo-001",
        source="pytest",
        asset="BTC-CAD",
        action="buy_leveraged",
        thesis="BTC subiu forte e quero entrar agora before I miss the move",
        amount_cad=500,
        risk_context={"leverage": True, "fomo": True, "latency": "high"},
        raw_signals={"price_change_2h": 7.2, "social_hype": "high", "spread": "wide"},
    )


def test_fomo_leverage_gets_blocked():
    result = evaluate_decision_with_sdca(_fomo_candidate())

    assert result.decision in {"BLOCK", "REVIEW"}
    assert "fomo_pattern_detected" in result.ghost_tokens
    assert "leverage_impulse" in result.ghost_tokens
    assert "execution_slippage_risk" in result.ghost_tokens


def test_low_risk_candidate_allowed():
    candidate = DecisionCandidate(
        id="test-low-risk-001",
        source="pytest",
        asset="AAPL",
        action="research_only",
        thesis="Review evidence for a small long-term allocation without leverage.",
        amount_cad=100,
        risk_context={"leverage": False, "data_quality": "high", "regime": "normal"},
        raw_signals={"evidence_quality": "high", "spread": "tight", "social_hype": "low"},
    )

    result = evaluate_decision_with_sdca(candidate)

    assert result.decision in {"ALLOW", "REVIEW"}
    assert result.decision != "BLOCK"


def test_rumination_max_three_cycles():
    trace = run_rumination(
        0.95,
        {"experience_count": 0, "evidence_strength": 0.0, "severe_count": 4},
    )

    assert 1 <= len(trace) <= 3
    assert trace[-1].cycle <= 3


def test_experience_delta_r_weighting(tmp_path):
    memory_path = tmp_path / "memory.jsonl"
    rows = [
        {
            "id": "low-delta-relevant",
            "vector_text": "leverage impulse fomo",
            "root_cause": "small leverage mistake",
            "consequence": "minor loss",
            "learned_rule": "review leverage",
            "delta_r": 0.2,
            "tags": ["leverage_impulse", "fomo_pattern_detected"],
            "regime": "high_volatility",
        },
        {
            "id": "high-delta-relevant",
            "vector_text": "leverage impulse fomo spread expansion",
            "root_cause": "leveraged chase",
            "consequence": "large loss",
            "learned_rule": "block leveraged FOMO",
            "delta_r": 0.9,
            "tags": ["leverage_impulse", "fomo_pattern_detected", "spread_expansion"],
            "regime": "high_volatility",
        },
        {
            "id": "huge-delta-unrelated",
            "vector_text": "macro shock accounting fraud",
            "root_cause": "unrelated macro event",
            "consequence": "large unrelated loss",
            "learned_rule": "review macro accounting",
            "delta_r": 9.0,
            "tags": ["macro_uncertainty_high", "data_quality_low"],
            "regime": "macro_shock",
        },
    ]
    memory_path.write_text("\n".join(json.dumps(row) for row in rows), encoding="utf-8")

    matches = retrieve_experiences(
        ["leverage_impulse", "fomo_pattern_detected"],
        _fomo_candidate(),
        top_k=3,
        memory_path=memory_path,
    )

    assert matches[0].episode_id == "high-delta-relevant"
    assert matches[0].weighted_score > matches[1].weighted_score
    assert matches[0].episode_id != "huge-delta-unrelated"


def test_project_fraud_memory_loaded():
    episodes = load_experience_memory()
    ids = {episode.id for episode in episodes}

    assert "sdca-001" in ids
    assert any(episode_id.startswith("fraud-pattern-") for episode_id in ids)
    assert any(episode_id.startswith("fraud-case-") for episode_id in ids)


def test_local_embedding_similarity_is_used():
    related = _cosine(
        _hashed_embedding("leveraged fomo breakout spread expansion"),
        _hashed_embedding("fomo leverage breakout wide spread"),
    )
    unrelated = _cosine(
        _hashed_embedding("leveraged fomo breakout spread expansion"),
        _hashed_embedding("macro accounting revenue audit"),
    )

    assert related > unrelated


def test_output_is_auditable():
    result = evaluate_decision_with_sdca(_fomo_candidate())
    payload = result.model_dump(mode="json")

    for key in (
        "ghost_tokens",
        "uncertainty",
        "matched_experiences",
        "rumination_trace",
        "consequence_score",
        "human_summary",
        "audit_log",
    ):
        assert key in payload
    assert payload["audit_log"]["no_broker_execution"] is True
    assert payload["audit_log"]["no_external_api_calls"] is True


def test_no_broker_execution(monkeypatch):
    real_import = builtins.__import__

    def guarded_import(name, *args, **kwargs):
        forbidden = ("core.trading", "adapters.broker", "alpaca", "ib_insync")
        if name.startswith(forbidden):
            raise AssertionError(f"SDCA imported forbidden execution module: {name}")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", guarded_import)

    result = evaluate_decision_with_sdca(_fomo_candidate())

    assert result.audit_log["no_broker_execution"] is True
    assert result.audit_log["no_external_api_calls"] is True


def test_pipeline_routes_sdca_block_to_blocked():
    from core.pipeline.nodes.sdca_firewall import route_after_sdca_firewall

    assert route_after_sdca_firewall({"sdca_blocked": True}) == "respond_blocked"
    assert route_after_sdca_firewall({"sdca_review_required": True}) == "rag_forensics"
    assert route_after_sdca_firewall({}) == "rag_forensics"


def test_sdca_blocked_response_mentions_no_execution():
    from core.pipeline.nodes.guardrails import _sdca_blocked_response

    response = _sdca_blocked_response(
        {
            "sdca_firewall": {
                "human_summary": "SDCA-Lite BLOCK: test block.",
                "ghost_tokens": ["fomo_pattern_detected", "leverage_impulse"],
            }
        }
    )

    assert "BLOCKED" in response
    assert "no execution" in response
    assert "fomo_pattern_detected" in response


def test_sdca_endpoint_route_registered():
    from agent_server.endpoints import router

    assert "/api/sdca/evaluate" in {route.path for route in router.routes}


def test_sdca_endpoint_returns_block_with_testclient():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from agent_server.endpoints import router

    app = FastAPI()
    app.include_router(router)
    response = TestClient(app).post(
        "/api/sdca/evaluate",
        json=_fomo_candidate().model_dump(mode="json"),
    )

    assert response.status_code == 200
    assert response.json()["decision"] == "BLOCK"


def test_frontend_renders_sdca_firewall_event():
    html = Path("frontend/index.html").read_text(encoding="utf-8")

    assert "function renderSDCA" in html
    assert 'case "SDCA_FIREWALL"' in html
    assert 'sdca_firewall: "sdca"' in html
