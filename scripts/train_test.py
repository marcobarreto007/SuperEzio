#!/usr/bin/env python
"""Bob Training — Small Caps (usando requests com debug)"""
import json
import sys

try:
    import requests
except ImportError:
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "requests"])
    import requests

BASE = "http://127.0.0.1:8002"

# Teste exato como no contrato
payload = {
    "from": "user",
    "to": "superezio",
    "type": "TASK.SUBMIT",
    "payload": {
        "message": "Analyze SIGA stock briefly",
        "ticker": "SIGA",
        "session_id": "test_session"
    }
}

print("Testing with exact test contract payload:")
print(json.dumps(payload, indent=2))

try:
    response = requests.post(
        f"{BASE}/task/submit",
        json=payload,
        headers={"Content-Type": "application/json"},
        timeout=120
    )

    print(f"\nStatus Code: {response.status_code}")
    if response.status_code != 200:
        print(f"Error Response: {response.text}")
    else:
        lines = response.text.strip().split("\n")
        print(f"Events received: {len(lines)}")
        for i, line in enumerate(lines[:5], 1):
            try:
                event = json.loads(line)
                print(f"  Event {i}: {event.get('type', 'UNKNOWN')}")
            except:
                print(f"  Line {i}: {line[:100]}")

except Exception as e:
    print(f"ERROR: {e}")
