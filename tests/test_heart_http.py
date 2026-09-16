import httpx
import pytest

from core.heart.http import HeartHttpError, build_headers, request


def test_headers_include_contact_ua_and_gzip(monkeypatch):
    monkeypatch.setenv("SUPEREZIO_HEART_USER_AGENT", "SuperEzioHeart/1.0 (marco@example.com)")
    h = build_headers(etag='"abc"', last_modified="Tue, 15 Sep 2026 16:00:00 GMT")
    assert "marco@example.com" in h["User-Agent"]
    assert h["Accept-Encoding"] == "gzip"
    assert h["If-None-Match"] == '"abc"'
    assert h["If-Modified-Since"] == "Tue, 15 Sep 2026 16:00:00 GMT"


def test_missing_user_agent_is_an_error(monkeypatch):
    monkeypatch.delenv("SUPEREZIO_HEART_USER_AGENT", raising=False)
    with pytest.raises(RuntimeError, match="SUPEREZIO_HEART_USER_AGENT"):
        build_headers()


def test_304_returns_empty_body(monkeypatch):
    monkeypatch.setenv("SUPEREZIO_HEART_USER_AGENT", "SuperEzioHeart/1.0 (marco@example.com)")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(304, headers={"ETag": '"abc"'})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    resp = request(client, "https://example.invalid/rss", etag='"abc"')
    assert resp.status == 304
    assert resp.body == b""


def test_500_raises(monkeypatch):
    monkeypatch.setenv("SUPEREZIO_HEART_USER_AGENT", "SuperEzioHeart/1.0 (marco@example.com)")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, content=b"nope")

    client = httpx.Client(transport=httpx.MockTransport(handler))
    with pytest.raises(HeartHttpError):
        request(client, "https://example.invalid/rss")
