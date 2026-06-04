from core.ml.reward_gate import RewardGate
from core.ml.sanity import SanityCheck


def test_reward_gate_empty_text_does_not_load_model():
    gate = RewardGate()

    assert gate.score("") == 0.0


def test_sanity_detects_magnitude_mismatch_with_accents():
    verdict = SanityCheck().verify(
        "Tenho 30 mil reais para investir.",
        "Voce tem 30 milhoes de reais para investir com seguranca.",
        min_answer_chars=10,
    )

    assert verdict.passed is True
    assert verdict.warnings
    assert verdict.warnings[0].startswith("magnitude_mismatch")
