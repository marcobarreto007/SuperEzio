"""Heart HTTP: UA obrigatório, gzip, 304 honesto, 4xx/5xx reais."""

from __future__ import annotations

import os
from dataclasses import dataclass

import httpx


class HeartHttpError(Exception):
    def __init__(self, status: int, body: bytes = b"") -> None:
        self.status = status
        self.body = body
        super().__init__(f"heart HTTP {status}")


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


def request(
    client: httpx.Client,
    url: str,
    *,
    etag: str | None = None,
    last_modified: str | None = None,
) -> HeartResponse:
    response = client.get(url, headers=build_headers(etag=etag, last_modified=last_modified))
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
