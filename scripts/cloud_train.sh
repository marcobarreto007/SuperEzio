#!/bin/bash
# SuperEzio Cloud Training — Vast.ai A100 80GB
# Usage: bash cloud_train.sh

set -e

INSTANCE_IP="${VAST_AI_IP:-ssh2.vast.ai}"
INSTANCE_PORT="${VAST_AI_PORT:-15024}"
SSH_CMD="ssh -p $INSTANCE_PORT root@$INSTANCE_IP"

echo "=== SuperEzio Cloud Training ==="
echo "Target: $INSTANCE_IP:$INSTANCE_PORT"
echo ""

# Step 1: Upload binaries
echo "[1/3] Uploading llama.cpp binaries..."
scp -P $INSTANCE_PORT \
  C:/llama.cpp/build/bin/llama-finetune-qlora.exe \
  C:/llama.cpp/build/bin/ggml-cuda.dll \
  C:/llama.cpp/build/bin/ggml.dll \
  C:/llama.cpp/build/bin/ggml-base.dll \
  C:/llama.cpp/build/bin/ggml-cpu.dll \
  C:/llama.cpp/build/bin/llama.dll \
  C:/llama.cpp/build/bin/llama-common.dll \
  root@$INSTANCE_IP:/root/llama-bin/

# Step 2: Upload model (biggest file, may take 30-60 min)
echo "[2/3] Uploading model (17.3 GB)..."
scp -P $INSTANCE_PORT \
  C:/llama.cpp/models/bob-core-local.gguf \
  root@$INSTANCE_IP:/root/models/

# Step 3: Upload dataset
echo "[3/3] Uploading dataset..."
scp -P $INSTANCE_PORT \
  "C:/Users/marco/Desktop/SuperEzio Financeiro/temp_gguf_workspace/train_finance.jsonl" \
  root@$INSTANCE_IP:/root/

echo ""
echo "=== Upload complete ==="
echo ""
echo "Starting training on cloud..."

# Launch training
$SSH_CMD << 'ENDSSH'
cd /root
mkdir -p /root/output

echo "=== GPU INFO ==="
nvidia-smi

echo ""
echo "=== STARTING 48/48 FULL TRAINING ==="
echo "Model: bob-core-local.gguf"
echo "Dataset: 116,000 examples"
echo "Config: freeze=0, rank=32, alpha=64, 3 epochs"
echo ""

LD_LIBRARY_PATH=/root/llama-bin ./llama-bin/llama-finetune-qlora \
  --model /root/models/bob-core-local.gguf \
  --train-file /root/train_finance.jsonl \
  --lora-out /root/output/bob_cloud_48layers_rank32.gguf \
  --lora-rank 32 \
  --lora-alpha 64 \
  --learning-rate 2e-5 \
  --epochs 3 \
  --ctx-size 2048 \
  --batch-size 2048 \
  --ubatch-size 512 \
  --val-split 0.05 \
  --grad-checkpoint 48 \
  --shuffle-dataset \
  --freeze-layers 0 \
  --gpu-layers 999 \
  --save-every 1000 \
  --seed 42

echo ""
echo "=== TRAINING COMPLETE ==="
ls -la /root/output/
ENDSSH

echo ""
echo "=== Downloading results ==="
scp -P $INSTANCE_PORT root@$INSTANCE_IP:/root/output/bob_cloud_48layers_rank32.gguf ./models/

echo "Done! LoRA saved to models/bob_cloud_48layers_rank32.gguf"
