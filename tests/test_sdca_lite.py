import builtins
import json

from core.risk_firewall import (
    DecisionCandidate,
    evaluate_decision_with_sdca,
    run_rumination,
)
from core.risk_firewall.experience_memory import retrieve_experiences


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
