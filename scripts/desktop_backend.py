"""Standalone Windows backend entry point owned by the Electron supervisor."""

from __future__ import annotations

import argparse
import json
import multiprocessing
import os
import shutil
import sys
from pathlib import Path


def resource_root() -> Path:
    return Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[1]))


def prepare_workspace(resources: Path, destination: Path) -> Path:
    """Install public defaults only; customer configuration survives upgrades."""
    destination = destination.expanduser().resolve()
    if destination == resources.resolve():
        raise ValueError("Desktop data must be separate from installed resources")
    for name in ("config", "frontend", "templates"):
        source = resources / name
        if not source.is_dir():
            raise FileNotFoundError(f"Required desktop resource missing: {name}")
        for item in source.rglob("*"):
            if not item.is_file() or item.is_symlink():
                continue
            if item.suffix.lower() not in {
                ".json",
                ".yml",
                ".yaml",
                ".html",
                ".css",
                ".js",
                ".svg",
                ".png",
                ".ico",
                ".woff",
                ".woff2",
            }:
                continue
            target = destination / name / item.relative_to(source)
            target.parent.mkdir(parents=True, exist_ok=True)
            if name != "config" or not target.exists():
                shutil.copy2(item, target)
    for name in ("runtime", "data", "journal", ".f51", "logs"):
        (destination / name).mkdir(parents=True, exist_ok=True)
    return destination


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="SuperEzio desktop backend")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args(argv)
    data = os.getenv("SUPEREZIO_DESKTOP_DATA_DIR")
    if not data:
        raise RuntimeError("SUPEREZIO_DESKTOP_DATA_DIR is required")
    port = int(os.getenv("SUPEREZIO_PORT", "18002"))
    if not 1024 <= port <= 65535:
        raise ValueError("Desktop port must be between 1024 and 65535")
    root = prepare_workspace(resource_root(), Path(data))
    os.environ["SUPEREZIO_DESKTOP_DATA_DIR"] = str(root)
    os.environ["SUPEREZIO_HOST"] = "127.0.0.1"
    os.environ["SUPEREZIO_PORT"] = str(port)
    os.environ.setdefault("A2A_AGENT_NAME", "SuperEzio")
    os.chdir(root)
    if not getattr(sys, "frozen", False):
        sys.path.insert(0, str(resource_root() / "src"))
    from agent_server.main import app

    if args.self_test:
        from fastapi.testclient import TestClient

        # No lifespan: validate frozen imports/routes/resources without API calls.
        client = TestClient(app)
        response = client.get("/")
        if response.status_code != 200 or "text/html" not in response.headers.get(
            "content-type", ""
        ):
            raise RuntimeError("Packaged frontend self-test failed")
        print(json.dumps({"status": "ok", "data_dir": str(root), "frontend": True}))
        return 0
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=port, log_level="info")
    return 0


if __name__ == "__main__":
    multiprocessing.freeze_support()
    raise SystemExit(main())
