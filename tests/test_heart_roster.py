"""Roster permanente dos 6 subagentes do módulo Coração."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ROSTER = ROOT / "docs" / "superpowers" / "agents" / "heart-roster.json"
AGENTS_DIR = ROOT / ".claude" / "agents"
CURSOR_AGENTS_DIR = ROOT / ".cursor" / "agents"

EXPECTED = (
    "heart-p0-ingest",
    "heart-p1-archive",
    "heart-p2-events",
    "heart-p3-cause",
    "heart-p4-panel",
    "heart-p5-ml",
)


def test_heart_roster_pins_composer_and_six_first_class_ml():
    data = json.loads(ROSTER.read_text(encoding="utf-8"))
    assert data["model"] == "composer-2.5-fast"
    assert data["ml_is_secondary"] is False
    names = [row["name"] for row in data["agents"]]
    assert names == list(EXPECTED)
    ml = next(row for row in data["agents"] if row["name"] == "heart-p5-ml")
    assert ml["first_class"] is True


def test_heart_agent_markdown_exists_for_claude_and_cursor():
    for name in EXPECTED:
        claude = AGENTS_DIR / f"{name}.md"
        cursor = CURSOR_AGENTS_DIR / f"{name}.md"
        assert claude.is_file(), claude
        assert cursor.is_file(), cursor
        text = claude.read_text(encoding="utf-8")
        assert f"name: {name}" in text
        assert "model: composer-2.5-fast" in text
        assert "composer-2.5-fast" in cursor.read_text(encoding="utf-8")


def test_heart_p5_agent_is_first_class_curator():
    text = (AGENTS_DIR / "heart-p5-ml.md").read_text(encoding="utf-8")
    lowered = text.lower()
    assert "não é um anexo" in lowered
    assert "cura" in lowered
    assert "peso" in lowered
    assert "NÃO é secundário" in text or "não é secundário" in lowered
