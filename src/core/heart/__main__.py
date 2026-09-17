"""Dedicated Heart ingest process — survives FastAPI death.

    python -m core.heart --once
    python -m core.heart --root data/heart

Requires SUPEREZIO_HEART_USER_AGENT. Does not start :8002.
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
import time
from pathlib import Path

from core.heart.raw_recorder import DEFAULT_HEART_ROOT
from core.heart.runtime_loop import _cycle_with_own_client, _interval_seconds

logger = logging.getLogger("core.heart")


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Heart ingest process (no FastAPI).")
    parser.add_argument("--once", action="store_true", help="One cycle then exit.")
    parser.add_argument(
        "--root",
        type=Path,
        default=None,
        help="Heart data root (default: data/heart).",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s heart-ingest %(message)s",
    )
    if not os.getenv("SUPEREZIO_HEART_USER_AGENT"):
        logger.error("SUPEREZIO_HEART_USER_AGENT is required")
        return 2
    root = Path(args.root) if args.root is not None else DEFAULT_HEART_ROOT
    root.mkdir(parents=True, exist_ok=True)
    if args.once:
        _cycle_with_own_client(root)
        return 0
    logger.info("Heart ingest process started root=%s interval=%ss", root, _interval_seconds())
    while True:
        try:
            _cycle_with_own_client(root)
        except Exception as exc:  # noqa: BLE001 — stay alive; next cycle retries
            logger.warning("heart ingest cycle failed: %s", exc)
        time.sleep(_interval_seconds())


if __name__ == "__main__":
    sys.exit(main())
