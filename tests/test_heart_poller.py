from pathlib import Path

import httpx
import pytest

from core.heart.feeds import feed_by_id
from core.heart.http import HeartHttpError
from core.heart.poller import poll_once
from core.heart.raw_recorder import RawRecorder


def test_one_cycle_appends_jsonl(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("SUPEREZIO_HEART_USER_AGENT", "SuperEzioHeart/1.0 (marco@example.com)")
    rss = (
        Path(__file__).resolve().parent / "fixtures" / "heart" / "spine" / "rss.xml"
    ).read_bytes()

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=rss, headers={"ETag": '"s"'})

    recorder = RawRecorder(root=tmp_path / "heart")
    client = httpx.Client(transport=httpx.MockTransport(handler))
    result = poll_once(client, feed_by_id("prnewswire"), recorder)
    assert result.written == 1
    path = recorder.capture_path("prnewswire", result.captured_at)
    assert path.is_file()
    text = path.read_text(encoding="utf-8")
    assert "spine-guid-1" in text or "FTFT noise" in text


def test_poll_once_propagates_http_error(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("SUPEREZIO_HEART_USER_AGENT", "SuperEzioHeart/1.0 (marco@example.com)")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, content=b"down")

    recorder = RawRecorder(root=tmp_path / "heart")
    client = httpx.Client(transport=httpx.MockTransport(handler))
    with pytest.raises(HeartHttpError):
        poll_once(client, feed_by_id("prnewswire"), recorder)
