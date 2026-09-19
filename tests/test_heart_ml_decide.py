import json
from pathlib import Path

from core.heart.ml.decide import SPINE_LABEL_SIGMA, decide_from_bars_tail, decide_path
from core.heart.paths import SPINE_PATH

BARS = json.loads(
    (Path(__file__).resolve().parent / "fixtures" / "heart" / "spine" / "bars.json").read_text(
        encoding="utf-8"
    )
)


def test_spine_path_is_killed_on_the_fixture_crash_bar():
    decision = decide_path(BARS, entry_index=3, spec=SPINE_PATH)
    assert decision.path_id == SPINE_PATH.path_id
    assert decision.status == "killed"
    assert decision.weight == 0.0


def test_decide_path_defaults_sigma_to_spine_constant():
    default = decide_path(BARS, entry_index=3, spec=SPINE_PATH)
    explicit = decide_path(BARS, entry_index=3, spec=SPINE_PATH, sigma=SPINE_LABEL_SIGMA)
    assert default == explicit


def test_decide_path_uses_custom_sigma_when_ewma_positive():
    """Caller-supplied sigma>0 changes barrier width and thus the decision."""
    entry_bar = {"open": 100.0, "high": 101.0, "low": 100.0, "close": 100.0}
    kept = decide_path([entry_bar], entry_index=0, spec=SPINE_PATH, sigma=0.01)
    killed = decide_path([entry_bar], entry_index=0, spec=SPINE_PATH, sigma=0.05)
    assert kept.status == "kept"
    assert killed.status == "killed"


def test_decide_path_sigma_zero_falls_back_to_spine():
    fallback = decide_path(BARS, entry_index=3, spec=SPINE_PATH, sigma=0.0)
    default = decide_path(BARS, entry_index=3, spec=SPINE_PATH)
    assert fallback == default


def test_decide_from_bars_tail_uses_penultimate_bar():
    decision = decide_from_bars_tail(BARS, SPINE_PATH)
    assert decision.path_id == SPINE_PATH.path_id
    assert decision.status == "killed"
    assert decision.weight == 0.0


def test_decide_from_bars_tail_single_bar_uses_zero():
    bars = [{"close": 10.0}]
    decision = decide_from_bars_tail(bars, SPINE_PATH)
    assert decision.status == "killed"
    assert decision.weight == 0.0
