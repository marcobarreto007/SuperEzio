"""Layout guard — live-DOM invariants for the cockpit at real viewport widths.

The cockpit must not overflow horizontally, must not let the docked Bob chat
tab cover the right rail, must clamp the chart zone column and must not clip
the orders mirror vertically. Those four defects were only visible in a real
browser at real widths (a full_page screenshot re-expands the viewport and
lies), so this script measures the live DOM instead of trusting pixels.

Usage:
    python scripts/layout_guard.py
    python scripts/layout_guard.py --headed --widths 1440,1024,320
    python scripts/layout_guard.py --bob-open      # also probe the open panel

Invariants per width (1440/1280/1024/834/768/600/390/320):
    A1  documentElement.scrollWidth <= innerWidth (and .app-main inside it)
    A2  computed .app-main min-width === 0px
    A3  .chart-zone has no horizontal overflow (scrollWidth <= clientWidth+1)
    A4  .chart-zone computed grid columns fit inside clientWidth
    A5  hit test for .expert-card__verdict / .bot-bar__item / .cockpit-empty:
        elementFromPoint(centre) is the element or a descendant (never the
        docked #bob-chat-tab), and the element does not overlap that tab
    A7  every .cockpit-empty stays inside the ancestors that clip it
    A7b the clipped .orders-mirror keeps its own header/body/lists inside its
        padding box (the centred 9px body row used to cut the list in two)
    A8  #f51-verdict reads READY and wins the hit test

Screenshots are taken WITHOUT full_page (see above). Exit code 0 only when
every invariant is green at every width.
"""

from __future__ import annotations

import argparse
import contextlib
import json
import sys
import time
from pathlib import Path
from typing import Any

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BASE_URL = "http://127.0.0.1:8002"
DEFAULT_WIDTHS = (1920, 1536, 1440, 1366, 1280, 1024, 960, 900, 834, 768, 600, 390, 320)
DEFAULT_HEIGHT = 900
SETTLE_MS = 1500

_PROBE_JS = r"""
() => {
  const px = (v) => { const m = String(v).match(/-?\d+(?:\.\d+)?/g); return m ? m.map(Number) : []; };
  const rect = (el) => {
    const r = el.getBoundingClientRect();
    return {left: r.left, top: r.top, right: r.right, bottom: r.bottom, width: r.width, height: r.height};
  };
  const overlap = (a, b) => Math.max(0, Math.min(a.right, b.right) - Math.max(a.left, b.left))
    * Math.max(0, Math.min(a.bottom, b.bottom) - Math.max(a.top, b.top));
  const desc = (el) => !el ? 'null' : (el.tagName ? el.tagName.toLowerCase() : '?')
    + (el.id ? '#' + el.id : '')
    + (typeof el.className === 'string' && el.className.trim() ? '.' + el.className.trim().split(/\s+/).join('.') : '');

  const appMain = document.querySelector('.app-main');
  const chartZone = document.querySelector('.chart-zone');
  const tab = document.getElementById('bob-chat-tab');
  const tabRect = tab ? rect(tab) : null;

  const box = (el) => {
    if (!el) return null;
    const cs = getComputedStyle(el);
    return {
      selector: desc(el),
      rect: rect(el),
      clientWidth: el.clientWidth,
      scrollWidth: el.scrollWidth,
      clientHeight: el.clientHeight,
      scrollHeight: el.scrollHeight,
      minWidth: cs.minWidth,
      maxHeight: cs.maxHeight,
      overflowX: cs.overflowX,
      overflowY: cs.overflowY,
      alignItems: cs.alignItems,
      gridColumns: cs.gridTemplateColumns,
      gridColumnPx: px(cs.gridTemplateColumns)
    };
  };

  const hits = [];
  ['.expert-card__verdict', '.bot-bar__item', '.cockpit-empty'].forEach((sel) => {
    document.querySelectorAll(sel).forEach((el) => {
      const r = rect(el);
      const entry = {selector: sel, element: desc(el), rect: r, tabOverlap: tabRect ? overlap(r, tabRect) : 0};
      if (r.width <= 0 || r.height <= 0) {
        entry.skipped = 'invisible';
        hits.push(entry);
        return;
      }
      const cx = r.left + r.width / 2;
      const cy = r.top + r.height / 2;
      entry.cx = cx;
      entry.cy = cy;
      entry.inViewport = cx >= 0 && cy >= 0 && cx <= window.innerWidth && cy <= window.innerHeight;
      if (!entry.inViewport) {
        entry.skipped = 'centre-outside-viewport';
        hits.push(entry);
        return;
      }
      const hit = document.elementFromPoint(cx, cy);
      entry.hit = desc(hit);
      entry.ok = !!(hit && (hit === el || el.contains(hit)));
      hits.push(entry);
    });
  });

  const empty = [];
  document.querySelectorAll('.cockpit-empty').forEach((el) => {
    const r = rect(el);
    const clippers = [];
    let n = el.parentElement;
    while (n && n !== document.documentElement) {
      const cs = getComputedStyle(n);
      const clipX = cs.overflowX !== 'visible';
      const clipY = cs.overflowY !== 'visible';
      if (clipX || clipY) {
        clippers.push({selector: desc(n), clipX: clipX, clipY: clipY, overflowY: cs.overflowY, rect: rect(n)});
      }
      n = n.parentElement;
    }
    empty.push({
      element: desc(el),
      text: (el.textContent || '').slice(0, 80),
      rect: r,
      visible: r.width > 0 && r.height > 0,
      clippers: clippers
    });
  });

  const f51 = document.getElementById('f51-verdict');
  let f51Hit = null;
  if (f51) {
    const r = rect(f51);
    const cx = r.left + r.width / 2;
    const cy = r.top + r.height / 2;
    const inside = cx >= 0 && cy >= 0 && cx <= window.innerWidth && cy <= window.innerHeight;
    const hit = inside ? document.elementFromPoint(cx, cy) : null;
    f51Hit = {
      text: (f51.textContent || '').trim(),
      rect: r,
      cx: cx,
      cy: cy,
      inViewport: inside,
      hit: desc(hit),
      ok: !!(hit && (hit === f51 || f51.contains(hit)))
    };
  }

  const panel = document.querySelector('.bob-chat__panel');

  /* Orders mirror: the body row is centred in a 1fr track (charts.css) while
     the body keeps its content height, so the clipped mirror painted the
     lists half above / half below its own box. */
  const mirror = document.querySelector('.orders-mirror');
  let mirrorBox = null;
  if (mirror) {
    const mcs = getComputedStyle(mirror);
    const mr = rect(mirror);
    const padTop = parseFloat(mcs.paddingTop) || 0;
    const padRight = parseFloat(mcs.paddingRight) || 0;
    const padBottom = parseFloat(mcs.paddingBottom) || 0;
    const padLeft = parseFloat(mcs.paddingLeft) || 0;
    const children = [];
    ['.orders-mirror__header', '.orders-mirror__body', '.orders-list', '.trade-history-list'].forEach((sel) => {
      const el = mirror.querySelector(sel);
      if (!el) return;
      const cr = rect(el);
      children.push({
        selector: desc(el),
        rect: cr,
        visible: cr.width > 0 && cr.height > 0,
        alignSelf: getComputedStyle(el).alignSelf
      });
    });
    mirrorBox = {
      selector: desc(mirror),
      rect: mr,
      paddingBox: {
        left: mr.left + padLeft, top: mr.top + padTop,
        right: mr.right - padRight, bottom: mr.bottom - padBottom
      },
      rows: mcs.gridTemplateRows,
      maxHeight: mcs.maxHeight,
      alignItems: mcs.alignItems,
      clips: mcs.overflowY !== 'visible',
      children: children
    };
  }

  return {
    innerWidth: window.innerWidth,
    innerHeight: window.innerHeight,
    docScrollWidth: document.documentElement.scrollWidth,
    docScrollHeight: document.documentElement.scrollHeight,
    bodyScrollWidth: document.body.scrollWidth,
    appMain: box(appMain),
    chartZone: box(chartZone),
    tab: tabRect ? {rect: tabRect, computedWidth: getComputedStyle(tab).width} : null,
    panelWidth: panel ? rect(panel).width : null,
    hits: hits,
    cockpitEmpty: empty,
    mirror: mirrorBox,
    f51: f51Hit
  };
}
"""


def _collect_failures(probe: dict[str, Any]) -> dict[str, list[str]]:
    """Turn one width's raw DOM probe into per-invariant failures."""
    out: dict[str, list[str]] = {}
    inner = probe["innerWidth"]

    def fail(key: str, msg: str) -> None:
        out.setdefault(key, []).append(msg)

    # A1 — no horizontal overflow of the document / app shell
    if probe["docScrollWidth"] > inner:
        fail("A1", f"documentElement.scrollWidth={probe['docScrollWidth']} > innerWidth={inner}")
    app = probe["appMain"]
    if app and app["rect"]["right"] > inner + 1:
        fail("A1", f".app-main right={round(app['rect']['right'], 1)} > innerWidth={inner}")
    if app and app["rect"]["left"] < -1:
        fail("A1", f".app-main left={round(app['rect']['left'], 1)} < 0")

    # A2 — the old min-width landmine must be gone
    if app and app["minWidth"] != "0px":
        fail("A2", f".app-main min-width computes to {app['minWidth']}")

    # A3 — chart zone must not overflow horizontally
    zone = probe["chartZone"]
    if zone:
        if zone["scrollWidth"] > zone["clientWidth"] + 1:
            fail(
                "A3",
                f".chart-zone scrollWidth={zone['scrollWidth']} > clientWidth={zone['clientWidth']}",
            )
        # A4 — the computed column must fit the box (implicit columns are
        # sized by min-content and blow past clientWidth when unclamped)
        too_wide = [c for c in zone["gridColumnPx"] if c > zone["clientWidth"] + 1]
        if too_wide:
            fail(
                "A4",
                f".chart-zone column(s) {too_wide} exceed clientWidth={zone['clientWidth']}",
            )

    # A5 — hit tests: nothing important may sit under the docked Bob chat tab
    for hit in probe["hits"]:
        if hit.get("skipped") in ("invisible",):
            continue
        if hit.get("tabOverlap", 0) > 0.5:
            fail(
                "A5",
                f"{hit['element']} overlaps #bob-chat-tab by {round(hit['tabOverlap'], 1)}px^2",
            )
        if hit.get("skipped") == "centre-outside-viewport":
            continue
        if not hit.get("ok"):
            fail(
                "A5",
                f"{hit['element']} centre ({round(hit['cx'])},{round(hit['cy'])}) hits "
                f"{hit.get('hit')} instead of itself",
            )

    # A7 — no .cockpit-empty clipped by its ancestors
    visible_empty = [e for e in probe["cockpitEmpty"] if e["visible"]]
    for entry in visible_empty:
        r = entry["rect"]
        for clip in entry["clippers"]:
            cr = clip["rect"]
            if clip["clipY"] and (r["top"] < cr["top"] - 1 or r["bottom"] > cr["bottom"] + 1):
                fail(
                    "A7",
                    f"{entry['element']} top={round(r['top'], 1)} bottom={round(r['bottom'], 1)} "
                    f"outside clipping {clip['selector']} (overflow-y:{clip['overflowY']}) "
                    f"top={round(cr['top'], 1)} bottom={round(cr['bottom'], 1)}",
                )
            if clip["clipX"] and (r["left"] < cr["left"] - 1 or r["right"] > cr["right"] + 1):
                fail(
                    "A7",
                    f"{entry['element']} left={round(r['left'], 1)} right={round(r['right'], 1)} "
                    f"outside clipping {clip['selector']} "
                    f"left={round(cr['left'], 1)} right={round(cr['right'], 1)}",
                )

    # A7b — the orders mirror clips (overflow:hidden); its own body/lists must
    # stay inside the box it clips, otherwise the list is cut above and below.
    mirror = probe.get("mirror")
    if mirror and mirror["clips"]:
        pb = mirror["paddingBox"]
        for child in mirror["children"]:
            if not child["visible"]:
                continue
            cr = child["rect"]
            if cr["top"] < pb["top"] - 1 or cr["bottom"] > pb["bottom"] + 1:
                fail(
                    "A7b",
                    f"{child['selector']} top={round(cr['top'], 1)} bottom={round(cr['bottom'], 1)} "
                    f"outside the clipping .orders-mirror padding box "
                    f"(rows={mirror['rows']}, max-height={mirror['maxHeight']}, "
                    f"align-items={mirror['alignItems']}) top={round(pb['top'], 1)} "
                    f"bottom={round(pb['bottom'], 1)}",
                )
            if cr["left"] < pb["left"] - 1 or cr["right"] > pb["right"] + 1:
                fail(
                    "A7b",
                    f"{child['selector']} left={round(cr['left'], 1)} right={round(cr['right'], 1)} "
                    f"outside the clipping .orders-mirror padding box "
                    f"left={round(pb['left'], 1)} right={round(pb['right'], 1)}",
                )

    # A8 — the F51 verdict reads READY in full and is not covered
    f51 = probe["f51"]
    if not f51:
        fail("A8", "#f51-verdict not found")
    else:
        if f51["text"] != "READY":
            fail("A8", f"#f51-verdict text is {f51['text']!r}, expected 'READY'")
        if not f51["inViewport"]:
            fail("A8", "#f51-verdict centre is outside the viewport")
        elif not f51["ok"]:
            fail("A8", f"#f51-verdict hit test resolved to {f51['hit']}")

    return out


def _console_collector(bucket: list[str]):
    """Build a console listener bound to one width's bucket (no loop capture)."""

    def _collect(msg) -> None:
        if msg.type == "error":
            bucket.append(msg.text)

    return _collect


def run(
    base_url: str, widths: list[int], height: int, headed: bool, bob_open: bool, shot_dir: Path
) -> dict[str, Any]:
    results: list[dict[str, Any]] = []
    shot_dir.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=not headed, args=["--no-sandbox"])
        for width in widths:
            context = browser.new_context(viewport={"width": width, "height": height})
            page = context.new_page()
            console_errors: list[str] = []
            page.on("console", _console_collector(console_errors))
            page.goto(base_url, wait_until="domcontentloaded", timeout=30000)
            page.wait_for_selector("#orders-mirror", timeout=15000)
            # The mirror's placeholder copy is not a gate — proceed if it never
            # shows (e.g. a broker connection with real rows).
            with contextlib.suppress(PlaywrightTimeoutError):
                page.wait_for_function(
                    "() => document.querySelectorAll('.cockpit-empty').length > 0",
                    timeout=8000,
                )
            page.wait_for_timeout(SETTLE_MS)

            if bob_open:
                page.click("#bob-chat-tab")
                page.wait_for_timeout(600)

            probe = page.evaluate(_PROBE_JS)
            shot = shot_dir / f"layout-{width}-{stamp}.png"
            page.screenshot(path=str(shot), full_page=False)  # full_page would lie

            failures = _collect_failures(probe)
            results.append(
                {
                    "width": width,
                    "failures": failures,
                    "ok": not failures,
                    "screenshot": str(shot),
                    "diagnostics": {
                        "docScrollWidth": probe["docScrollWidth"],
                        "innerWidth": probe["innerWidth"],
                        "appMain": {
                            "minWidth": probe["appMain"]["minWidth"] if probe["appMain"] else None,
                            "right": round(probe["appMain"]["rect"]["right"], 1)
                            if probe["appMain"]
                            else None,
                        },
                        "chartZone": {
                            "clientWidth": probe["chartZone"]["clientWidth"]
                            if probe["chartZone"]
                            else None,
                            "scrollWidth": probe["chartZone"]["scrollWidth"]
                            if probe["chartZone"]
                            else None,
                            "columns": probe["chartZone"]["gridColumnPx"]
                            if probe["chartZone"]
                            else None,
                        },
                        "mirror": {
                            "rows": probe["mirror"]["rows"] if probe["mirror"] else None,
                            "maxHeight": probe["mirror"]["maxHeight"] if probe["mirror"] else None,
                            "alignItems": probe["mirror"]["alignItems"]
                            if probe["mirror"]
                            else None,
                        },
                        "cockpitEmptyCount": len(probe["cockpitEmpty"]),
                        "cockpitEmptyVisible": sum(
                            1 for e in probe["cockpitEmpty"] if e["visible"]
                        ),
                        "hitTargets": len(probe["hits"]),
                        "f51": probe["f51"]["text"] if probe["f51"] else None,
                        "bobPanelOpen": bob_open,
                        "bobPanelWidth": probe["panelWidth"],
                        "consoleErrors": console_errors[:5],
                    },
                }
            )
            context.close()
        browser.close()

    return {"base_url": base_url, "results": results}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--widths", default=",".join(str(w) for w in DEFAULT_WIDTHS))
    parser.add_argument("--height", type=int, default=DEFAULT_HEIGHT)
    parser.add_argument("--headed", action="store_true")
    parser.add_argument(
        "--bob-open", action="store_true", help="also probe with the Bob panel open"
    )
    parser.add_argument("--screenshot-dir", default=str(ROOT / "scratch" / "layout-guard"))
    parser.add_argument("--json", action="store_true", help="print the full probe as JSON")
    args = parser.parse_args()

    widths = [int(w) for w in args.widths.split(",") if w.strip()]
    report = run(
        base_url=args.base_url.rstrip("/"),
        widths=widths,
        height=args.height,
        headed=args.headed,
        bob_open=args.bob_open,
        shot_dir=Path(args.screenshot_dir),
    )

    failed_widths = 0
    for entry in report["results"]:
        if entry["ok"]:
            print(f"[PASS] {entry['width']:>4}px  A1-A8 green")
        else:
            failed_widths += 1
            print(f"[FAIL] {entry['width']:>4}px")
            for key in sorted(entry["failures"]):
                for msg in entry["failures"][key]:
                    print(f"         {key}: {msg}")
        diag = entry["diagnostics"]
        print(
            f"         diag scrollWidth={diag['docScrollWidth']} inner={diag['innerWidth']} "
            f"app-main[minWidth={diag['appMain']['minWidth']},right={diag['appMain']['right']}] "
            f"chart-zone[client={diag['chartZone']['clientWidth']},"
            f"scroll={diag['chartZone']['scrollWidth']},cols={diag['chartZone']['columns']}] "
            f"cockpit-empty={diag['cockpitEmptyVisible']}/{diag['cockpitEmptyCount']} "
            f"f51={diag['f51']!r} shot={entry['screenshot']}"
        )

    if args.json:
        print(json.dumps(report, indent=2))

    print(
        f"\nlayout_guard: {len(widths) - failed_widths}/{len(widths)} widths green "
        f"(A1 scroll, A2 min-width, A3/A4 chart-zone column, A5 hit-test, "
        f"A7 vertical clipping, A8 f51 verdict)"
    )
    return 1 if failed_widths else 0


if __name__ == "__main__":
    sys.exit(main())
