"""One mocked ingest cycle. Does not parse RSS into MarketEvent."""

from __future__ import annotations

import argparse
from pathlib import Path

import httpx

from core.heart.feeds import FeedSpec, feed_by_id
from core.heart.http import request
from core.heart.raw_recorder import RawCapture, RawRecorder, RecordResult


def poll_once(client: httpx.Client, feed: FeedSpec, recorder: RawRecorder) -> RecordResult:
    cond = recorder.conditional_headers(feed)
    response = request(
        client,
        feed.url,
        etag=cond.get("If-None-Match"),
        last_modified=cond.get("If-Modified-Since"),
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


def ingest_cli(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="run_heart_ingest")
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--root", type=Path)
    parser.add_argument("--feed-id", default="prnewswire")
    args = parser.parse_args(argv)
    if not args.once:
        parser.error("--once is required")
    if args.root is None:
        parser.error("--root is required")
    recorder = RawRecorder(root=args.root)
    feed = feed_by_id(args.feed_id)
    with httpx.Client(timeout=30.0) as client:
        poll_once(client, feed, recorder)
    return 0
