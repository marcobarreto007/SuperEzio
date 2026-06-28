"""Bob Watchdog — keeps the CEO alive 24/7.

Monitors :8082 health endpoint. If Bob dies, restarts automatically.
Runs as a background daemon. Never stops.

Usage:
    python scripts/bob_watchdog.py
    # or: powershell -File scripts/bob_watchdog.ps1
"""

import os
import signal
import socket
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
BOB_PORT = int(os.getenv("SUPEREZIO_CEO_PORT", "8082"))
CHECK_INTERVAL = int(os.getenv("BOB_WATCHDOG_INTERVAL_SEC", "30"))
MAX_RESTARTS = int(os.getenv("BOB_WATCHDOG_MAX_RESTARTS", "10"))
RESTART_COOLDOWN = int(os.getenv("BOB_WATCHDOG_COOLDOWN_SEC", "120"))

_shutdown = False
_restart_count = 0
_last_restart = 0.0


def log(msg: str):
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
    print(f"[{timestamp}] {msg}", flush=True)


def is_bob_alive() -> bool:
    """Check if Bob is responding on health endpoint."""
    try:
        import urllib.request
        req = urllib.request.Request(f"http://127.0.0.1:{BOB_PORT}/health")
        with urllib.request.urlopen(req, timeout=5) as resp:
            return resp.status == 200
    except Exception:
        pass
    
    # Fallback: raw socket check
    try:
        s = socket.socket()
        s.settimeout(3)
        s.connect(("127.0.0.1", BOB_PORT))
        s.close()
        return True
    except Exception:
        return False


def restart_bob() -> bool:
    """Restart Bob via the PowerShell serve script."""
    global _restart_count, _last_restart
    
    now = time.time()
    if now - _last_restart < RESTART_COOLDOWN:
        log(f"Cooldown active. Skipping restart. Next in {RESTART_COOLDOWN - (now - _last_restart):.0f}s")
        return False
    
    if _restart_count >= MAX_RESTARTS:
        log(f"MAX_RESTARTS ({MAX_RESTARTS}) reached. Giving up. Manual intervention required.")
        return False
    
    _restart_count += 1
    _last_restart = now
    
    log(f"Restarting Bob (attempt {_restart_count}/{MAX_RESTARTS})...")
    
    script = PROJECT_ROOT / "scripts" / "serve_agent_llamacpp.ps1"
    if not script.exists():
        log(f"ERROR: Script not found: {script}")
        return False
    
    try:
        # Kill any existing llama-server
        subprocess.run(["taskkill", "/F", "/IM", "llama-server.exe"], 
                       capture_output=True, timeout=10)
        time.sleep(5)
        
        # Start new instance
        subprocess.Popen(
            ["powershell", "-ExecutionPolicy", "Bypass", "-File", str(script),
             "-Port", str(BOB_PORT), "-GpuLayers", "14"],
            cwd=str(PROJECT_ROOT),
            creationflags=subprocess.CREATE_NEW_CONSOLE if sys.platform == "win32" else 0,
        )
        
        # Wait for Bob to come online
        for i in range(40):  # Up to 200 seconds
            time.sleep(5)
            if is_bob_alive():
                log(f"Bob restarted successfully after {(i+1)*5}s")
                return True
        
        log("Bob did not come online after restart attempt")
        return False
        
    except Exception as e:
        log(f"Restart failed: {e}")
        return False


def handle_signal(signum, frame):
    global _shutdown
    log(f"Received signal {signum}. Shutting down...")
    _shutdown = True


def main():
    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)
    
    log("=" * 55)
    log("  BOB WATCHDOG — Keeping the CEO alive 24/7")
    log(f"  Port: {BOB_PORT}  |  Check: every {CHECK_INTERVAL}s")
    log(f"  Max restarts: {MAX_RESTARTS}  |  Cooldown: {RESTART_COOLDOWN}s")
    log("=" * 55)
    
    consecutive_failures = 0
    
    while not _shutdown:
        if is_bob_alive():
            if consecutive_failures > 0:
                log(f"Bob is back online after {consecutive_failures} failures")
            consecutive_failures = 0
        else:
            consecutive_failures += 1
            log(f"Bob OFFLINE ({consecutive_failures} consecutive checks)")
            
            if consecutive_failures >= 3:  # 3 checks = 90 seconds of downtime
                log("Bob has been down for 3 checks. Attempting restart...")
                if restart_bob():
                    consecutive_failures = 0
                else:
                    log("Restart failed. Will retry next cycle.")
        
        time.sleep(CHECK_INTERVAL)
    
    log("Watchdog stopped.")


if __name__ == "__main__":
    main()
