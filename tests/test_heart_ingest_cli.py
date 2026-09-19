from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import httpx

from core.heart.poller import ingest_cli
from core.heart.raw_recorder import DEFAULT_HEART_ROOT, RawRecorder, RecordResult


def test_cli_once_with_mock_is_callable():
    assert callable(ingest_cli)


def test_cli_default_root(monkeypatch):
    roots: list[Path | None] = []
    original_init = RawRecorder.__init__

    def spy_init(self, root=None):
        roots.append(root)
        original_init(self, root=root)

    fake_result = RecordResult(
        written=0,
        skipped=0,
        not_modified=True,
        captured_at=datetime.now(UTC),
    )
    monkeypatch.setattr(RawRecorder, "__init__", spy_init)
    monkeypatch.setattr("core.heart.poller.poll_once", lambda *a, **k: fake_result)
    monkeypatch.setenv("SUPEREZIO_HEART_USER_AGENT", "SuperEzioHeart/1.0 (marco@example.com)")

    exit_code = ingest_cli(["--once", "--feed-id", "prnewswire"])
    assert exit_code == 0
    assert roots == [DEFAULT_HEART_ROOT]


def test_all_feeds_continues_after_one_timeout(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("SUPEREZIO_HEART_USER_AGENT", "SuperEzioHeart/1.0 (marco@example.com)")
    rss = (
        Path(__file__).resolve().parent / "fixtures" / "heart" / "spine" / "rss.xml"
    ).read_bytes()

    def handler(request: httpx.Request) -> httpx.Response:
        if "newswire.ca" in str(request.url):
            raise httpx.ReadTimeout("timeout", request=request)
        return httpx.Response(200, content=rss, headers={"ETag": '"s"'})

    real_client = httpx.Client

    def client_factory(*args, **kwargs):
        kwargs.pop("transport", None)
        return real_client(transport=httpx.MockTransport(handler), **kwargs)

    monkeypatch.setattr(httpx, "Client", client_factory)

    root = tmp_path / "heart"
    exit_code = ingest_cli(["--once", "--all-feeds", "--root", str(root)])
    assert exit_code == 0

    recorder = RawRecorder(root=root)
    pr_path = recorder.capture_path("prnewswire", datetime.now(UTC))
    assert pr_path.is_file()
    assert "spine-guid-1" in pr_path.read_text(
        encoding="utf-8"
    ) or "FTFT noise" in pr_path.read_text(encoding="utf-8")


def test_all_feeds_exit_one_when_all_fail(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("SUPEREZIO_HEART_USER_AGENT", "SuperEzioHeart/1.0 (marco@example.com)")

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timeout", request=request)

    real_client = httpx.Client

    def client_factory(*args, **kwargs):
        kwargs.pop("transport", None)
        return real_client(transport=httpx.MockTransport(handler), **kwargs)

    monkeypatch.setattr(httpx, "Client", client_factory)

    exit_code = ingest_cli(["--once", "--all-feeds", "--root", str(tmp_path / "heart")])
    assert exit_code == 1
