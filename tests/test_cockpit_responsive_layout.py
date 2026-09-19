"""Cockpit shell must fit a laptop and a phone, not only a 1920 terminal.

The live DOM at 1366x768 (Windows 1080p at 125%) had a dead zone: the only
breakpoints were 1100px (slight rail shrink) and 860px (phone stack). Between
them the 380px expert rail, flex-shrink:0 price cells, 88+96px oscillator
panes, two + Trade buttons and the floating control-panel ate the chart.
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COCKPIT_CSS = (ROOT / "frontend" / "css" / "cockpit.css").read_text(encoding="utf-8")
CONTROL_CSS = (ROOT / "frontend" / "css" / "control-panel.css").read_text(encoding="utf-8")
COCKPIT_JS = (ROOT / "frontend" / "js" / "cockpit.js").read_text(encoding="utf-8")
CHART_JS = (ROOT / "frontend" / "js" / "chart.js").read_text(encoding="utf-8")


def _first_rule(css: str, selector: str) -> str:
    token = selector + " {"
    return css.split(token, 1)[1].split("}", 1)[0]


def _media_block(css: str, query: str) -> str:
    token = f"@media {query}"
    assert token in css, f"missing {token}"
    rest = css.split(token, 1)[1]
    # Take until the next @media at the same nesting depth, not a nested one.
    # These files keep queries sequential at the top level.
    nxt = rest.find("\n@media ")
    return rest if nxt < 0 else rest[:nxt]


def test_laptop_breakpoint_exists_before_phone_stack():
    assert "@media (max-width: 1680px)" in COCKPIT_CSS
    assert COCKPIT_CSS.index("@media (max-width: 1680px)") < COCKPIT_CSS.index(
        "@media (max-width: 860px)"
    )


def test_laptop_rail_is_narrower_than_desktop_380():
    block = _media_block(COCKPIT_CSS, "(max-width: 1680px)")
    assert ".app-main" in block
    assert "280px" in block
    assert "380px" not in block.split(".app-main", 1)[1].split("}", 1)[0]


def test_topbar_clears_the_docked_bob_tab():
    """app-main already pads 32px; the topbar did not, so ops sat under Bob."""
    rule = _first_rule(COCKPIT_CSS, ".topbar")
    assert "padding-right: 44px" in rule


def test_connection_text_ellipsizes_instead_of_shoving_icons():
    rule = _first_rule(COCKPIT_CSS, ".topbar__conn-text")
    assert "text-overflow: ellipsis" in rule
    assert "overflow: hidden" in rule
    laptop = _media_block(COCKPIT_CSS, "(max-width: 1680px)")
    assert ".topbar__conn-text" in laptop
    assert "max-width:" in laptop


def test_market_header_prices_shrink_on_laptop():
    laptop = _media_block(COCKPIT_CSS, "(max-width: 1680px)")
    assert ".market-header__prices" in laptop
    assert "flex-shrink: 1" in laptop
    assert ".profile-text" in COCKPIT_CSS
    profile = _first_rule(COCKPIT_CSS, ".profile-text")
    assert "white-space: nowrap" in profile
    assert "text-overflow: ellipsis" in profile


def test_oscillator_panes_are_css_not_inline_locked():
    assert "chart-osc-pane" in CHART_JS
    assert "flex:0 0 88px" not in CHART_JS
    assert "flex:0 0 96px" not in CHART_JS
    assert ".chart-osc-pane" in COCKPIT_CSS
    assert "(max-height: 900px)" in COCKPIT_CSS


def test_paper_trade_is_reachable_from_both_cards():
    """The Mangala ticket is product, not layout — the laptop pass deleted it.

    19/09: this file used to pin `tradeFormHTML("mangala") not in COCKPIT_JS`,
    enshrining the deletion as if it were a layout consequence. It never was:
    both "+ Trade" buttons live inside rail cards, and the rail is a fixed-width
    grid column (280px at 1366/1440/1680, 380px at 1920) — a button inside a
    card cannot widen the chart column. Reverted by the operator.
    """
    assert 'tradeFormHTML("f51")' in COCKPIT_JS
    assert COCKPIT_JS.count('tradeFormHTML("mangala")') >= 2, (
        "both Mangala render paths (no-data and loaded) must keep their ticket"
    )


def test_status_bar_labels_ellipsize_instead_of_overlapping():
    """Shrinking a nowrap label with no ellipsis paints it over the neighbour.

    Measured before the fix: +4.7px of overlap at 900, +29.8px at 860, +194px at
    390 — and below 860px the bar is position:fixed, so the smear stayed on screen.
    """
    rule = _first_rule(COCKPIT_CSS, ".bot-bar__item")
    assert "overflow: hidden" in rule
    assert "text-overflow: ellipsis" in rule


def test_collapsed_control_panel_docks_to_the_status_bar():
    assert ".control-panel:has(" in CONTROL_CSS
    assert "bottom: 0" in CONTROL_CSS


def test_phone_stack_still_drops_the_rail_under_the_chart():
    phone = _media_block(COCKPIT_CSS, "(max-width: 860px)")
    app = phone.split(".app-main {", 1)[1].split("}", 1)[0]
    assert "grid-template-columns: 1fr" in app


def test_layout_guard_covers_windows_laptop_widths():
    from scripts.layout_guard import DEFAULT_WIDTHS

    for width in (1920, 1536, 1366):
        assert width in DEFAULT_WIDTHS
