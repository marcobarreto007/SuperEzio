#!/bin/bash
# F51 Nitro-MoE — Boot com upstream llama.cpp
# Modelo: Mixtral 8x7B Q4_K_M

MODEL="/mnt/c/F51_LAB/models/mixtral-new/mixtral-8x7b-instruct-v0.1.Q4_K_M.gguf"

# Se o modelo ainda nao foi copiado, procurar no WSL nativo
if [ ! -f "$MODEL" ]; then
    WSL_MODEL="/home/marco/models/mixtral-new/mixtral-8x7b-instruct-v0.1.Q4_K_M.gguf"
    if [ -f "$WSL_MODEL" ]; then
        echo "Copiando modelo para $MODEL ..."
        mkdir -p "$(dirname "$MODEL")"
        cp "$WSL_MODEL" "$MODEL"
    fi
fi

echo "=== F51 Lab - Mixtral 8x7B Q4_K_M ==="
echo "Modelo: $MODEL"
echo "GPU:"
nvidia-smi --query-gpu=memory.free,memory.total --format=csv
echo ""

# Usar o upstream (f51-merged) que suporta o formato GGUF novo
BIN="/home/marco/f51-merged/build-cuda/bin/llama-server"

echo "Binario: $BIN"
echo "Iniciando servidor em http://0.0.0.0:8080 ..."
echo ""

$BIN \
  -m "$MODEL" \
  --port 8080 \
  --gpu-layers 18 \
  -c 4096 \
  -np 4 \
  > /mnt/c/F51_LAB/server_stdout.log \
  2> /mnt/c/F51_LAB/server_stderr.log
