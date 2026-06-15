#!/usr/bin/env python
"""Debug Bob Training"""
import json
import sys

try:
    import requests
except ImportError:
    print("Installing requests...")
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "requests"])
    import requests

BASE = "http://127.0.0.1:8002"

# Test payload
payload = {
    "version": "a2a/1.0",
    "from": "test",
    "to": "bob",
    "type": "TASK.SUBMIT",
    "payload": {
        "message": "Analyze SIGA stock briefly",
        "ticker": "SIGA",
        "session_id": "debug_test"
    }
}

print("Testing API with payload:")
print(json.dumps(payload, indent=2))

try:
    response = requests.post(
        f"{BASE}/task/submit",
        json=payload,
        headers={"Content-Type": "application/json"},
        timeout=60
    )

    print(f"\nStatus: {response.status_code}")
    print(f"Response: {response.text[:500]}")

except Exception as e:
    print(f"\nERROR: {e}")

# Test with simpler payload
print("\n\n=== Trying simpler payload ===")
payload2 = {
    "from": "test",
    "to": "bob",
    "type": "TASK.SUBMIT",
    "payload": {
        "message": "Analyze SIGA stock briefly",
        "ticker": "SIGA"
    }
}

print(json.dumps(payload2, indent=2))

try:
    response = requests.post(
        f"{BASE}/task/submit",
        json=payload2,
        headers={"Content-Type": "application/json"},
        timeout=60
    )

    print(f"\nStatus: {response.status_code}")
    print(f"Response: {response.text[:500]}")

except Exception as e:
    print(f"\nERROR: {e}")
