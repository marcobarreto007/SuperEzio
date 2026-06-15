#!/usr/bin/env python
"""Simple Bob Training — Small Caps"""
import json
import urllib.request
import time

BASE = "http://127.0.0.1:8002"

# Top 15 small caps — prompts diretos
PROMPTS = [
    ("AEHR", "Analyze Aehr Test Systems semiconductor testing. Bull and bear case?"),
    ("PLAB", "Evaluate Photronics AI/quantum photomasks. Undervalued?"),
    ("SKYT", "Assess SkyWater Technology semiconductor manufacturing. Risks?"),
    ("INOD", "Analyze Innodata AI data solutions. Revenue sustainable?"),
    ("USIO", "Evaluate Univest semiconductor IP. What's the moat?"),
    ("SIGA", "Analyze SIGA Technologies TPOXX antiviral. Catalyst timeline?"),
    ("NEPH", "Assess NephroSense kidney diagnostic. Regulatory risks?"),
    ("PDSB", "Evaluate PDS Biotechnology immunotherapy. Binary trial risk?"),
    ("IMRX", "Analyze Immuneering precision oncology. Cash runway?"),
    ("NUVB", "Assess Nuvation Bio precision therapies. Pipeline diversified?"),
    ("FINV", "Evaluate FinVolution fintech lending. Credit risk?"),
    ("III", "Analyze Hamilton Insurance technology. Underwriting discipline?"),
    ("LX", "Assess LexinFintech digital lending. Delinquency trend?"),
    ("BNRG", "Analyze Brenmiller Energy thermal storage. Nano cap ~$3M. Survival path?"),
    ("DIBS", "Evaluate 1stdibs luxury marketplace. Growth decelerating?"),
]

def submit(msg, ticker):
    payload = json.dumps({
        "version": "a2a/1.0",
        "from": "training",
        "to": "bob",
        "type": "TASK.SUBMIT",
        "payload": {"message": msg, "ticker": ticker, "session_id": "small_caps_training"},
    }).encode()

    try:
        with urllib.request.urlopen(f"{BASE}/task/submit", data=payload, timeout=120) as r:
            for line in r:
                if line:
                    event = json.loads(line.decode())
                    if event.get("type") == "FINAL_RESPONSE":
                        return event.get("verdict", "?"), len(event.get("content", ""))
    except Exception as e:
        return None, str(e)

def main():
    print("=== BOB TRAINING — SMALL CAPS ===\n")

    # Health check
    try:
        with urllib.request.urlopen(f"{BASE}/health", timeout=5) as r:
            print(f"API: {json.loads(r.read()).get('status', 'unknown')}\n")
    except:
        print("ERROR: API not responding. Start with: runtime\\do_restart.ps1")
        return

    results = []
    for i, (ticker, msg) in enumerate(PROMPTS, 1):
        print(f"[{i}/15] {ticker}...", end=" ")
        verdict, info = submit(msg, ticker)
        if verdict is None:
            print(f"ERROR: {info}")
            results.append({"ticker": ticker, "error": info})
        else:
            print(f"OK {verdict} ({info} chars)")
            results.append({"ticker": ticker, "verdict": verdict, "chars": info})
        time.sleep(1)  # Rate limit

    # Save
    with open("output/small_caps_training_simple.json", "w") as f:
        json.dump({"timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"), "results": results}, f, indent=2)

    print(f"\nDone: {len([r for r in results if 'error' not in r])}/15 successful")
    print("Saved: output/small_caps_training_simple.json")

if __name__ == "__main__":
    main()
