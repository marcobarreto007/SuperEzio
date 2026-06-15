#!/usr/bin/env python
"""Bob Training — Small Caps (com timeout maior e menos prompts)"""
import json
import urllib.request
import time

BASE = "http://127.0.0.1:8002"

# Top 5 small caps para teste (primeiro 5)
PROMPTS = [
    ("AEHR", "Analyze Aehr Test Systems semiconductor testing. Bull and bear case?"),
    ("PLAB", "Evaluate Photronics AI/quantum photomasks. Undervalued?"),
    ("SKYT", "Assess SkyWater Technology semiconductor manufacturing. Risks?"),
    ("SIGA", "Analyze SIGA Technologies TPOXX antiviral. Catalyst timeline?"),
    ("BNRG", "Analyze Brenmiller Energy thermal storage. Nano cap ~$3M. Survival path?"),
]

def submit(msg, ticker):
    payload = json.dumps({
        "from": "training",
        "to": "superezio",
        "type": "TASK.SUBMIT",
        "payload": {"message": msg, "ticker": ticker, "session_id": "small_caps_training"},
    }).encode()

    try:
        with urllib.request.urlopen(f"{BASE}/task/submit", data=payload, timeout=300) as r:
            events = []
            for line in r:
                if line:
                    try:
                        event = json.loads(line.decode())
                        events.append(event)
                        if event.get("type") == "FINAL_RESPONSE":
                            return event.get("verdict", "?"), len(event.get("content", "")), events
                    except:
                        pass
            return None, None, events
    except Exception as e:
        return None, str(e), []

def main():
    print("=== BOB TRAINING — SMALL CAPS (Top 5) ===\n")

    # Health check
    try:
        with urllib.request.urlopen(f"{BASE}/health", timeout=5) as r:
            print(f"API: {json.loads(r.read()).get('status', 'unknown')}\n")
    except:
        print("ERROR: API not responding. Start with: runtime\\do_restart.ps1")
        return

    results = []
    for i, (ticker, msg) in enumerate(PROMPTS, 1):
        print(f"[{i}/5] {ticker}... ", end="", flush=True)
        verdict, info, events = submit(msg, ticker)
        if verdict is None:
            print(f"ERROR: {info}")
            results.append({"ticker": ticker, "error": info})
        else:
            print(f"OK {verdict} ({info} chars)")
            results.append({"ticker": ticker, "verdict": verdict, "chars": info, "events": len(events)})
        time.sleep(2)  # Rate limit

    # Save
    output_file = "output/small_caps_training_top5.json"
    with open(output_file, "w") as f:
        json.dump({"timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"), "results": results}, f, indent=2)

    print(f"\nDone: {len([r for r in results if 'error' not in r])}/5 successful")
    print(f"Saved: {output_file}")

if __name__ == "__main__":
    main()
