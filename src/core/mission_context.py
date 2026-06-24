"""Mission context for Bob's pre-debut operating state.

The mission context is not market data and not an execution permission. It is
the product/runtime posture Bob should understand before answering users.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .paths import project_path


MISSION_CONTEXT_PATH = project_path("config", "mission_context.json")
LEARNING_LOG_PATH = project_path("data", "learning_log.jsonl")


def _load_learning_lessons(max_lessons: int = 10) -> list[dict[str, Any]]:
    """Load lessons from learning_log.jsonl."""
    lessons_path = Path(LEARNING_LOG_PATH)
    if not lessons_path.exists():
        return []

    lessons: list[dict[str, Any]] = []
    try:
        for line in lessons_path.read_text(encoding="utf-8").strip().splitlines():
            if not line:
                continue
            try:
                lesson = json.loads(line)
                if isinstance(lesson, dict) and lesson.get("lesson_id"):
                    lessons.append(lesson)
            except (json.JSONDecodeError, TypeError):
                continue

        # Sort by recency and confidence
        lessons.sort(key=lambda l: (
            float(l.get("confidence", 0)),
            -(l.get("created_at", "")),
        ), reverse=True)
        return lessons[:max_lessons]
    except Exception:
        return []


def load_mission_context(path: str | Path | None = None) -> dict[str, Any]:
    """Load the mission context JSON, returning an empty dict if unavailable."""

    context_path = Path(path) if path is not None else MISSION_CONTEXT_PATH
    if not context_path.exists():
        return {}
    try:
        payload = json.loads(context_path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _append_key_values(lines: list[str], title: str, payload: dict[str, Any]) -> None:
    if not payload:
        return
    lines.append(title)
    for key, value in payload.items():
        if isinstance(value, (dict, list)):
            continue
        lines.append(f"- {key}: {value}")
    lines.append("")


def render_mission_context_for_prompt(path: str | Path | None = None) -> str:
    """Render mission context as a compact system-prompt preface for Bob."""

    data = load_mission_context(path)
    if not data:
        return ""

    identity = data.get("identity", {}) if isinstance(data.get("identity"), dict) else {}
    situation = (
        data.get("current_situation", {}) if isinstance(data.get("current_situation"), dict) else {}
    )
    mission = data.get("grand_mission", {}) if isinstance(data.get("grand_mission"), dict) else {}
    rules = data.get("operating_rules", [])
    rules = rules if isinstance(rules, list) else []
    agent_info = data.get("agent", {}) if isinstance(data.get("agent"), dict) else {}
    training = data.get("training", {}) if isinstance(data.get("training"), dict) else {}
    apprenticeship = (
        data.get("apprenticeship", {}) if isinstance(data.get("apprenticeship"), dict) else {}
    )

    lines: list[str] = [
        "=== MISSION CONTEXT - READ BEFORE RESPONDING ===",
        "",
        "## WHO YOU ARE",
    ]
    for line in identity.get("who_i_am", []):
        lines.append(f"- {line}")
    lines.append("")

    lines.append("## WHAT YOU ARE NOT")
    for line in identity.get("what_i_am_not", []):
        lines.append(f"- {line}")
    lines.append("")

    lines.append(f"## YOUR PHASE: {agent_info.get('phase', 'unknown').upper()}")
    if agent_info.get("phase_description"):
        lines.append(f"- {agent_info['phase_description']}")
    lines.append("")

    _append_key_values(lines, "## TRAINING AND LIMITS", training)

    if apprenticeship:
        lines.append("## TWO-WEEK IBKR APPRENTICESHIP")
        for key in ("name", "status", "start_date", "end_date", "duration_days"):
            if key in apprenticeship:
                lines.append(f"- {key}: {apprenticeship[key]}")
        if apprenticeship.get("role_language"):
            lines.append(f"- role_language: {apprenticeship['role_language']}")
        if apprenticeship.get("purpose"):
            lines.append(f"- purpose: {apprenticeship['purpose']}")
        for title, key in (
            ("Responsibilities", "responsibilities"),
            ("Prohibited claims", "prohibited_claims"),
            ("Success criteria", "success_criteria"),
        ):
            values = apprenticeship.get(key, [])
            if isinstance(values, list) and values:
                lines.append(f"{title}:")
                for value in values:
                    lines.append(f"- {value}")
        lines.append("")

    runtime = situation.get("runtime", {}) if isinstance(situation.get("runtime"), dict) else {}
    pipeline = situation.get("pipeline", {}) if isinstance(situation.get("pipeline"), dict) else {}
    broker = situation.get("broker", {}) if isinstance(situation.get("broker"), dict) else {}
    data_sources = (
        situation.get("data_sources", {}) if isinstance(situation.get("data_sources"), dict) else {}
    )

    _append_key_values(lines, "## CURRENT RUNTIME", runtime)
    _append_key_values(lines, "## PIPELINE QUALITY", pipeline)

    if broker:
        lines.append("## BROKER / PAPER MODE STATUS")
        for broker_name, broker_info in broker.items():
            if not isinstance(broker_info, dict):
                continue
            connection = broker_info.get("connection", "unknown")
            mode = broker_info.get("mode", "read_only_no_orders")
            port = broker_info.get("port", "unknown")
            source = broker_info.get("verification_source", "static_mission_context")
            static_source = source != "cockpit_portfolio_live"
            account_equity = (
                "runtime_snapshot_required"
                if static_source
                else broker_info.get("account_equity", "unknown")
            )
            positions_count = (
                "runtime_snapshot_required"
                if static_source
                else broker_info.get("positions_count", "unknown")
            )
            can_submit = broker_info.get("can_submit_orders", False)
            lines.append(
                f"- {broker_name.upper()}: connection={connection}; mode={mode}; "
                f"port={port}; account_equity={account_equity}; "
                f"positions_count={positions_count}; can_submit_orders={can_submit}"
            )
            if static_source:
                lines.append(
                    "  Runtime broker numbers must come from the IBKR portfolio snapshot/tool, "
                    "not from this static mission file."
                )
            if broker_info.get("note"):
                lines.append(f"  Note: {broker_info['note']}")
            if broker_name.lower() == "ibkr" and connection == "connected_paper":
                lines.append(
                    "  THIS IS A PAPER ACCOUNT. Live-money execution is disabled, "
                    "but paper order submission is enabled through submit_paper_order "
                    "when the paper execution gate is active. Use LMT orders only."
                )
                lines.append(
                    "  Broker proof rule: report order_id, broker status, filled quantity, "
                    "and avg fill price only from the submit_paper_order tool result."
                )
            elif broker_name.lower() == "ibkr" and connection == "connected_read_only":
                lines.append(
                    "  THIS IS A PAPER ACCOUNT. Real broker order submission is disabled, "
                    "but you CAN and MUST simulate paper trades via PaperJournal CLI "
                    "(scripts/paper_journal_cli.py). The journal IS your execution platform "
                    "for paper training. You are allowed to lose paper money — this is training."
                )
                lines.append(
                    "  Broker visibility: account equity and positions only. Do not claim "
                    "broker transaction history, order history, or live market data unless "
                    "a separate tool explicitly provides it."
                )
        lines.append("")

    # ── Paper trading mode ──
    paper_trading = situation.get("paper_trading", {}) if isinstance(situation, dict) else {}
    if isinstance(paper_trading, dict) and paper_trading.get("active"):
        lines.append("## PAPER TRADING MODE — ACTIVE")
        lines.append(f"- Mode: {paper_trading.get('mode', 'paper_simulation')}")
        lines.append(f"- Paper equity: {paper_trading.get('equity', 'unknown')}")
        lines.append(f"- Max position: {paper_trading.get('max_position_pct', 10)}% of equity")
        lines.append(f"- Max risk per trade: {paper_trading.get('max_risk_per_trade_pct', 2)}%")
        for rule in paper_trading.get("rules", []):
            lines.append(f"- RULE: {rule}")
    lines.append("")

    _append_key_values(lines, "## DATA SOURCES YOU MAY EXPLAIN", data_sources)

    lines.append("## YOUR GRAND MISSION")
    if mission.get("description"):
        lines.append(f"- {mission['description']}")
    lines.append("")
    lines.append("## DEBUT CRITERIA STATUS")
    for crit in mission.get("eight_criteria", []):
        if not isinstance(crit, dict):
            continue
        crit_status = crit.get("status", "pending")
        if crit_status == "proven":
            label = "[PROVEN]"
        elif crit_status == "instrumented":
            label = "[INSTRUMENTED]"
        else:
            label = "[PENDING]"
        lines.append(f"- {label} {crit.get('id', '?')}: {crit.get('name', '')}")
        if crit.get("what_it_means"):
            lines.append(f"  Means: {crit['what_it_means']}")
    # Compute summary dynamically from criteria array - never from static JSON string
    debut = _build_debut_summary(mission)
    lines.append(
        f"Progress: {debut['proven']}/{debut['total']} proven, "
        f"{debut['instrumented']}/{debut['total']} instrumented, "
        f"{debut['pending']}/{debut['total']} pending. "
        f"Readiness: {debut['readiness_pct']}%"
    )
    lines.append("")

    lines.append("## OPERATING RULES - NEVER VIOLATE")
    for i, rule in enumerate(rules, 1):
        lines.append(f"{i}. {rule}")
    lines.append("")

    # ── Learning: lessons from feedback loop ──
    lessons = _load_learning_lessons()
    if lessons:
        lines.append("## LESSONS LEARNED - CRITICAL FOR DECISIONS")
        lines.append("These lessons were extracted from YOUR past trades. DO NOT repeat mistakes.")
        lines.append("")

        # Group by category
        by_category: dict[str, list[dict]] = {}
        for lesson in lessons:
            category = lesson.get("category", "general")
            by_category.setdefault(category, []).append(lesson)

        for category, cat_lessons in by_category.items():
            lines.append(f"### {category.upper()}")
            for lesson in cat_lessons[:5]:  # Max 5 per category
                lines.append(f"- {lesson.get('title', 'Unknown')}")
                content = lesson.get("content", "")[:200]
                if content:
                    lines.append(f"  {content}")
                tickers = lesson.get("applicable_tickers", [])
                if tickers:
                    lines.append(f"  Applies to: {', '.join(tickers)}")
                lines.append("")

    lines.append("=== END MISSION CONTEXT ===")
    return "\n".join(lines)


def _build_debut_summary(mission: dict) -> dict[str, Any]:
    """Compute debut criteria summary from actual criteria status array.

    Derives proven/instrumented/pending counts and readiness_pct.
    Never reads the static string from the JSON - everything is computed
    from the individual criteria statuses so a stale static string cannot
    mask the real state.
    """
    criteria = mission.get("eight_criteria", [])
    criteria = criteria if isinstance(criteria, list) else []
    proven = sum(1 for c in criteria if isinstance(c, dict) and c.get("status") == "proven")
    instrumented = sum(
        1 for c in criteria if isinstance(c, dict) and c.get("status") == "instrumented"
    )
    pending = sum(1 for c in criteria if isinstance(c, dict) and c.get("status") == "pending")
    total = len(criteria)
    readiness_pct = round((proven / total * 100), 1) if total > 0 else 0.0

    return {
        "proven": proven,
        "instrumented": instrumented,
        "pending": pending,
        "total": total,
        "readiness_pct": readiness_pct,
    }


def mission_health_summary(path: str | Path | None = None) -> dict[str, Any]:
    """Health/details payload for the configured mission context.

    debut_criteria is always computed from the individual criteria statuses,
    not from the static criteria_summary string in the JSON.
    """
    data = load_mission_context(path)
    if not data:
        return {"status": "no_mission_context_file"}

    situation = data.get("current_situation", {})
    mission = data.get("grand_mission", {}) if isinstance(data.get("grand_mission"), dict) else {}
    return {
        "status": "loaded",
        "phase": data.get("agent", {}).get("phase", "unknown"),
        "phase_description": data.get("agent", {}).get("phase_description", ""),
        "training": data.get("training", {}),
        "apprenticeship": data.get("apprenticeship", {}),
        "broker": situation.get("broker", {}) if isinstance(situation, dict) else {},
        "paper_trading": situation.get("paper_trading", {}) if isinstance(situation, dict) else {},
        "debut_criteria": _build_debut_summary(mission),
    }


def get_mission_equity(path: str | Path | None = None) -> float:
    """Retorna o equity do broker ou paper trading configurado no mission_context.json.

    Default para 10000.0 se nao encontrado ou se houver erro.
    """
    data = load_mission_context(path)
    if not data:
        return 10000.0

    situation = data.get("current_situation", {})
    if not isinstance(situation, dict):
        return 10000.0

    # 1. Tentar ler do paper_trading
    try:
        pt = situation.get("paper_trading", {})
        if isinstance(pt, dict):
            eq_str = pt.get("equity")
            if eq_str:
                # Ex: "10000.00 USD"
                return float(str(eq_str).split()[0])
    except Exception:
        pass

    # 2. Tentar ler do broker.ibkr.account_equity
    try:
        ibkr = situation.get("broker", {}).get("ibkr", {})
        if isinstance(ibkr, dict):
            eq_str = ibkr.get("account_equity")
            if eq_str:
                return float(eq_str)
    except Exception:
        pass

    return 10000.0

