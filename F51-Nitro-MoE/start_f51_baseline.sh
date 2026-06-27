#!/bin/bash
# F51 Nitro-MoE — Baseline (Layer 2 DISABLED)
# Server start script for WSL/Ubuntu

export F51_MOE_CACHE=1
export F51_CACHE_CAP=26
export F51_DEBUG=1
export GGML_OP_OFFLOAD_MIN_BATCH=1
export F51_LAYER2_ENABLED=0

MODEL="/mnt/c/Users/marco/Desktop/F51-Nitro-MoE/F51_Nitro_20GB_DualGPU/models/Mixtral-8x7B-Instruct-v0.1-GGUF/mixtral-8x7b-instruct-v0.1.Q4_K_M.gguf"

echo "=== F51 Nitro-MoE Baseline (Layer 2 DISABLED) ==="
echo "Model: $MODEL"
echo "Starting server on http://0.0.0.0:8080 ..."

~/f51-llama.cpp/build-cuda/bin/llama-server \
  -m "$MODEL" \
  --host 0.0.0.0 \
  --port 8080 \
  -ngl 18 \
  -c 2048 \
  -np 4 \
  > /mnt/c/F51_LAB/f51_server_stdout.log \
  2> /mnt/c/F51_LAB/f51_server_stderr.log
