"""Peça 0: gravador cru. Sem rede. Sem parsing de negócio."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from core.heart.feeds import NON_RECOVERABLE_FEEDS, feed_by_id
from core.heart.raw_recorder import RawCapture, RawRecorder


@pytest.fixture
def recorder(tmp_path: Path) -> RawRecorder:
    return RawRecorder(root=tmp_path / "heart")


def test_catalog_covers_the_wires_that_have_no_history():
    ids = {feed.feed_id for feed in NON_RECOVERABLE_FEEDS}
    assert ids >= {
        "prnewswire",
        "cnw",
        "businesswire_ma",
        "newsfile",
        "globenewswire",
        "nasdaq_rssoutbound",
    }
    for feed in NON_RECOVERABLE_FEEDS:
        assert feed.url.startswith("http")
        assert feed.recoverable is False


def test_200_appends_one_raw_line_with_body_hash(recorder: RawRecorder):
    captured = datetime(2026, 9, 15, 16, 0, tzinfo=UTC)
    body = b"<rss><channel><title>x</title></channel></rss>"
    result = recorder.record(
        feed_by_id("prnewswire"),
        capture=RawCapture(
            status=200,
            body=body,
            headers={"ETag": '"abc"', "Last-Modified": "Tue, 15 Sep 2026 16:00:00 GMT"},
            captured_at=captured,
        ),
    )

    assert result.written == 1
    assert result.skipped == 0
    assert result.not_modified is False
    path = recorder.capture_path("prnewswire", captured)
    lines = path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    row = json.loads(lines[0])
    assert row["feed_id"] == "prnewswire"
    assert row["http_status"] == 200
    assert row["body"] == body.decode("utf-8")
    assert row["body_sha256"] == hashlib.sha256(body).hexdigest()
    assert row["captured_at"] == "2026-09-15T16:00:00+00:00"


def test_identical_body_is_not_written_twice(recorder: RawRecorder):
    feed = feed_by_id("cnw")
    body = b"<rss>same</rss>"
    first = recorder.record(feed, capture=RawCapture(status=200, body=body))
    second = recorder.record(feed, capture=RawCapture(status=200, body=body))
    assert first.written == 1
    assert second.written == 0
    assert second.skipped == 1
    path = recorder.capture_path(feed.feed_id, first.captured_at)
    assert len(path.read_text(encoding="utf-8").strip().splitlines()) == 1


def test_304_writes_nothing(recorder: RawRecorder, tmp_path: Path):
    result = recorder.record(
        feed_by_id("newsfile"),
        capture=RawCapture(status=304, body=b"", headers={"ETag": '"keep"'}),
    )
    assert result.not_modified is True
    assert result.written == 0
    assert not any((tmp_path / "heart").rglob("*.jsonl"))


def test_conditional_headers_round_trip_etag_and_last_modified(recorder: RawRecorder):
    feed = feed_by_id("globenewswire")
    assert recorder.conditional_headers(feed) == {}
    recorder.record(
        feed,
        capture=RawCapture(
            status=200,
            body=b"<rss>v1</rss>",
            headers={
                "ETag": '"v1"',
                "Last-Modified": "Tue, 15 Sep 2026 12:00:00 GMT",
            },
        ),
    )
    assert recorder.conditional_headers(feed) == {
        "If-None-Match": '"v1"',
        "If-Modified-Since": "Tue, 15 Sep 2026 12:00:00 GMT",
    }


def test_capture_path_is_partitioned_by_utc_date(recorder: RawRecorder):
    captured = datetime(2026, 1, 2, 3, 4, tzinfo=UTC)
    path = recorder.capture_path("nasdaq_rssoutbound", captured)
    assert path.as_posix().endswith("raw/2026/01/02/nasdaq_rssoutbound.jsonl")


def test_seen_hashes_survive_a_new_recorder_instance(tmp_path: Path):
    root = tmp_path / "heart"
    body = b"<rss>persist</rss>"
    RawRecorder(root).record(feed_by_id("prnewswire"), capture=RawCapture(status=200, body=body))
    again = RawRecorder(root).record(
        feed_by_id("prnewswire"), capture=RawCapture(status=200, body=body)
    )
    assert again.written == 0
    assert again.skipped == 1


def test_corrupt_line_is_quarantined_and_does_not_block_new_capture(recorder: RawRecorder):
    captured = datetime(2026, 9, 15, tzinfo=UTC)
    path = recorder.capture_path("prnewswire", captured)
    path.parent.mkdir(parents=True)
    path.write_text("{not json\n", encoding="utf-8")
    result = recorder.record(
        feed_by_id("prnewswire"),
        capture=RawCapture(status=200, body=b"<rss>ok</rss>", captured_at=captured),
    )
    assert result.written == 1
    quarantine = path.with_name(path.name + ".quarantine")
    assert quarantine.read_text(encoding="utf-8").startswith("{not json")
    surviving = [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip().startswith("{") and '"feed_id"' in line
    ]
    assert len(surviving) == 1


def test_pytest_cannot_write_the_production_heart_path(monkeypatch, tmp_path: Path):
    production = tmp_path / "production_heart"
    monkeypatch.setattr("core.heart.raw_recorder.DEFAULT_HEART_ROOT", production)
    monkeypatch.setenv("PYTEST_CURRENT_TEST", "tests/test_heart_raw_recorder.py::test")
    blocked = RawRecorder(root=production)
    with pytest.raises(RuntimeError, match="pytest"):
        blocked.record(feed_by_id("prnewswire"), capture=RawCapture(status=200, body=b"x"))
