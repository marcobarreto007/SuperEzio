#!/usr/bin/env python
"""Bob Training — Small Caps (streaming, timeout muito alto)"""
import json
import sys
import time

try:
    import requests
except:
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "requests"])
    import requests

BASE = "http://127.0.0.1:8002"

# Top 5 small caps
PROMPTS = [
    ("AEHR", "Analyze Aehr Test Systems semiconductor testing. Bull and bear case?"),
    ("PLAB", "Evaluate Photronics AI/quantum photomasks. Undervalued?"),
    ("SKYT", "Assess SkyWater Technology semiconductor manufacturing. Risks?"),
    ("SIGA", "Analyze SIGA Technologies TPOXX antiviral. Catalyst timeline?"),
    ("BNRG", "Analyze Brenmiller Energy thermal storage. Nano cap ~$3M. Survival path?"),
]

def submit_streaming(msg, ticker):
    """Submit com streaming e mostra eventos em tempo real"""
    payload = {
        "from": "user",
        "to": "superezio",
        "type": "TASK.SUBMIT",
        "payload": {
            "message": msg,
            "ticker": ticker,
            "session_id": "small_caps_training"
        }
    }

    try:
        with requests.post(
            f"{BASE}/task/submit",
            json=payload,
            headers={"Content-Type": "application/json"},
            stream=True,
            timeout=600  # 10 minutos
        ) as response:
            if response.status_code != 200:
                return None, f"HTTP {response.status_code}: {response.text[:200]}"

            events = []
            for line in response.iter_lines():
                if line:
                    try:
                        event = json.loads(line.decode())
                        events.append(event)
                        typ = event.get("type", "?")
                        if typ == "STREAM_START":
                            print(f"  [START]", end="", flush=True)
                        elif typ == "INTENT_CLASSIFIED":
                            print(f" [INTENT:{event.get('intent','?')}]", end="", flush=True)
                        elif typ == "ROUTE_SELECTED":
                            print(f" [ROUTE:{event.get('route','?')}]", end="", flush=True)
                        elif typ == "CHUNK":
                            print("▪", end="", flush=True)
                        elif typ == "FINAL_RESPONSE":
                            verdict = event.get("verdict", "?")
                            print(f" [DONE:{verdict}]")
                            return verdict, len(event.get("content", "")), events
                        elif typ == "ERROR":
                            return None, event.get("message", "Unknown error"), events
                    except json.JSONDecodeError:
                        pass

            return None, "No events received", events

    except requests.Timeout:
        return None, "Timeout after 600s", []
    except Exception as e:
        return None, str(e), []

def main():
    print("=== BOB TRAINING — SMALL CAPS (Streaming) ===\n")

    # Health check
    try:
        resp = requests.get(f"{BASE}/health", timeout=5)
        print(f"API: {resp.json().get('status', 'unknown')}\n")
    except:
        print("ERROR: API not responding")
        return

    results = []
    for i, (ticker, msg) in enumerate(PROMPTS, 1):
        print(f"[{i}/5] {ticker}...", end="", flush=True)
        verdict, info, events = submit_streaming(msg, ticker)
        if verdict is None:
            print(f" ERROR: {info}")
            results.append({"ticker": ticker, "error": info})
        else:
            print(f" OK ({info} chars, {len(events)} events)")
            results.append({"ticker": ticker, "verdict": verdict, "chars": info, "events": len(events)})
        time.sleep(3)  # Rate limit entre prompts

    # Save
    with open("output/small_caps_training_stream.json", "w") as f:
        json.dump({"timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"), "results": results}, f, indent=2)

    print(f"\nDone: {len([r for r in results if 'error' not in r])}/5 successful")
    print("Saved: output/small_caps_training_stream.json")

if __name__ == "__main__":
    main()
