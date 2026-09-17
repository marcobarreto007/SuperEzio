from pathlib import Path
from unittest.mock import patch

import pytest

from core.heart.ml.empty_store import decide_or_refuse
from core.heart.paths import SPINE_PATH

VALID_CSV = """Date,Open,High,Low,Close,Volume
2026-09-13,9.0,9.5,8.8,9.2,1000
2026-09-14,9.2,9.8,8.0,8.5,2000
"""


def test_empty_directory_refuses_with_named_status(tmp_path: Path):
    store = tmp_path / "ohlcv"
    store.mkdir()
    decision = decide_or_refuse(store, SPINE_PATH.path_id)
    assert decision.path_id == SPINE_PATH.path_id
    assert decision.status == "refused_empty_store"
    assert decision.weight == 0.0


def test_gitkeep_only_directory_refuses(tmp_path: Path):
    store = tmp_path / "ohlcv"
    store.mkdir()
    (store / ".gitkeep").write_text("", encoding="utf-8")
    decision = decide_or_refuse(store, SPINE_PATH.path_id)
    assert decision.status == "refused_empty_store"
    assert decision.weight == 0.0


def test_header_only_csv_refuses(tmp_path: Path):
    store = tmp_path / "ohlcv"
    store.mkdir()
    (store / "FTFT.csv").write_text("Date,Open,High,Low,Close,Volume\n", encoding="utf-8")
    decision = decide_or_refuse(store, SPINE_PATH.path_id)
    assert decision.status == "refused_empty_store"
    assert decision.weight == 0.0


def test_missing_store_dir_refuses(tmp_path: Path):
    decision = decide_or_refuse(tmp_path / "missing", SPINE_PATH.path_id)
    assert decision.status == "refused_empty_store"
    assert decision.weight == 0.0


def test_store_with_bars_returns_unweighted_not_trained(tmp_path: Path):
    store = tmp_path / "ohlcv"
    store.mkdir()
    (store / "FTFT.csv").write_text(VALID_CSV, encoding="utf-8")
    decision = decide_or_refuse(store, SPINE_PATH.path_id)
    assert decision.status == "unweighted"
    assert decision.weight == 0.0


def test_never_calls_barrier_decider(tmp_path: Path):
    store = tmp_path / "ohlcv"
    store.mkdir()
    with patch("core.heart.ml.decide.decide_path") as mock_decide:
        decide_or_refuse(store, SPINE_PATH.path_id)
        mock_decide.assert_not_called()


def test_never_imports_boosters():
    import ast

    import core.heart.ml.empty_store as mod

    tree = ast.parse(Path(mod.__file__).read_text(encoding="utf-8"))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
    forbidden = {"lightgbm", "catboost", "river"}
    assert forbidden.isdisjoint(imported)


@pytest.mark.parametrize(
    "status",
    ["refused_empty_store", "unweighted"],
)
def test_refusal_statuses_require_zero_weight(status: str):
    from core.heart.paths import PathDecision

    decision = PathDecision(path_id=SPINE_PATH.path_id, status=status, weight=0.0)
    assert decision.weight == 0.0

    with pytest.raises(ValueError, match="must have weight 0.0"):
        PathDecision(path_id=SPINE_PATH.path_id, status=status, weight=0.5)
