#!/bin/bash
# ============================================
#  F51 Nitro-MoE — Layer 2 Boot
#  Modelo: GLM-4.5-Air IQ4_XS
#  Binario: Windows F51 (Blackwell nativo)
# ============================================

export F51_MOE_CACHE=1
export F51_CACHE_CAP=26
export F51_DEBUG=1
export GGML_OP_OFFLOAD_MIN_BATCH=1
export F51_LAYER2_ENABLED=1

# Caminhos
BIN="/mnt/c/llama.cpp/build/bin/llama-server.exe"
MODEL_DIR="/mnt/c/F51_LAB/models/glm"
MODEL=$(ls "$MODEL_DIR"/*-00001-of-*.gguf 2>/dev/null | head -1)

# Se nao achou no Windows, procura no WSL e copia
if [ -z "$MODEL" ]; then
    echo "Procurando modelo no cache WSL..."
    for f in /home/marco/models/glm/IQ4_XS/*-00001-of-*.gguf; do
        if [ -f "$f" ]; then
            echo "Copiando $f para $MODEL_DIR ..."
            mkdir -p "$MODEL_DIR"
            cp /home/marco/models/glm/IQ4_XS/*.gguf "$MODEL_DIR/"
            MODEL=$(ls "$MODEL_DIR"/*-00001-of-*.gguf 2>/dev/null | head -1)
            break
        fi
    done
fi

if [ -z "$MODEL" ]; then
    echo "ERRO: Modelo GLM-4.5-Air nao encontrado!"
    echo "Verifique: $MODEL_DIR"
    exit 1
fi

echo "============================================"
echo "  F51 Nitro-MoE — Layer 2 ENABLED"
echo "============================================"
echo "Modelo:  $MODEL"
echo "Binario: $BIN"
echo "GPU:"
nvidia-smi --query-gpu=memory.free,memory.total --format=csv
echo ""
echo "Iniciando servidor em http://0.0.0.0:8080 ..."
echo ""

"$BIN" \
    -m "$MODEL" \
    --host 0.0.0.0 \
    --port 8080 \
    -ngl 999 \
    -c 2048 \
    -np 4 \
    > /mnt/c/F51_LAB/f51_server_stdout.log \
    2> /mnt/c/F51_LAB/f51_server_stderr.log
