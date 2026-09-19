"""Spec aceite: um LULD FTFT, arquivo P0, junção, ranking killed visível."""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from core.heart.attribution import attribute_move
from core.heart.feeds import feed_by_id
from core.heart.listings import parse_nasdaqtraded_lines
from core.heart.ml.decide import decide_path
from core.heart.moves import daily_moves_from_bars
from core.heart.nyse_halts import parse_nyse_halts_csv
from core.heart.paths import SPINE_PATH
from core.heart.poller import poll_once
from core.heart.ranking import RankingWeights, rank_moves
from core.heart.raw_recorder import RawRecorder

ROOT = Path(__file__).resolve().parent / "fixtures" / "heart" / "spine"


@pytest.fixture
def ua(monkeypatch):
    monkeypatch.setenv("SUPEREZIO_HEART_USER_AGENT", "SuperEzioHeart/1.0 (marco@example.com)")


def test_spine_archive_join_kill_and_row(tmp_path, ua):
    rss = (ROOT / "rss.xml").read_bytes()

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=rss, headers={"ETag": '"s"'})

    rec = RawRecorder(root=tmp_path / "heart")
    result = poll_once(
        httpx.Client(transport=httpx.MockTransport(handler)), feed_by_id("prnewswire"), rec
    )
    assert result.written == 1

    events = parse_nyse_halts_csv((ROOT / "nyse_halts.csv").read_text(encoding="utf-8"))
    assert events[0].event_type == "nyse.luld_pause"

    listing = parse_nasdaqtraded_lines(
        (ROOT / "nasdaqtraded_ftft.txt").read_text(encoding="utf-8")
    )[0]
    bars = json.loads((ROOT / "bars.json").read_text(encoding="utf-8"))
    moves = daily_moves_from_bars(bars=bars, listing=listing, first_seen="2020-01-02")
    day = next(m for m in moves if m["session_date"] == "2026-09-14")
    att = attribute_move(day, events)
    assert att["event_identity"] == events[0].identity
    assert att["confidence"] >= 0.6

    decision = decide_path(bars, entry_index=3, spec=SPINE_PATH)
    assert decision.status == "killed"

    ranked = rank_moves([day], RankingWeights.equal(), attributions={att["move_key"]: att})
    assert ranked[0]["symbol"] == "FTFT"
    ranked[0]["path_status"] = decision.status
    ranked[0]["path_id"] = decision.path_id
    assert ranked[0]["path_status"] == "killed"
