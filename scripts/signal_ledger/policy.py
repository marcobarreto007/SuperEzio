"""Carrega política versionada de sinal oficial."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def load_policy(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if "policy_version" not in data:
        raise ValueError(f"policy missing policy_version: {path}")
    return data


def project_root() -> Path:
    return Path(__file__).resolve().parents[2]
