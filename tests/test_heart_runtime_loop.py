from pathlib import Path

import httpx

from core.heart.event_book import EventBook
from core.heart.feeds import NON_RECOVERABLE_FEEDS, feed_by_id
from core.heart.runtime_loop import run_heart_cycle

RSS_WITH_PUBDATE = """<?xml version="1.0"?>
<rss version="2.0"><channel><title>t</title>
<item>
  <title>hello</title>
  <guid>cycle-guid-1</guid>
  <pubDate>Wed, 16 Sep 2026 15:00:00 GMT</pubDate>
</item>
</channel></rss>
"""

HALT_CSV = (
    Path(__file__).resolve().parent / "fixtures" / "heart" / "spine" / "nyse_halts.csv"
).read_text(encoding="utf-8")


def test_cycle_writes_raw_rss_and_event_book(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("SUPEREZIO_HEART_USER_AGENT", "SuperEzioHeart/1.0 (marco@example.com)")
    root = tmp_path / "heart"

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if "trade-halts" in url:
            return httpx.Response(200, content=HALT_CSV.encode("utf-8"))
        return httpx.Response(200, content=RSS_WITH_PUBDATE.encode("utf-8"))

    client = httpx.Client(transport=httpx.MockTransport(handler), timeout=30.0)
    result = run_heart_cycle(root=root, client=client)
    assert result["feeds_ok"] == len(NON_RECOVERABLE_FEEDS)
    assert result["rss_events"] >= 1
    assert result["nyse_events"] >= 1
    book = EventBook(root / "events.jsonl")
    identities = {event.identity for event in book.read_all()}
    assert "cycle-guid-1" in identities
    assert any(event.event_type == "nyse.luld_pause" for event in book.read_all())
    raw = list((root / "raw").rglob("*.jsonl"))
    assert raw
    assert feed_by_id("prnewswire").feed_id


def test_cycle_nyse_http_error_does_not_invent_halts(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("SUPEREZIO_HEART_USER_AGENT", "SuperEzioHeart/1.0 (marco@example.com)")
    root = tmp_path / "heart"

    def handler(request: httpx.Request) -> httpx.Response:
        if "trade-halts" in str(request.url):
            return httpx.Response(403, content=b"nope")
        return httpx.Response(200, content=RSS_WITH_PUBDATE.encode("utf-8"))

    client = httpx.Client(transport=httpx.MockTransport(handler), timeout=30.0)
    result = run_heart_cycle(root=root, client=client)
    assert result["feeds_ok"] == len(NON_RECOVERABLE_FEEDS)
    assert result["nyse_events"] == 0
    events = EventBook(root / "events.jsonl").read_all()
    assert all(event.event_type != "nyse.luld_pause" for event in events)


def test_process_main_once_does_not_need_fastapi(tmp_path: Path, monkeypatch):
    import importlib

    heart_main = importlib.import_module("core.heart.__main__")

    calls: list[Path] = []

    def fake_cycle(root: Path):
        calls.append(root)
        return {"feeds_ok": 0, "feeds_total": 0, "rss_events": 0, "nyse_events": 0}

    monkeypatch.setattr(heart_main, "_cycle_with_own_client", fake_cycle)
    monkeypatch.setenv("SUPEREZIO_HEART_USER_AGENT", "SuperEzioHeart/1.0 (marco@example.com)")
    exit_code = heart_main.main(["--once", "--root", str(tmp_path / "heart")])
    assert exit_code == 0
    assert calls == [tmp_path / "heart"]


def test_cycle_nasdaq_timeout_does_not_abort_cycle(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("SUPEREZIO_HEART_USER_AGENT", "SuperEzioHeart/1.0 (marco@example.com)")
    root = tmp_path / "heart"
    nasdaq_url = feed_by_id("nasdaq_rssoutbound").url

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if url == nasdaq_url:
            raise httpx.ReadTimeout("read timed out", request=request)
        if "trade-halts" in url:
            return httpx.Response(200, content=HALT_CSV.encode("utf-8"))
        return httpx.Response(200, content=RSS_WITH_PUBDATE.encode("utf-8"))

    client = httpx.Client(transport=httpx.MockTransport(handler), timeout=30.0)
    result = run_heart_cycle(root=root, client=client)
    assert result["feeds_ok"] == len(NON_RECOVERABLE_FEEDS) - 1
    assert result["rss_events"] >= 1
    assert result["nyse_events"] >= 1
    assert (root / "raw").exists()
    assert (root / "events.jsonl").exists()


def test_process_main_refuses_without_user_agent(monkeypatch):
    import importlib

    heart_main = importlib.import_module("core.heart.__main__")
    monkeypatch.delenv("SUPEREZIO_HEART_USER_AGENT", raising=False)
    assert heart_main.main(["--once"]) == 2
