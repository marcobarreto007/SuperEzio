"""The right rail had a ~600px void below the last card.

`/health/details` already reaches the browser every 10s — `health.js:89` stores
it in `SZ.state.healthDetails` — carrying circuit breakers, the cost guard,
providers and the GPUs behind the local brain. None of it had a UI, while the
panel pooled 49% empty space at 1440p.

This card renders that payload, and only that payload: a block whose data is
absent is skipped, never filled with a zero the backend did not send.

The front is exercised for real — `system-health.js` is loaded into node and its
`buildHTML()` called with live payload shapes — because a text assertion over
the source would pass while the card printed the wrong numbers.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SYSTEM_HEALTH_JS = ROOT / "frontend" / "js" / "system-health.js"
COCKPIT_JS = (ROOT / "frontend" / "js" / "cockpit.js").read_text(encoding="utf-8")
COCKPIT_CSS = (ROOT / "frontend" / "css" / "cockpit.css").read_text(encoding="utf-8")
INDEX_HTML = (ROOT / "frontend" / "index.html").read_text(encoding="utf-8")

_DRIVER = """
const fs = require('fs'), vm = require('vm');
let raw = '';
process.stdin.on('data', d => { raw += d; });
process.stdin.on('end', () => {
  const payload = JSON.parse(raw);
  const win = { SZ: { state: {}, subscribe() {} }, setInterval() {} };
  const ctx = {
    document: { readyState: 'loading', addEventListener() {} },
    window: win,
    console,
    setInterval() {},
  };
  ctx.globalThis = ctx;
  vm.createContext(ctx);
  vm.runInContext(fs.readFileSync(payload.script, 'utf8'), ctx);
  process.stdout.write(ctx.window.SZ.systemHealth.buildHTML(payload.details));
});
"""


def _build(details):
    """Drive the real frontend/js/system-health.js in node; return its HTML."""
    node = shutil.which("node") or pytest.skip("node is required to exercise system-health.js")
    proc = subprocess.run(
        [node, "-e", _DRIVER],
        input=json.dumps({"details": details, "script": str(SYSTEM_HEALTH_JS)}),
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert proc.returncode == 0, f"system-health.js failed under node: {proc.stderr}"
    return proc.stdout


_BREAKERS = [
    {
        "circuit": "data.finnhub",
        "state": "closed",
        "failures": 0,
        "total_failures": 0,
        "total_successes": 105,
    },
    {
        "circuit": "data.yfinance",
        "state": "closed",
        "failures": 0,
        "total_failures": 1,
        "total_successes": 10,
    },
]

_PAYLOAD = {
    "checks": {
        "gpu": {
            "status": "ok",
            "devices": [
                {
                    "id": 0,
                    "name": "NVIDIA GeForce RTX 2070",
                    "vram_mb": 8007,
                    "memory_used_mb": 6975,
                }
            ],
        },
        "providers_summary": {
            "primary": {
                "provider": "local_orchestrator",
                "role": "ceo",
                "model": "deepseek-v4-pro",
                "reachable": True,
                "status": "ok",
            },
            "experts": {
                "provider": "deepseek",
                "model": "deepseek-v4-flash",
                "status": "configured",
            },
            "optional_providers": {
                "glm": {"provider": "glm", "status": "unconfigured_missing_api_key"}
            },
        },
        "circuit_breakers": _BREAKERS,
        "cost_guard": {
            "daily_budget_usd": 10.0,
            "max_runs_per_day": 50,
            "cost_today_usd": 0.0,
            "runs_today": 0,
            "budget_remaining_usd": 10.0,
            "runs_remaining": 50,
        },
    },
    "mission": {"status": "loaded"},
}


def test_card_renders_the_circuit_breakers():
    html = _build(_PAYLOAD)
    assert "data.finnhub" in html
    assert "105" in html


def test_card_renders_the_cost_guard():
    html = _build(_PAYLOAD)
    assert "50" in html  # max_runs_per_day


def test_card_renders_the_providers():
    html = _build(_PAYLOAD)
    assert "deepseek-v4-pro" in html
    assert "deepseek-v4-flash" in html


def test_card_renders_the_local_brain_gpus():
    html = _build(_PAYLOAD)
    assert "RTX 2070" in html


def test_absent_payload_says_sem_dado_instead_of_inventing():
    assert "SEM DADO" in _build(None)


def test_missing_block_is_skipped_not_filled_with_zeroes():
    """A block with no data must vanish, not print a $0.00 the backend never sent."""
    html = _build({"checks": {"circuit_breakers": _BREAKERS}})
    assert "data.finnhub" in html
    assert "$0.00" not in html


def test_open_circuit_is_not_painted_healthy():
    """An open breaker means a data source is down; it must not render as is-ok."""
    html = _build(
        {
            "checks": {
                "circuit_breakers": [
                    {
                        "circuit": "data.finnhub",
                        "state": "open",
                        "failures": 3,
                        "total_failures": 4,
                        "total_successes": 105,
                    }
                ]
            }
        }
    )
    assert "data.finnhub" in html
    assert "is-ok" not in html


def test_card_is_wired_into_the_panel():
    assert 'id="expert-card-health"' in INDEX_HTML
    assert 'id="health-body"' in INDEX_HTML
    assert "js/system-health.js" in INDEX_HTML


# ---------------------------------------------------------------------------
# Capital & risk card — values it fetched and threw away.
# ---------------------------------------------------------------------------


def test_risk_budget_comes_from_the_payload_not_a_hardcoded_literal():
    """The card printed a literal "$15 CAD" while risk_budget_cad was discarded.

    It asserted a number the backend never sent, which is worse than not showing
    it: a reader cannot tell an agreed protocol value from a stale constant.
    """
    assert COCKPIT_JS.count("riskBudget") >= 2, "risk_budget_cad must be rendered, not dropped"
    assert "$15 CAD</strong>" not in COCKPIT_JS


def test_capital_card_renders_the_profit_it_already_computes():
    """total_profit was parsed and formatted into profitStr, then never used."""
    assert COCKPIT_JS.count("profitStr") >= 2, "the computed P&L must reach the card"


# ---------------------------------------------------------------------------
# The card that absorbs the rail's leftover height.
# ---------------------------------------------------------------------------


def test_health_card_grows_but_never_shrinks_below_its_content():
    """`flex: 1 1 auto` squashed the card and clipped the payload.

    Measured with the default shrink: 71px lost at 1080p, 141px at 1440x900 and
    187px at 1366x768. The rail is `overflow-y: auto`, so refusing to shrink
    makes it scroll instead — which shows the data rather than hiding it.
    """
    rule = COCKPIT_CSS.split("#expert-card-health {", 1)[1].split("}", 1)[0]
    assert "flex: 1 0 auto" in rule
    assert "flex-shrink: 1" not in rule
