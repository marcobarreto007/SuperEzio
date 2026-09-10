"""Artifact paths must not depend on the process cwd.

The documented run command starts the server from ``src/``; a relative
``Path("data/...")`` constant then resolved to ``src/data/...`` and the runtime
split its artifacts in two (live example: ``src/data/bob_pain_log.jsonl`` with
lines missing from the canonical ``data/bob_pain_log.jsonl``).
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SRC_DIR = PROJECT_ROOT / "src"

# Prints the module-level artifacts that used to be cwd-relative.
_PROBE = """
import json

from core.bob_consciousness.body import BobsBody
from core.investor.storage import InvestorStorage
from core.paths import PROJECT_ROOT
from core.trading.historical_cache import DB_PATH

print(json.dumps({
    "DB_PATH": str(DB_PATH),
    "pain_log": str(BobsBody()._pain_log_path),
    "storage_db": str(InvestorStorage().db_path),
    "PROJECT_ROOT": str(PROJECT_ROOT),
}, sort_keys=True))
"""


def _probe(cwd: Path) -> dict[str, str]:
    """Run the probe in a fresh interpreter with *cwd* as working directory."""
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join(
        [str(SRC_DIR), *([env["PYTHONPATH"]] if env.get("PYTHONPATH") else [])]
    )
    proc = subprocess.run(
        [sys.executable, "-c", _PROBE],
        cwd=str(cwd),
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=True,
        timeout=180,
    )
    return json.loads(proc.stdout.strip().splitlines()[-1])


def test_artifact_paths_are_identical_from_src_and_project_root():
    from_root = _probe(PROJECT_ROOT)
    from_src = _probe(SRC_DIR)

    assert from_root == from_src, "artifact paths changed with the cwd"

    root = Path(from_root["PROJECT_ROOT"])
    for key in ("DB_PATH", "pain_log", "storage_db"):
        artifact = Path(from_root[key])
        assert artifact.is_absolute(), f"{key} is not absolute: {artifact}"
        assert root in artifact.parents, f"{key} escaped the project root: {artifact}"
        # The regression this test guards: artifacts under <root>/src/.
        assert SRC_DIR not in artifact.parents, f"{key} landed under src/: {artifact}"


def test_no_relative_data_or_runtime_path_literal_in_src():
    """Static guard: no ``Path("data/...")`` / ``Path("runtime/...")`` literal."""
    pattern = re.compile(r"""Path\(\s*["'](?:data|runtime)/""")
    offenders = [
        f"{path.relative_to(PROJECT_ROOT)}:{lineno}: {line.strip()}"
        for path in sorted(SRC_DIR.rglob("*.py"))
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1)
        if pattern.search(line)
    ]

    assert offenders == [], "relative artifact paths reintroduced:\n" + "\n".join(offenders)
