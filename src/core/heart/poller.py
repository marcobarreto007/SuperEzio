"""One mocked ingest cycle. Does not parse RSS into MarketEvent."""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

import httpx

from core.heart.feeds import NON_RECOVERABLE_FEEDS, FeedSpec, feed_by_id
from core.heart.http import HeartHttpError, request
from core.heart.raw_recorder import (
    DEFAULT_HEART_ROOT,
    RawCapture,
    RawRecorder,
    RecordResult,
)

logger = logging.getLogger(__name__)

_POLL_ERRORS = (
    HeartHttpError,
    httpx.TimeoutException,
    httpx.ReadTimeout,
    httpx.ConnectError,
    httpx.RemoteProtocolError,
    httpx.NetworkError,
)


def poll_once(client: httpx.Client, feed: FeedSpec, recorder: RawRecorder) -> RecordResult:
    cond = recorder.conditional_headers(feed)
    response = request(
        client,
        feed.url,
        etag=cond.get("If-None-Match"),
        last_modified=cond.get("If-Modified-Since"),
        read_timeout=feed.poll_read_timeout_s,
    )
    headers: dict[str, str] = {}
    if response.etag:
        headers["ETag"] = response.etag
    if response.last_modified:
        headers["Last-Modified"] = response.last_modified
    return recorder.record(
        feed,
        capture=RawCapture(status=response.status, body=response.body, headers=headers),
    )


def _poll_feed_safe(
    client: httpx.Client,
    feed: FeedSpec,
    recorder: RawRecorder,
) -> bool:
    try:
        poll_once(client, feed, recorder)
    except _POLL_ERRORS as exc:
        logger.error("heart ingest failed for %s: %s", feed.feed_id, exc)
        return False
    return True


def poll_all_feeds(client: httpx.Client, recorder: RawRecorder) -> int:
    """One pass over NON_RECOVERABLE_FEEDS. Individual failures are logged."""
    return sum(1 for feed in NON_RECOVERABLE_FEEDS if _poll_feed_safe(client, feed, recorder))


def ingest_cli(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="run_heart_ingest")
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--root", type=Path, default=DEFAULT_HEART_ROOT)
    parser.add_argument("--feed-id", default="prnewswire")
    parser.add_argument(
        "--all-feeds",
        action="store_true",
        help="Poll every non-recoverable feed once; continue after individual failures.",
    )
    args = parser.parse_args(argv)
    if not args.once:
        parser.error("--once is required")

    recorder = RawRecorder(root=args.root)

    with httpx.Client(timeout=30.0) as client:
        if args.all_feeds:
            ok = poll_all_feeds(client, recorder)
            return 0 if ok > 0 else 1

        poll_once(client, feed_by_id(args.feed_id), recorder)
    return 0
