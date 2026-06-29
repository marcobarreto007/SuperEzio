"""End-to-end fiducial test — full pipeline: parse → collect → gates → Bob → journal.

Simulates a complete paper trade flow WITHOUT touching real money.
Validates that the entire chain works end-to-end.
"""

import os
import sys
import json
import time
import urllib.request
import uuid

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

API = "http://127.0.0.1:8002"


def check(condition, msg):
    if not condition:
        print(f"  FAIL: {msg}")
        return False
    print(f"  PASS: {msg}")
    return True


def test_e2e():
    print("=" * 55)
    print("  E2E FIDUCIAL TEST — Paper Trade Simulation")
    print("=" * 55)
    passed = 0
    failed = 0

    # Pre-checks
    if not check(_api_alive(), "API server online :8002"):
        print("Start API: PYTHONPATH=src python -m agent_server.main")
        return
    passed += 1

    if not check(_bob_alive(), "Bob CEO online :8082"):
        print("Start Bob: scripts/serve_agent_llamacpp.ps1")
        failed += 1
    else:
        passed += 1

    # Check FREEZE status
    from core.pipeline.f51_trade_gate import is_execution_frozen

    frozen = is_execution_frozen()
    if not check(not frozen, f"FREEZE is OFF (currently: {frozen})"):
        print("Set F51_TRADING_EXECUTION_FREEZE=false to run E2E")
        failed += 1
        return
    passed += 1

    # Submit a real analysis request
    msg = {
        "version": "a2a/1.0",
        "msg_id": str(uuid.uuid4()),
        "from": "e2e-test",
        "to": "bob-ceo",
        "type": "TASK.SUBMIT",
        "timestamp": time.time(),
        "payload": {"message": "NVDA — analise e sugira entry/stop", "session_id": "e2e"},
    }

    print("\n  Submitting task to pipeline...")
    t0 = time.time()
    try:
        data = json.dumps(msg).encode()
        req = urllib.request.Request(
            f"{API}/task/submit", data=data, headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req, timeout=300) as resp:
            raw = resp.read().decode()
            elapsed = time.time() - t0

        lines = [json.loads(line) for line in raw.strip().split("\n") if line.strip()]
        steps = set()
        bob_content = ""
        cache_hit = False
        errors = []

        for e in lines:
            if e.get("type") == "PIPELINE_STEP":
                steps.add(e.get("step", "?"))
                if e.get("status") == "cache_hit":
                    cache_hit = True
            elif e.get("type") == "CHUNK":
                bob_content += e.get("content", "")
            if e.get("type") == "PIPELINE_STEP" and "error" in str(e.get("reason", "")).lower():
                errors.append(e.get("reason", ""))

        if not check(elapsed < 300, f"Pipeline completed in {elapsed:.0f}s"):
            failed += 1
        else:
            passed += 1

        if not check(cache_hit, "Cache HIT (fast path active)"):
            failed += 1
        else:
            passed += 1

        if not check(len(steps) >= 15, f"Steps executed: {len(steps)}"):
            failed += 1
        else:
            passed += 1

        if not check(len(bob_content) > 50, f"Bob responded ({len(bob_content)} chars)"):
            failed += 1
        else:
            passed += 1

        if not check("NVDA" in bob_content.upper(), "Bob references NVDA"):
            failed += 1
        else:
            passed += 1

        has_decision = any(
            w in bob_content.lower()
            for w in ["buy", "sell", "wait", "comprar", "vender", "esperar"]
        )
        if not check(has_decision, "Bob made a decision"):
            failed += 1
        else:
            passed += 1

        if not check(len(errors) == 0, f"No errors ({len(errors)} found: {errors[:2]})"):
            failed += 1
        else:
            passed += 1

    except Exception as e:
        check(False, f"Pipeline error: {str(e)[:100]}")
        failed += 1

    print(f"\n{'=' * 40}")
    print(f"  PASSED: {passed}  FAILED: {failed}")
    print(f"  STATUS: {'PASS' if failed == 0 else 'FAIL'}")
    print(f"{'=' * 40}")


def _api_alive():
    try:
        import socket

        s = socket.socket()
        s.settimeout(2)
        s.connect(("127.0.0.1", 8002))
        s.close()
        return True
    except Exception:
        return False


def _bob_alive():
    try:
        import socket

        s = socket.socket()
        s.settimeout(2)
        s.connect(("127.0.0.1", 8082))
        s.close()
        return True
    except Exception:
        return False


if __name__ == "__main__":
    test_e2e()
