"""Heart HTTP: UA obrigatório, gzip, 304 honesto, 4xx/5xx reais."""

from __future__ import annotations

import os
from dataclasses import dataclass

import httpx


class HeartHttpError(Exception):
    def __init__(self, status: int, body: bytes = b"", *, reason: str | None = None) -> None:
        self.status = status
        self.body = body
        self.reason = reason
        message = f"heart HTTP {status}"
        if reason:
            message = f"{message}: {reason}"
        super().__init__(message)


@dataclass(frozen=True, slots=True)
class HeartResponse:
    status: int
    body: bytes
    etag: str | None = None
    last_modified: str | None = None


def build_headers(
    etag: str | None = None,
    last_modified: str | None = None,
) -> dict[str, str]:
    ua = os.environ.get("SUPEREZIO_HEART_USER_AGENT")
    if not ua:
        raise RuntimeError("SUPEREZIO_HEART_USER_AGENT is required")
    headers = {
        "User-Agent": ua,
        "Accept-Encoding": "gzip",
    }
    if etag:
        headers["If-None-Match"] = etag
    if last_modified:
        headers["If-Modified-Since"] = last_modified
    return headers


def _require_read_timeout(client: httpx.Client) -> None:
    timeout = client.timeout
    if timeout is None:
        raise RuntimeError("httpx.Client read timeout is required for heart ingest")
    if isinstance(timeout, (int, float)):
        return
    if isinstance(timeout, httpx.Timeout):
        if timeout.read is None:
            raise RuntimeError("httpx.Client read timeout is required for heart ingest")
        return
    raise RuntimeError("httpx.Client read timeout is required for heart ingest")


def request(
    client: httpx.Client,
    url: str,
    *,
    etag: str | None = None,
    last_modified: str | None = None,
    read_timeout: float | None = None,
) -> HeartResponse:
    _require_read_timeout(client)
    get_kwargs: dict[str, object] = {}
    if read_timeout is not None:
        connect = min(10.0, read_timeout)
        get_kwargs["timeout"] = httpx.Timeout(read_timeout, connect=connect, read=read_timeout)
    try:
        response = client.get(
            url,
            headers=build_headers(etag=etag, last_modified=last_modified),
            **get_kwargs,
        )
    except httpx.TimeoutException as exc:
        raise HeartHttpError(408, reason=str(exc)) from exc
    if response.status_code == 304:
        return HeartResponse(
            status=304,
            body=b"",
            etag=response.headers.get("ETag"),
            last_modified=response.headers.get("Last-Modified"),
        )
    if response.status_code >= 400:
        raise HeartHttpError(response.status_code, response.content)
    return HeartResponse(
        status=response.status_code,
        body=response.content,
        etag=response.headers.get("ETag"),
        last_modified=response.headers.get("Last-Modified"),
    )
