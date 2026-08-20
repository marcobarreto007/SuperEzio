"""Tests for scripts/check_agents.py — the agent/skill cross-reference gate.

Gate inspired by anthropics/financial-services check.py
(see docs/architecture/ANTHROPIC_FS_DEEP_DIVE.md, section 6).
Deterministic, local-only: no network, no server required.
"""

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "check_agents.py"

_spec = importlib.util.spec_from_file_location("check_agents", SCRIPT)
assert _spec is not None and _spec.loader is not None
check_agents = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(check_agents)


def test_frontmatter_parser_extracts_fields():
    text = "---\nname: captain\ndescription: Capitao\ntools: Read, Bash\n---\nbody"
    fm = check_agents.parse_frontmatter(text)
    assert fm["name"] == "captain"
    assert "Bash" in fm["tools"]


def test_frontmatter_parser_rejects_missing_block():
    assert check_agents.parse_frontmatter("no frontmatter here") == {}


def test_skill_refs_extracts_call_path_and_inline():
    text = (
        '1. Skill("f51-quality-gate")\n'
        "2. veja .claude/skills/tese-tracker\n"
        "3. invoque a skill `tese-tracker` antes\n"
        "4. palavra skill na linha sem ref\n"
    )
    refs = check_agents.skill_refs_in_text(text)
    assert "f51-quality-gate" in refs
    assert "tese-tracker" in refs


def test_skill_refs_ignores_unrelated_backticks():
    text = "rode `python -m pytest` depois de `git status`"
    assert check_agents.skill_refs_in_text(text) == set()


def test_agent_refs_extracts_subagent_type():
    text = 'Agent(subagent_type="recon-researcher") e Agent(subagent_type="general-purpose")'
    refs = check_agents.agent_refs_in_text(text)
    assert refs == {"recon-researcher", "general-purpose"}


def test_current_tree_is_clean():
    """The gate itself, as a test: every cross-ref in the live tree must resolve."""
    issues = check_agents.check()
    assert issues == [], "cross-reference violations:\n" + "\n".join(issues)


def test_delivery_roster_has_builder_and_separation_of_powers():
    agents = check_agents.collect_agents()

    assert check_agents.REQUIRED_DELIVERY_AGENTS <= agents.keys()
    implementer = check_agents.parse_frontmatter(
        agents["product-implementer"].read_text(encoding="utf-8")
    )
    assert "Write" in implementer["tools"]
    assert "Edit" in implementer["tools"]
    captain = agents["captain"].read_text(encoding="utf-8")
    assert 'subagent_type="general-purpose"' not in captain
    assert "O implementer não aprova o próprio trabalho" in captain
