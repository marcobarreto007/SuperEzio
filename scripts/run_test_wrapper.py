"""Wrapper temporario para smoke test — nao modifica codigo existente.

Contorna:
- NewsScout que bloqueia event loop com tqdm (SUPEREZIO_GENIE_DISCOVERY_ENABLED=false)
- JWT auth que bloqueia chart fetch (SUPEREZIO_JWT_SECRET="")
"""
import os
import sys
import time
import subprocess
import json

# Config
os.environ["SUPEREZIO_GENIE_DISCOVERY_ENABLED"] = "false"
os.environ["SUPEREZIO_JWT_SECRET"] = ""

# 1. Start server
server_proc = subprocess.Popen(
    [sys.executable, "-m", "src.agent_server.main"],
    cwd="C:/Users/marco/Desktop/SuperEzio",
    stdout=subprocess.PIPE,
    stderr=subprocess.STDOUT,
)

# Wait for server
import urllib.request
for i in range(20):
    try:
        with urllib.request.urlopen("http://127.0.0.1:8002/health", timeout=3) as r:
            data = json.loads(r.read())
            if data.get("status") == "ok":
                print(f"[OK] Server ready (attempt {i+1})")
                break
    except Exception:
        pass
    time.sleep(2)
else:
    print("[FAIL] Server did not start")
    server_proc.kill()
    sys.exit(1)

# 2. Run smoke test
print("[INFO] Running browser smoke test...")
result = subprocess.run(
    [sys.executable, "scripts/browser_smoke.py", "--headed", "--timeout-ms", "300000"],
    cwd="C:/Users/marco/Desktop/SuperEzio",
    capture_output=True, text=True, timeout=360
)
print(result.stdout[-2000:] if len(result.stdout) > 2000 else result.stdout)
if result.stderr:
    print("[STDERR]", result.stderr[-1000:])

# 3. Cleanup
server_proc.kill()
server_proc.wait()
print(f"[DONE] Exit code: {result.returncode}")
