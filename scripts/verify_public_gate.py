#!/usr/bin/env python3
"""Verify the public-deploy gate (G1-G6, G12 of the plan, 2026-08-22).

Checks against a base URL (local or public):
  G1  protected route anonymous -> 401
  G4  register -> 403 (unless SUPEREZIO_PUBLIC_REGISTRATION=1)
  G5  /auth/me anonymous -> 401
  G6  /health and / are public 200; /metrics, /health/dashboard and
      /api/health/dashboard-data are NOT anonymous-reachable (401/403/404)
  G12 public responses scanned for secret-shaped values (no real keys)

Usage:
    python scripts/verify_public_gate.py --base-url http://127.0.0.1:8002

Exit code 0 = all gates green. Non-zero = gate failure (deploy NO-GO).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.error
import urllib.request
from typing import Any

PROTECTED_PROBES = ["/cockpit/summary", "/auth/me"]
TIGHTENED_PROBES = ["/metrics", "/health/dashboard", "/api/health/dashboard-data"]
PUBLIC_PROBES = ["/health", "/"]
SECRET_PATTERNS = re.compile(
    r"(sk-[A-Za-z0-9]{16,}|api[_-]?key\s*[:=]\s*[A-Za-z0-9]{16,}|password\s*[:=]\s*\S{8,})",
    re.IGNORECASE,
)


def _fetch(base_url: str, path: str) -> tuple[int, str]:
    try:
        with urllib.request.urlopen(f"{base_url}{path}", timeout=10) as resp:
            return resp.status, resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8", "replace")
    except Exception as exc:  # connection refused etc.
        return 0, str(exc)


def run_checks(base_url: str) -> dict[str, Any]:
    results: dict[str, Any] = {"base_url": base_url, "checks": [], "failures": []}

    def check(name: str, ok: bool, detail: str) -> None:
        results["checks"].append({"name": name, "ok": ok, "detail": detail})
        if not ok:
            results["failures"].append(name)

    # G1/G5 — protected routes must refuse anonymous access
    for path in PROTECTED_PROBES:
        code, body = _fetch(base_url, path)
        check(f"G1/G5 protected {path} -> 401", code == 401, f"got {code}")

    # G4 — registration must be operator-gated in public mode (POST probe)
    payload = json.dumps(
        {"username": "probe", "email": "p@x.com", "password": "p@ssw0rd123"}
    ).encode()
    req = urllib.request.Request(
        f"{base_url}/auth/register",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            code = resp.status
    except urllib.error.HTTPError as exc:
        code = exc.code
    except Exception:
        code = 0
    check("G4 register -> 403", code == 403, f"got {code}")

    # G6 — tightened public set
    for path in PUBLIC_PROBES:
        code, body = _fetch(base_url, path)
        check(f"G6 public {path} -> 200", code == 200, f"got {code}")
    for path in TIGHTENED_PROBES:
        code, body = _fetch(base_url, path)
        check(
            f"G6 tightened {path} not anonymous (401/403/404)",
            code in (401, 403, 404),
            f"got {code}",
        )

    # G12 — no secret-shaped values in anonymous responses
    leaks = []
    for path in PUBLIC_PROBES + TIGHTENED_PROBES + PROTECTED_PROBES + ["/auth/login"]:
        code, body = _fetch(base_url, path)
        if SECRET_PATTERNS.search(body):
            leaks.append(path)
    check("G12 no secret-shaped values in anonymous responses", not leaks, f"leaks: {leaks}")

    return results


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify SuperEzio public-deploy gate.")
    parser.add_argument("--base-url", default="http://127.0.0.1:8002")
    args = parser.parse_args()

    results = run_checks(args.base_url.rstrip("/"))
    print(json.dumps(results, indent=2))
    return 0 if not results["failures"] else 1


if __name__ == "__main__":
    sys.exit(main())
