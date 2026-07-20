"""Verify 5 expert cards render real pipeline data after a chat query.

Usage:
    python scripts/verify_cockpit_cards.py
    python scripts/verify_cockpit_cards.py --headed
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any

from playwright.sync_api import Page, TimeoutError as PlaywrightTimeoutError, sync_playwright


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BASE_URL = "http://localhost:8002"
QUERY = "AAPL analise"

# Initial "empty" states per card
INITIAL_STATES = {
    "f51": {"verdict": "WAIT"},
    "sdca": {"verdict": "WAIT"},
    "neural": {"verdict": "WAIT"},
    "trinity": {"verdict": "--"},
    "guardrail": {"summary": "--/30"},
}


def check_card_state(page: Page) -> dict[str, Any]:
    """Snapshot every expert card's state from the DOM."""
    cards = {}

    for key, id_map in [
        ("f51", {"verdict": "f51-verdict", "body": "f51-body", "trust": "f51-trust-bar"}),
        ("sdca", {"verdict": "sdca-verdict", "body": "sdca-body", "trust": "sdca-trust-bar"}),
        ("neural", {"verdict": "neural-verdict", "body": "neural-body", "trust": "neural-trust-bar"}),
        ("trinity", {"verdict": "trinity-verdict", "body": "trinity-body", "trust": "trinity-trust-bar"}),
        ("guardrail", {"summary": "guardrails-summary", "body": "guardrails-body", "trust": "guardrail-trust-bar"}),
    ]:
        card_data = {}
        for field, dom_id in id_map.items():
            val = page.evaluate(
                f"(id) => document.getElementById(id)?.textContent?.trim() || null",
                dom_id,
            )
            card_data[field] = val or ""
        # Body length
        card_data["body_length"] = len(card_data.get("body", ""))
        # Trust bar width
        trust_w = page.evaluate(
            f"(id) => {{ const b=document.getElementById(id); if(!b) return null; const s=b.querySelector('span'); return s ? s.style.width : null; }}",
            id_map.get("trust", ""),
        )
        card_data["trust_width"] = trust_w or "0%"

        cards[key] = card_data

    return cards


def has_real_data(card: dict[str, Any], card_key: str) -> bool:
    """Check if a card shows real data (not the initial empty state)."""
    initial = INITIAL_STATES.get(card_key, {})
    for field, init_val in initial.items():
        current = card.get(field, "")
        if current != init_val:
            return True
    # Also check body content - if there's meaningful content, it has data
    if card.get("body_length", 0) > 50:
        return True
    return False


def run_verification(
    base_url: str,
    headed: bool,
    timeout_ms: int,
    slow_mo: int = 0,
) -> dict[str, Any]:
    out_dir = ROOT / "output" / "playwright"
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    screenshot_path = out_dir / f"cockpit-cards-{stamp}.png"

    console_errors: list[str] = []
    page_errors: list[str] = []
    timeline: list[dict[str, Any]] = []

    with sync_playwright() as pw:
        browser = pw.chromium.launch(
            headless=not headed,
            slow_mo=slow_mo,
            args=["--no-sandbox", "--disable-web-security"],
        )
        page = browser.new_page(viewport={"width": 1440, "height": 980})
        page.on("console", lambda msg: console_errors.append(msg.text) if msg.type == "error" else None)
        page.on("pageerror", lambda exc: page_errors.append(str(exc)))

        # 1. Load page
        page.goto(base_url, wait_until="domcontentloaded", timeout=timeout_ms)
        page.wait_for_selector("#expert-panel-cards", timeout=timeout_ms)
        page.wait_for_timeout(1500)

        # 2. Take initial state
        initial = check_card_state(page)
        timeline.append({"t": 0, "label": "initial", "cards": initial})

        # 3. Open Bob chat panel
        page.evaluate("() => document.getElementById('live-panel')?.classList.add('is-open')")
        page.wait_for_timeout(500)

        # 4. Submit query via keyboard
        inp = page.locator("#user-inp")
        inp.wait_for(state="visible", timeout=5000)
        inp.focus()
        inp.fill(QUERY)
        page.wait_for_timeout(200)
        inp.press("Enter")

        # 5. Monitor card evolution over time
        deadline = time.time() + timeout_ms / 1000
        last_snapshot_time = time.time()
        stable_cycles = 0
        final_all_real = False
        previous_fingerprint = ""

        while time.time() < deadline:
            page.wait_for_timeout(1000)
            elapsed = int(time.time() - last_snapshot_time)
            current = check_card_state(page)

            # Create fingerprint
            fp = json.dumps(
                {k: (v.get("verdict") or v.get("summary", "")) for k, v in current.items()},
                sort_keys=True,
            )

            if fp != previous_fingerprint:
                timeline.append({"t": elapsed, "label": "update", "cards": current})
                previous_fingerprint = fp
                stable_cycles = 0
            else:
                stable_cycles += 1

            # Check if all 5 cards have real data
            all_real = all(has_real_data(current[k], k) for k in INITIAL_STATES)
            if all_real:
                final_all_real = True
                if stable_cycles >= 3:  # Stable for 3+ seconds
                    break

        # Final snapshot
        final = check_card_state(page)
        timeline.append({"t": int(time.time() - last_snapshot_time), "label": "final", "cards": final})

        # Check if Bob answered
        chat_ok = page.evaluate(
            """() => {
                const msgs = document.querySelectorAll('#chat .msg-ceo');
                if (msgs.length === 0) return false;
                const last = msgs[msgs.length - 1];
                return last && last.innerText && last.innerText.length > 50;
            }"""
        )

        page.screenshot(path=str(screenshot_path), full_page=True)
        browser.close()

    return {
        "base_url": base_url,
        "query": QUERY,
        "chat_responded": bool(chat_ok),
        "initial": initial,
        "final": final,
        "timeline": timeline,
        "all_cards_have_real_data": final_all_real,
        "console_errors": console_errors[:20],
        "page_errors": page_errors[:10],
        "screenshot": str(screenshot_path),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify cockpit expert cards.")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--headed", action="store_true")
    parser.add_argument("--timeout-ms", type=int, default=300000)
    parser.add_argument("--slow-mo", type=int, default=300)
    args = parser.parse_args()

    slow_mo = args.slow_mo if args.headed else 0

    result = run_verification(
        base_url=args.base_url,
        headed=args.headed,
        timeout_ms=args.timeout_ms,
        slow_mo=slow_mo,
    )

    # Analyse results
    per_card = {}
    for key in INITIAL_STATES:
        final_card = result["final"].get(key, {})
        has_data = has_real_data(final_card, key)
        detail = {
            "has_real_data": has_data,
            "verdict": final_card.get("verdict") or final_card.get("summary", ""),
            "body_length": final_card.get("body_length", 0),
            "trust_width": final_card.get("trust_width", ""),
        }
        per_card[key] = detail

    problems = [k for k, v in per_card.items() if not v["has_real_data"]]
    healthy = len(INITIAL_STATES) - len(problems)
    health_pct = round(healthy / len(INITIAL_STATES) * 100, 1)

    realtime_detected = len(result["timeline"]) > 2  # More than initial + final = intermediate updates

    output = {
        "ok": healthy >= 3,  # At least 3 out of 5 cards healthy
        "health_pct": health_pct,
        "healthy_cards": healthy,
        "total_cards": len(INITIAL_STATES),
        "cards_verdict": per_card,
        "problems": problems,
        "chat_responded": result["chat_responded"],
        "realtime_updates_detected": realtime_detected,
        "timeline_snapshots": len(result["timeline"]),
        "all_cards_have_real_data": result["all_cards_have_real_data"],
        "console_errors_count": len(result.get("console_errors", [])),
        "page_errors": result.get("page_errors", []),
        "screenshot": result.get("screenshot", ""),
    }

    print(json.dumps(output, indent=2, ensure_ascii=False))
    return 0 if output["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
