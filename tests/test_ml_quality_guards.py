from core.ml.reward_gate import QualityScore, RewardGate
from core.ml.sanity import SanityCheck


def test_reward_gate_empty_text_does_not_load_model():
    gate = RewardGate()

    assert gate.score("") == 0.0


def test_quality_score_never_claims_investment_accuracy(monkeypatch):
    import importlib

    gate = RewardGate()

    def unavailable():
        raise RuntimeError("offline")

    reward_module = importlib.import_module("core.ml.reward_gate")
    monkeypatch.setattr(reward_module, "_ensure_loaded", unavailable)
    result = gate.score_with_provenance("Structured answer " * 30)
    assert isinstance(result, QualityScore)
    assert result.source == "text_structure_heuristic"
    assert result.scope == "response_form_not_investment_accuracy"


def test_reward_gate_best_of_uses_min_score(monkeypatch):
    gate = RewardGate()
    scores = {"bad": 0.10, "good": 0.80, "best": 0.95}

    monkeypatch.setattr(gate, "score", lambda text: scores[text])

    best_text, best_score, best_idx = gate.best_of(["bad", "good", "best"], min_score=0.75)

    assert best_text == "good"
    assert best_score == 0.80
    assert best_idx == 1


def test_sanity_detects_magnitude_mismatch_with_accents():
    verdict = SanityCheck().verify(
        "Tenho 30 mil reais para investir.",
        "Voce tem 30 milhoes de reais para investir com seguranca.",
        min_answer_chars=10,
    )

    assert verdict.passed is True
    assert verdict.warnings
    assert verdict.warnings[0].startswith("magnitude_mismatch")


def test_feedback_storage_round_trip(tmp_path, monkeypatch):
    import core.ml.feedback as feedback

    monkeypatch.setattr(feedback, "_FEEDBACK_DIR", tmp_path)

    path = feedback.save_feedback(
        "msg-1",
        5,
        comment="good",
        trace={"quality_score": 0.91},
    )
    path.write_text(path.read_text(encoding="utf-8") + "not-json\n", encoding="utf-8")

    records = feedback.load_recent_feedback(days=1)

    assert path.exists()
    assert len(records) == 1
    assert records[0]["msg_id"] == "msg-1"
    assert records[0]["trace"]["quality_score"] == 0.91
