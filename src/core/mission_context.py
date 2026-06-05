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
        data.get("current_situation", {})
        if isinstance(data.get("current_situation"), dict)
        else {}
    )
    mission = data.get("grand_mission", {}) if isinstance(data.get("grand_mission"), dict) else {}
    rules = data.get("operating_rules", [])
    rules = rules if isinstance(rules, list) else []
    agent_info = data.get("agent", {}) if isinstance(data.get("agent"), dict) else {}
    training = data.get("training", {}) if isinstance(data.get("training"), dict) else {}

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

    runtime = situation.get("runtime", {}) if isinstance(situation.get("runtime"), dict) else {}
    pipeline = situation.get("pipeline", {}) if isinstance(situation.get("pipeline"), dict) else {}
    broker = situation.get("broker", {}) if isinstance(situation.get("broker"), dict) else {}
    data_sources = (
        situation.get("data_sources", {})
        if isinstance(situation.get("data_sources"), dict)
        else {}
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
            account_equity = broker_info.get("account_equity", "unknown")
            positions_count = broker_info.get("positions_count", "unknown")
            can_submit = broker_info.get("can_submit_orders", False)
            lines.append(
                f"- {broker_name.upper()}: connection={connection}; mode={mode}; "
                f"port={port}; account_equity={account_equity}; "
                f"positions_count={positions_count}; can_submit_orders={can_submit}"
            )
            if broker_info.get("note"):
                lines.append(f"  Note: {broker_info['note']}")
            if broker_name.lower() == "ibkr" and connection == "connected_read_only":
                lines.append(
                    "  User explanation: IBKR TWS is connected through localhost in "
                    "demo/paper-style read-only mode. You may explain account/position "
                    "visibility, but you must state you cannot submit or cancel orders."
                )
                lines.append(
                    "  Verified broker reads only: account equity and positions. Do not "
                    "claim broker transaction history, order history, live market data, "
                    "or execution capability unless a separate tool explicitly provides it."
                )
                lines.append(
                    "  Paper journal boundary: PaperJournal is an offline/manual thesis "
                    "tracker. It is not IBKR order history and it does not prove broker "
                    "execution or automatic execution logging."
                )
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
    instrumented = sum(1 for c in criteria if isinstance(c, dict) and c.get("status") == "instrumented")
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
        "broker": situation.get("broker", {}) if isinstance(situation, dict) else {},
        "debut_criteria": _build_debut_summary(mission),
    }
