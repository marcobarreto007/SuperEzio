"""Verify 5 expert cards render real pipeline data after a chat query.

Usage:
    python scripts/verify_cockpit_cards.py
    python scripts/verify_cockpit_cards.py --headed  (watch browser)
    python scripts/verify_cockpit_cards.py --timeout-ms 300000
"""

from __future__ import annotations

import argparse
import json
import time
import urllib.request
from pathlib import Path
from typing import Any

from playwright.sync_api import Page, TimeoutError as PlaywrightTimeoutError, sync_playwright


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BASE_URL = "http://127.0.0.1:8002"
QUERY = "AAPL analise"


def _http_json(url: str, timeout_s: float = 5.0) -> dict[str, Any]:
    with urllib.request.urlopen(url, timeout=timeout_s) as r:
        return json.loads(r.read().decode("utf-8"))


def check_card_state(page: Page) -> dict[str, Any]:
    """Snapshot every expert card's state from the DOM."""
    cards = {}

    # --- F51 Card ---
    f51_verdict = page.evaluate("() => document.getElementById('f51-verdict')?.textContent?.trim() || 'N/A'")
    f51_body = page.evaluate("() => document.getElementById('f51-body')?.innerText?.trim() || 'N/A'")
    f51_trust = page.evaluate("""() => {
        const bar = document.getElementById('f51-trust-bar');
        if (!bar) return null;
        const span = bar.querySelector('span');
        return span ? span.style.width : null;
    }""")
    cards["f51"] = {
        "verdict": f51_verdict,
        "body_preview": f51_body[:300],
        "body_length": len(f51_body),
        "trust_width": f51_trust,
        "has_real_data": f51_verdict not in ("WAIT", "N/A", "--")
    }

    # --- SDCA Card ---
    sdca_verdict = page.evaluate("() => document.getElementById('sdca-verdict')?.textContent?.trim() || 'N/A'")
    sdca_body = page.evaluate("() => document.getElementById('sdca-body')?.innerText?.trim() || 'N/A'")
    sdca_trust = page.evaluate("""() => {
        const bar = document.getElementById('sdca-trust-bar');
        if (!bar) return null;
        const span = bar.querySelector('span');
        return span ? span.style.width : null;
    }""")
    cards["sdca"] = {
        "verdict": sdca_verdict,
        "body_preview": sdca_body[:300],
        "body_length": len(sdca_body),
        "trust_width": sdca_trust,
        "has_real_data": sdca_verdict not in ("WAIT", "N/A", "--")
    }

    # --- Neural Card ---
    neural_verdict = page.evaluate("() => document.getElementById('neural-verdict')?.textContent?.trim() || 'N/A'")
    neural_body = page.evaluate("() => document.getElementById('neural-body')?.innerText?.trim() || 'N/A'")
    neural_trust = page.evaluate("""() => {
        const bar = document.getElementById('neural-trust-bar');
        if (!bar) return null;
        const span = bar.querySelector('span');
        return span ? span.style.width : null;
    }""")
    cards["neural"] = {
        "verdict": neural_verdict,
        "body_preview": neural_body[:300],
        "body_length": len(neural_body),
        "trust_width": neural_trust,
        "has_real_data": neural_verdict not in ("WAIT", "N/A", "--")
    }

    # --- Trinity Card ---
    trinity_verdict = page.evaluate("() => document.getElementById('trinity-verdict')?.textContent?.trim() || 'N/A'")
    trinity_body = page.evaluate("() => document.getElementById('trinity-body')?.innerText?.trim() || 'N/A'")
    trinity_trust = page.evaluate("""() => {
        const bar = document.getElementById('trinity-trust-bar');
        if (!bar) return null;
        const span = bar.querySelector('span');
        return span ? span.style.width : null;
    }""")
    cards["trinity"] = {
        "verdict": trinity_verdict,
        "body_preview": trinity_body[:300],
        "body_length": len(trinity_body),
        "trust_width": trinity_trust,
        "has_real_data": trinity_verdict not in ("--", "N/A")
    }

    # --- Guardrail Card ---
    guard_summary = page.evaluate("() => document.getElementById('guardrails-summary')?.textContent?.trim() || 'N/A'")
    guard_body = page.evaluate("() => document.getElementById('guardrails-body')?.innerText?.trim() || 'N/A'")
    guard_trust = page.evaluate("""() => {
        const bar = document.getElementById('guardrail-trust-bar');
        if (!bar) return null;
        const span = bar.querySelector('span');
        return span ? span.style.width : null;
    }""")
    cards["guardrail"] = {
        "summary": guard_summary,
        "body_preview": guard_body[:300],
        "body_length": len(guard_body),
        "trust_width": guard_trust,
        "has_real_data": guard_summary not in ("--/30", "N/A")
    }

    return cards


def wait_for_cards_update(
    page: Page,
    initial: dict[str, Any],
    max_wait_ms: int = 180000,
    poll_interval_ms: int = 1000,
) -> dict[str, Any]:
    """Poll until at least one card shows real data (verdict changed from initial WAIT/--)."""
    deadline = time.time() + max_wait_ms / 1000
    while time.time() < deadline:
        current = check_card_state(page)
        changed = 0
        for key in ("f51", "sdca", "neural", "trinity", "guardrail"):
            initial_card = initial.get(key, {})
            current_card = current.get(key, {})
            # Check if verdict changed
            if key == "guardrail":
                old_v = initial_card.get("summary", "")
                new_v = current_card.get("summary", "")
            else:
                old_v = initial_card.get("verdict", "")
                new_v = current_card.get("verdict", "")
            if new_v != old_v and old_v not in ("N/A", ""):
                changed += 1
        if changed >= 1:
            return current
        page.wait_for_timeout(poll_interval_ms)
    return check_card_state(page)


def detect_realtime_updates(page: Page, timeout_ms: int = 120000) -> dict[str, Any]:
    """Monitor whether cards update progressively (real-time) or all at once at the end."""
    snapshots: list[dict[str, Any]] = []
    seen_states: set[str] = set()
    stable_count = 0

    deadline = time.time() + timeout_ms / 1000
    while time.time() < deadline:
        cards = check_card_state(page)
        # Create a fingerprint of all verdicts
        fp = json.dumps(
            {
                "f51": cards.get("f51", {}).get("verdict", ""),
                "sdca": cards.get("sdca", {}).get("verdict", ""),
                "neural": cards.get("neural", {}).get("verdict", ""),
                "trinity": cards.get("trinity", {}).get("verdict", ""),
                "guard": cards.get("guardrail", {}).get("summary", ""),
            },
            sort_keys=True,
        )
        if fp not in seen_states:
            seen_states.add(fp)
            snapshots.append(cards)
            stable_count = 0
        else:
            stable_count += 1

        # Stop if all 5 cards have real data and have been stable for 5+ polls
        all_real = all(
            cards[k].get("has_real_data", False) for k in ("f51", "sdca", "neural", "trinity", "guardrail")
        )
        if all_real and stable_count >= 5:
            break

        page.wait_for_timeout(1000)

    return {
        "card_count": len(snapshots),
        "unique_states": len(seen_states),
        "cards_final": snapshots[-1] if snapshots else {},
        "final_all_real": all(
            snapshots[-1][k].get("has_real_data", False) for k in ("f51", "sdca", "neural", "trinity", "guardrail")
        )
        if snapshots
        else False,
    }


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

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=not headed, slow_mo=slow_mo)
        page = browser.new_page(viewport={"width": 1440, "height": 980})
        page.on(
            "console",
            lambda msg: console_errors.append(msg.text) if msg.type == "error" else None,
        )
        page.on("pageerror", lambda exc: page_errors.append(str(exc)))

        # 1. Open page
        page.goto(base_url, wait_until="domcontentloaded", timeout=timeout_ms)
        page.wait_for_selector("#chat", timeout=timeout_ms)
        page.wait_for_selector("#user-inp", timeout=timeout_ms)
        page.wait_for_selector("#send-btn", timeout=timeout_ms)
        page.wait_for_selector("#expert-panel-cards", timeout=timeout_ms)
        page.wait_for_timeout(2000)

        # 2. Take initial snapshot
        initial_cards = check_card_state(page)

        # 3. Open Bob chat panel (it's collapsed by default)
        # First, force the panel open via JavaScript to avoid viewport issues
        page.evaluate("() => { const p = document.getElementById('live-panel'); if(p) p.classList.add('is-open'); }")
        page.wait_for_timeout(300)
        # Also ensure the send button is scrolled into view
        page.evaluate("() => { const btn = document.getElementById('send-btn'); if(btn) btn.scrollIntoView({block:'center'}); }")
        page.wait_for_timeout(200)

        # 4. Type query and send using keyboard submit (Enter) which is more reliable
        inp = page.locator("#user-inp")
        inp.wait_for(state="visible", timeout=5000)
        inp.fill(QUERY)
        page.wait_for_timeout(300)

        # Use keyboard Enter to submit (works even if send-btn has viewport issues)
        inp.press("Enter")

        # 5. Wait for Bob's response in the chat
        try:
            page.wait_for_function(
                """
                () => {
                    const bobMsgs = document.querySelectorAll('#chat .msg-ceo');
                    if (bobMsgs.length < 1) return false;
                    const last = bobMsgs[bobMsgs.length - 1];
                    const text = last.innerText || '';
                    return text.length > 80 && !text.includes('Erro:');
                }
                """,
                timeout=timeout_ms,
            )
            chat_ok = True
        except PlaywrightTimeoutError:
            chat_ok = False

        # 6. Take snapshot after chat response
        post_chat_cards = check_card_state(page)

        # 7. Detect real-time updates by monitoring over time
        realtime_result = detect_realtime_updates(page, timeout_ms=min(timeout_ms, 120000))

        # 8. Final snapshot
        final_cards = realtime_result.get("cards_final", check_card_state(page))

        # Screenshot
        page.screenshot(path=str(screenshot_path), full_page=True)
        browser.close()

    return {
        "base_url": base_url,
        "query": QUERY,
        "chat_response_ok": chat_ok,
        "initial_cards": initial_cards,
        "post_chat_cards": post_chat_cards,
        "realtime": realtime_result,
        "final_cards": final_cards,
        "console_errors": console_errors,
        "page_errors": page_errors,
        "screenshot": str(screenshot_path),
    }


def score_cards(cards: dict[str, Any]) -> dict[str, Any]:
    """Score each card: 1.0 = full real data, 0.0 = WAIT/empty."""
    scores = {}
    for key in ("f51", "sdca", "neural", "trinity", "guardrail"):
        card = cards.get(key, {})
        has_data = card.get("has_real_data", False)
        body_len = card.get("body_length", 0)
        trust_w = card.get("trust_width", "0%")

        if key == "guardrail":
            summary = card.get("summary", "--/30")
            is_default = summary in ("--/30", "N/A")
        else:
            verdict = card.get("verdict", "WAIT")
            is_default = verdict in ("WAIT", "--", "N/A")

        # Score: 0 (stuck on default), 0.5 (partial), 1.0 (real data)
        if has_data and body_len > 80 and trust_w and trust_w != "0%":
            scores[key] = 1.0
        elif has_data and body_len > 20:
            scores[key] = 0.5
        else:
            scores[key] = 0.0

    overall = sum(scores.values()) / len(scores) * 100 if scores else 0
    return {"per_card": scores, "overall_pct": round(overall, 1)}


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify cockpit expert cards render real pipeline data.")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--headed", action="store_true", help="Run with visible browser")
    parser.add_argument("--timeout-ms", type=int, default=300000, help="Overall timeout")
    parser.add_argument(
        "--slow-mo", type=int, default=300,
        help="Milliseconds slow_mo (only with --headed)",
    )
    args = parser.parse_args()

    slow_mo = args.slow_mo if args.headed else 0

    try:
        result = run_verification(
            base_url=args.base_url,
            headed=args.headed,
            timeout_ms=args.timeout_ms,
            slow_mo=slow_mo,
        )
    except PlaywrightTimeoutError as e:
        print(json.dumps({"ok": False, "error": f"timeout: {e}"}, indent=2))
        return 1
    except Exception as e:
        print(json.dumps({"ok": False, "error": str(e)}, indent=2))
        return 1

    # Score the cards
    final_cards = result.get("final_cards", {})
    score = score_cards(final_cards)

    # Determine which cards are problematic
    problems = []
    for key in ("f51", "sdca", "neural", "trinity", "guardrail"):
        card = final_cards.get(key, {})
        score_val = score["per_card"].get(key, 0)
        if score_val < 0.8:
            problems.append({
                "card": key,
                "verdict": card.get("verdict", card.get("summary", "N/A")),
                "body_preview": card.get("body_preview", "")[:120],
                "trust_width": card.get("trust_width", "N/A"),
                "score": score_val,
            })

    output = {
        "ok": score["overall_pct"] >= 60,
        "query": result["query"],
        "chat_response_ok": result["chat_response_ok"],
        "cards_rendering_score": score["overall_pct"],
        "per_card_score": score["per_card"],
        "realtime_card_states_seen": result["realtime"]["unique_states"],
        "realtime_updates_detected": result["realtime"]["unique_states"] > 1,
        "final_all_real": result["realtime"]["final_all_real"],
        "problems": problems,
        "problems_count": len(problems),
        "console_errors": result["console_errors"],
        "page_errors": result["page_errors"],
        "screenshot": result["screenshot"],
    }

    # Detailed card preview
    output["cards_detail"] = {}
    for key in ("f51", "sdca", "neural", "trinity", "guardrail"):
        card = final_cards.get(key, {})
        output["cards_detail"][key] = {
            "verdict": card.get("verdict", card.get("summary", "")),
            "body_length": card.get("body_length", 0),
            "trust_width": card.get("trust_width", ""),
            "has_real_data": card.get("has_real_data", False),
            "body_preview": card.get("body_preview", "")[:200],
        }

    print(json.dumps(output, indent=2, ensure_ascii=False))
    return 0 if output["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
