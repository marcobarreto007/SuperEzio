#!/usr/bin/env python
import os
import subprocess
import time

PROXY_SCRIPT = os.path.join(os.path.dirname(__file__), "qwen_proxy.py")
PYTHON = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".venv", "Scripts", "python.exe")

print("Starting Qwen Proxy on http://127.0.0.1:8787...")
proc = subprocess.Popen(
    [PYTHON, PROXY_SCRIPT], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
)
time.sleep(2)
print("Proxy PID:", proc.pid)
print()
print("Agora digite: bob")
print("O Claude Code vai usar Qwen Cloud via proxy local.")
