"""Gate de integridade do exercito de agentes (inspirado no check.py de
anthropics/financial-services — ver docs/architecture/ANTHROPIC_FS_DEEP_DIVE.md).

Valida que toda referencia cruzada entre agentes, skills e comandos EXISTE:
1. Todo .claude/agents/*.md tem frontmatter valida com name + description + tools.
2. Todo .claude/skills/<slug>/SKILL.md existe e tem frontmatter com name + description.
3. Toda skill citada em agentes/comandos (Skill("x"), `x` em linha com "skill",
   .claude/skills/<x>) resolve para uma skill existente.
4. Todo subagent_type="x" e roster de agentes citado resolve para um agente existente
   (ou builtin conhecido do Claude Code).

Exit codes: 0 limpo / 1 issues encontrados (herdados do check.py da Anthropic).
Uso: python scripts/check_agents.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
AGENTS_DIR = ROOT / ".claude" / "agents"
SKILLS_DIR = ROOT / ".claude" / "skills"
COMMANDS_DIR = ROOT / ".claude" / "commands"

# Subagentes builtins do Claude Code (nao sao arquivos nossos)
BUILTIN_SUBAGENTS = {"general-purpose", "Explore", "Plan", "claude", "fork"}
REQUIRED_DELIVERY_AGENTS = {
    "product-delivery-orchestrator",
    "product-implementer",
    "ai-eval-verifier",
    "reliability-sre-operator",
    "release-readiness-manager",
}

KEBAB = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)+$")
SKILL_CALL = re.compile(r'Skill\(\s*"([a-z0-9-]+)"')
SKILLS_PATH = re.compile(r"\.claude/skills/([a-z0-9-]+)")
SUBAGENT_TYPE = re.compile(r'subagent_type="([a-z0-9-]+)"')
BACKTICKED = re.compile(r"`([a-z0-9]+(?:-[a-z0-9]+)+)`")
SKILL_WORD = re.compile(r"\bskill", re.IGNORECASE)
AGENT_DISPATCH = re.compile(r"Agent\(\s*subagent_type")


def parse_frontmatter(text: str) -> dict[str, str]:
    """Extrai pares chave: valor do bloco --- ... --- (valores simples)."""
    if not text.startswith("---"):
        return {}
    end = text.find("\n---", 3)
    if end == -1:
        return {}
    fm: dict[str, str] = {}
    for line in text[4:end].splitlines():
        if ":" in line:
            key, _, value = line.partition(":")
            fm[key.strip()] = value.strip()
    return fm


def collect_agents() -> dict[str, Path]:
    return {p.stem: p for p in sorted(AGENTS_DIR.glob("*.md"))}


def collect_skills() -> dict[str, Path]:
    return {p.parent.name: p for p in sorted(SKILLS_DIR.glob("*/SKILL.md"))}


def skill_refs_in_text(text: str) -> set[str]:
    refs: set[str] = set()
    refs.update(SKILL_CALL.findall(text))
    refs.update(SKILLS_PATH.findall(text))
    for line in text.splitlines():
        if SKILL_WORD.search(line):
            refs.update(BACKTICKED.findall(line))
    return refs


def agent_refs_in_text(text: str) -> set[str]:
    return set(SUBAGENT_TYPE.findall(text))


def check() -> list[str]:
    issues: list[str] = []
    agents = collect_agents()
    skills = collect_skills()

    for name in sorted(REQUIRED_DELIVERY_AGENTS - agents.keys()):
        issues.append(f"delivery: agente obrigatorio '{name}' ausente")

    implementer = agents.get("product-implementer")
    if implementer:
        tools = parse_frontmatter(implementer.read_text(encoding="utf-8")).get("tools", "")
        if "Write" not in tools or "Edit" not in tools:
            issues.append("delivery: product-implementer precisa de Write e Edit")

    captain = agents.get("captain")
    if captain and 'subagent_type="general-purpose"' in captain.read_text(encoding="utf-8"):
        issues.append("delivery: captain nao pode delegar ownership a general-purpose")

    # 1. Frontmatter dos agentes
    for name, path in agents.items():
        fm = parse_frontmatter(path.read_text(encoding="utf-8"))
        for field in ("name", "description", "tools"):
            if not fm.get(field):
                issues.append(f"agente {path.name}: frontmatter sem campo '{field}'")
        if fm.get("name") and fm["name"] != name:
            issues.append(
                f"agente {path.name}: name '{fm['name']}' difere do arquivo"
            )

    # 2. Frontmatter das skills
    for name, path in skills.items():
        fm = parse_frontmatter(path.read_text(encoding="utf-8"))
        for field in ("name", "description"):
            if not fm.get(field):
                issues.append(f"skill {name}: SKILL.md sem campo '{field}'")
        if fm.get("name") and fm["name"] != name:
            issues.append(f"skill {name}: name '{fm['name']}' difere da pasta")

    # Pastas de skill sem SKILL.md
    for folder in sorted(SKILLS_DIR.iterdir()):
        if folder.is_dir() and folder.name not in skills:
            issues.append(f"skill {folder.name}: pasta existe mas SKILL.md ausente")

    # 3+4. Referencias cruzadas em agentes e comandos
    sources = {**agents}
    if COMMANDS_DIR.exists():
        sources.update({f"cmd:{p.stem}": p for p in sorted(COMMANDS_DIR.glob("*.md"))})
    for src, path in sources.items():
        text = path.read_text(encoding="utf-8")
        for ref in sorted(skill_refs_in_text(text)):
            if ref not in skills:
                issues.append(f"{src}: cita skill '{ref}' que nao existe")
        for ref in sorted(agent_refs_in_text(text)):
            if ref not in agents and ref not in BUILTIN_SUBAGENTS:
                issues.append(f"{src}: dispara agente '{ref}' que nao existe")

    return issues


def main() -> int:
    issues = check()
    agents_n = len(collect_agents())
    skills_n = len(collect_skills())
    if issues:
        print(f"CHECK AGENTS: {len(issues)} issue(s) ({agents_n} agentes, {skills_n} skills)")
        for issue in issues:
            print(f"  - {issue}")
        return 1
    print(f"CHECK AGENTS: clean ({agents_n} agentes, {skills_n} skills, 0 issues)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
