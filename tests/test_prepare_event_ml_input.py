"""Synthetic fixtures verify snapshot provenance, not investment performance."""

import hashlib
import json
import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from prepare_event_ml_input import prepare


def test_freezes_cutoff_and_hashes_original_and_output(tmp_path):
    source = tmp_path / "data/reference/effective_universe/ohlcv"
    source.mkdir(parents=True)
    (tmp_path / "config").mkdir()
    (tmp_path / "config/td_universe_effective.json").write_text("{}")
    csv = "Date,Open,High,Low,Close,Volume\n2020-01-01,1,2,1,2,10\n2020-01-02,2,3,1,2,10\n"
    (source / "TEST.TO.csv").write_text(csv)
    output = tmp_path / "experiment"
    result = prepare(tmp_path, output, "2020-01-01", ("TEST.TO",))
    assert result["rows"] == 1
    assert result["input_sha256"] == hashlib.sha256((output / "bars.csv").read_bytes()).hexdigest()
    assert (
        result["sources"][0]["source_sha256"]
        == hashlib.sha256((source / "TEST.TO.csv").read_bytes()).hexdigest()
    )
    assert pd.read_csv(output / "bars.csv")["date"].tolist() == ["2020-01-01"]
    assert json.loads((output / "input_manifest.json").read_text()) == result
    assert prepare(tmp_path, output, "2020-01-01", ("TEST.TO",)) == result


def test_rejects_paths_before_reading(tmp_path):
    with pytest.raises(ValueError, match="invalid ticker"):
        prepare(tmp_path, tmp_path / "output", "2020-01-01", ("../BAD.TO",))
