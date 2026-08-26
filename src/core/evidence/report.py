"""Generate a self-contained HTML evidence report."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .run import EvidenceRun

_CSS = """
* { margin:0; padding:0; box-sizing:border-box; }
body { font-family:'Segoe UI', system-ui, sans-serif; background:#0a0e0b; color:#d0d5d0; padding:24px; max-width:900px; margin:auto; }
h1 { color:#4ade80; font-size:1.5em; margin-bottom:4px; }
h2 { color:#86efac; font-size:1.1em; margin:20px 0 10px; border-bottom:1px solid #1a2a1a; padding-bottom:4px; }
.card { background:#111a11; border:1px solid #1a2a1a; border-radius:8px; padding:14px; margin:10px 0; }
.meta { color:#608060; font-size:0.85em; }
.pass { color:#4ade80; } .fail { color:#f87171; } .warn { color:#fbbf24; }
.badge { display:inline-block; padding:2px 8px; border-radius:4px; font-size:0.8em; font-weight:600; margin:2px; }
.badge-pass { background:#14532d; color:#4ade80; }
.badge-fail { background:#7f1d1d; color:#f87171; }
.badge-warn { background:#713f12; color:#fbbf24; }
.timeline { list-style:none; }
.timeline li { padding:6px 0; border-left:2px solid #1a3a1a; padding-left:12px; margin-left:6px; font-size:0.9em; }
.timeline li.error { border-left-color:#7f1d1d; }
table { width:100%; border-collapse:collapse; font-size:0.9em; }
th, td { text-align:left; padding:6px 8px; border-bottom:1px solid #1a2a1a; vertical-align:top; }
th { color:#86efac; }
pre { background:#0a150a; padding:12px; border-radius:6px; overflow-x:auto; font-size:0.85em; white-space:pre-wrap; }
.footer { margin-top:30px; padding-top:12px; border-top:1px solid #1a2a1a; color:#406040; font-size:0.75em; text-align:center; }
"""


def generate_html_report(run: EvidenceRun, run_dir: Path) -> str:
    """Generate a self-contained HTML report and return the path."""
    data = run.to_dict()

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>SuperEzio Evidence - {_esc(run.run_id)}</title>
<style>{_CSS}</style>
</head>
<body>

<h1>SuperEzio Evidence Report</h1>
<p class="meta">Run: {_esc(run.run_id)}<br>Created: {_esc(run.created_at)}<br>Prompt: {_esc(run.prompt)}</p>

{_section_sources(data)}
{_section_experts(data)}
{_section_risk(data)}
{_section_response(data)}
{_section_timeline(data)}
{_section_errors(data)}

<div class="footer">
SuperEzio v4.0.0 - Evidence Mode - Educational framework, not financial advice.
</div>

</body>
</html>"""

    report_path = run_dir / "report.html"
    report_path.write_text(html, encoding="utf-8")
    return str(report_path)


def _esc(value: Any) -> str:
    """HTML-escape a value."""
    text = "" if value is None else str(value)
    return (
        text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")
    )


def _num(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _section_sources(data: dict[str, Any]) -> str:
    sources = data.get("sources", {})
    candidates = data.get("candidates", [])
    price = data.get("price_at_analysis", {})

    rows = ""
    if price:
        rows += f"""<tr><td>Price</td><td>{_esc(price.get("ticker", "?"))}</td>
            <td><span class="badge badge-pass">${_esc(price.get("price", "?"))}</span></td>
            <td>{_esc(price.get("source", "?"))}</td></tr>"""

    for src in sources.values():
        status = src.get("status", "?")
        badge_cls = (
            "badge-pass"
            if status == "ok"
            else ("badge-warn" if "fallback" in str(status) else "badge-fail")
        )
        rows += f"""<tr><td>{_esc(src.get("capability", "?"))}</td>
            <td>{_esc(src.get("provider", "?"))}</td>
            <td><span class="badge {badge_cls}">{_esc(status)}</span></td>
            <td class="meta">{_esc(str(src.get("timestamp", ""))[:19])}</td></tr>"""

    cand_info = f"<p class='meta'>{len(candidates)} candidates analyzed</p>" if candidates else ""

    return f"""<h2>Sources & Data</h2>
<div class="card">
{cand_info}
<table>{rows or '<tr><td colspan="4">No sources recorded</td></tr>'}</table>
</div>"""


def _section_experts(data: dict[str, Any]) -> str:
    experts = data.get("experts", {})
    if not experts:
        return ""

    rows = ""
    for name, exp in experts.items():
        verdict = exp.get("verdict", "?")
        # Skip empty experts: no verdict ("?" or "") AND no Bob-readable
        # summary means the entry carries no content — rendering it would
        # show a meaningless "? 0%" row (measured 2026-08-24: the empty
        # red_team_agent_1 / judge / auditor entries).
        verdict_empty = not str(verdict).strip() or str(verdict).strip() == "?"
        if verdict_empty and not str(exp.get("bob_readable", "")).strip():
            continue
        conf = _num(exp.get("confidence", 0))
        color = "#4ade80" if conf >= 70 else ("#fbbf24" if conf >= 40 else "#f87171")
        rows += f"""<tr>
            <td>{_esc(name)}</td>
            <td>{_esc(verdict)}</td>
            <td style="color:{color}">{conf:.0f}%</td>
            <td class="meta">{_esc(exp.get("bob_readable", ""))}</td>
        </tr>"""

    return f"""<h2>Expert Analysis</h2>
<div class="card">
<table>
<tr><th>Expert</th><th>Verdict</th><th>Confidence</th><th>Summary</th></tr>
{rows}
</table>
</div>"""


def _section_risk(data: dict[str, Any]) -> str:
    risk = data.get("risk", {})
    if not risk:
        return ""

    tokens = risk.get("ghost_tokens", [])
    blocked = bool(risk.get("blocked", False))
    confidence = _num(risk.get("confidence", 0))
    uncertainty = _num(risk.get("uncertainty", 0))

    token_tags = " ".join(
        f'<span class="badge badge-{"fail" if blocked else "warn"}">{_esc(t)}</span>'
        for t in (tokens or [])
    )

    return f"""<h2>Risk Firewall (SDCA)</h2>
<div class="card">
<p>Blocked: <span class="{"fail" if blocked else "pass"}">{blocked}</span></p>
<p>Confidence: {confidence:.0f}% | Uncertainty: {uncertainty:.0f}%</p>
<p>Ghost Tokens: {token_tags or "None"}</p>
</div>"""


def _section_response(data: dict[str, Any]) -> str:
    response = data.get("response", "")
    if not response:
        return "<h2>Response</h2><div class='card'><p class='warn'>No response captured</p></div>"

    return f"""<h2>CEO Response</h2>
<div class="card">
<pre>{_esc(response)}</pre>
</div>"""


def _section_timeline(data: dict[str, Any]) -> str:
    timeline = data.get("timeline", [])
    if not timeline:
        return ""

    items = ""
    for item in timeline:
        cls = "error" if item.get("event") == "error" else ""
        elapsed = _num(item.get("elapsed_ms", 0))
        time_str = f"{elapsed / 1000:.1f}s" if elapsed else ""
        items += f'<li class="{cls}"><span class="meta">{time_str}</span> {_esc(item.get("event", "?"))}</li>'

    return f"""<h2>Pipeline Timeline</h2>
<div class="card">
<ol class="timeline">{items}</ol>
</div>"""


def _section_errors(data: dict[str, Any]) -> str:
    errors = data.get("errors", [])
    if not errors:
        return ""

    items = ""
    for err in errors:
        items += f"""<tr class="fail">
            <td>{_esc(err.get("phase", "?"))}</td>
            <td>{_esc(err.get("error", "?"))}</td>
            <td class="meta">{_esc(str(err.get("timestamp", ""))[:19])}</td>
        </tr>"""

    return f"""<h2>Errors</h2>
<div class="card">
<table>
<tr><th>Phase</th><th>Error</th><th>Time</th></tr>
{items}
</table>
</div>"""
