import json
from pathlib import Path

from core.heart.ml.decide import decide_path
from core.heart.paths import SPINE_PATH

BARS = json.loads(
    (Path(__file__).resolve().parent / "fixtures" / "heart" / "spine" / "bars.json").read_text(encoding="utf-8")
)


def test_spine_path_is_killed_on_the_fixture_crash_bar():
    decision = decide_path(BARS, entry_index=3, spec=SPINE_PATH)
    assert decision.path_id == SPINE_PATH.path_id
    assert decision.status == "killed"
    assert decision.weight == 0.0
