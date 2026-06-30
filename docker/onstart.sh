#!/bin/bash
set -e
cd /workspace

echo "[F51] Starting training box"
mkdir -p /workspace/models /workspace/datasets /workspace/outputs /workspace/logs
env >> /etc/environment
nvidia-smi > /workspace/logs/gpu.txt
echo "[F51] Ready"
