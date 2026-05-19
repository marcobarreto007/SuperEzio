#!/usr/bin/env bash
# =============================================================================
# SuperEzio — Intent Classifier LoRA on top of CEO Model
# =============================================================================
# PIPELINE:
#   1. Download base Qwen3.6-35B-A3B
#   2. Merge CEO LoRA (checkpoint-2600) into base → ceo-merged
#   3. Train intent LoRA on ceo-merged (648 examples)
#   4. Merge intent LoRA into ceo-merged → final-merged
#   5. Convert final-merged to GGUF (Q4_K_M)
#
# VAST.AI INSTANCE: 4x RTX PRO 6000 96GB ($3.70/hr total)
# ESTIMATED TIME: ~2.5h total
#   - PyTorch upgrade: 10 min
#   - Model download: 20 min
#   - CEO merge: 15 min
#   - Intent training: 15-30 min (648 examples, 2 epochs)
#   - Intent merge: 15 min
#   - GGUF conversion: 30-60 min
# ESTIMATED COST: ~$9
#
# USAGE:
#   1. Upload local files to vast.ai. Do not clone from GitHub.
#      rsync/scp this local SuperEzio tree to vast:/root/SuperEzio/
#      scp output/qwen36-sft/checkpoint-2600/* vast:/root/ceo-checkpoint/
#      scp data/intent_training.jsonl vast:/root/
#      upload or preinstall llama.cpp at vast:/root/SuperEzio/llama.cpp/
#      scp scripts/vastai_setup_intent.sh vast:/root/
#   2. SSH and run:
#      bash vastai_setup_intent.sh
# =============================================================================

set -euo pipefail

START_TIME=$(date +%s)
echo "============================================"
echo "SuperEzio Intent Classifier — Full Pipeline"
echo "Started: $(date)"
echo "============================================"

# ── Check GPU ──────────────────────────────────────────────────────────
echo ""
echo "[1/8] Checking GPU..."
nvidia-smi --query-gpu=name,memory.total --format=csv,noheader
GPU_COUNT=$(nvidia-smi --query-gpu=name --format=csv,noheader | wc -l)
echo "GPU count: $GPU_COUNT"

# ── Install deps ───────────────────────────────────────────────────────
echo ""
echo "[2/8] Installing dependencies..."

# Upgrade PyTorch to CUDA 12.4 (base image has 2.2.1 with CUDA 12.1)
echo "  Upgrading PyTorch to CUDA 12.4..."
pip install --quiet torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu124

echo "  Installing ML libraries..."
pip install --quiet transformers>=4.51.0 accelerate>=1.0.0 peft>=0.14.0
pip install --quiet datasets>=3.0.0 bitsandbytes>=0.45.0

python -c "
import torch; print(f'PyTorch {torch.__version__} | CUDA: {torch.cuda.is_available()} | GPUs: {torch.cuda.device_count()}')
import transformers; print(f'Transformers {transformers.__version__}')
import peft; print(f'PEFT {peft.__version__}')
"

# ── Clone repo ─────────────────────────────────────────────────────────
echo ""
echo "[3/8] Setting up repo..."
cd /root
if [ ! -d SuperEzio ]; then
    echo "ERROR: /root/SuperEzio not found."
    echo "This project is DISK ONLY. Upload the local SuperEzio tree to /root/SuperEzio before running."
    exit 1
fi
cd SuperEzio

# ── Place CEO checkpoint + intent dataset ──────────────────────────────
echo ""
echo "[4/8] Verifying CEO checkpoint + intent dataset..."

CEO_CKPT="/root/ceo-checkpoint"
INTENT_DATA="/root/intent_training.jsonl"

if [ ! -f "$CEO_CKPT/adapter_model.safetensors" ]; then
    echo "ERROR: CEO checkpoint not found at $CEO_CKPT/"
    echo "Upload it first: scp -r output/qwen36-sft/checkpoint-2600/* vast:/root/ceo-checkpoint/"
    exit 1
fi
echo "CEO checkpoint: $(du -sh $CEO_CKPT | cut -f1)"

if [ ! -f "$INTENT_DATA" ]; then
    echo "ERROR: Intent dataset not found at $INTENT_DATA"
    echo "Upload it first: scp data/intent_training.jsonl vast:/root/"
    exit 1
fi
EXAMPLES=$(wc -l < "$INTENT_DATA")
echo "Intent dataset: $EXAMPLES examples"

# ── Merge CEO LoRA → ceo-merged ────────────────────────────────────────
echo ""
echo "[5/8] Merging CEO LoRA (checkpoint-2600) into base model..."
echo "       This produces the CEO model in HF format for intent training."

python scripts/merge_qwen36_lora.py \
    --base Qwen/Qwen3.6-35B-A3B \
    --adapter "$CEO_CKPT" \
    --output /root/SuperEzio/ceo-merged \
    --dtype fp16

echo "CEO merged model saved to: ceo-merged/"
echo "Size: $(du -sh ceo-merged | cut -f1)"

# ── Train intent LoRA on CEO model ─────────────────────────────────────
echo ""
echo "[6/8] Training intent classifier LoRA on CEO model..."
echo "       Base model: ceo-merged/ (CEO already merged)"
echo "       Dataset: $EXAMPLES examples"
echo "       GPUs: $GPU_COUNT"

# Multi-GPU if available
if [ "$GPU_COUNT" -ge 2 ]; then
    TRAIN_CMD="accelerate launch --num_processes $GPU_COUNT"
else
    TRAIN_CMD="python"
fi

$TRAIN_CMD scripts/finetune_qwen36_sft.py \
    --model /root/SuperEzio/ceo-merged \
    --dataset "$INTENT_DATA" \
    --output-dir /root/SuperEzio/output/qwen36-intent \
    --epochs 2 \
    --batch-size 1 \
    --gradient-accumulation 4 \
    --learning-rate 1e-4 \
    --lora-r 32 \
    --lora-alpha 64 \
    --max-seq-length 2048 \
    --save-steps 50 \
    --warmup-ratio 0.05

echo "Intent LoRA training complete."
echo "Output: output/qwen36-intent/"

# ── Merge intent LoRA → final-merged ───────────────────────────────────
echo ""
echo "[7/8] Merging intent LoRA into CEO model..."

# Find the best/final intent checkpoint
INTENT_CKPT="/root/SuperEzio/output/qwen36-intent/final"
if [ ! -d "$INTENT_CKPT" ]; then
    # Use the latest checkpoint
    INTENT_CKPT=$(ls -d /root/SuperEzio/output/qwen36-intent/checkpoint-* 2>/dev/null | sort -V | tail -1)
fi
echo "Intent checkpoint: $INTENT_CKPT"

python scripts/merge_qwen36_lora.py \
    --base /root/SuperEzio/ceo-merged \
    --adapter "$INTENT_CKPT" \
    --output /root/SuperEzio/final-merged \
    --dtype fp16

echo "Final merged model saved to: /root/SuperEzio/final-merged/"
echo "Size: $(du -sh /root/SuperEzio/final-merged | cut -f1)"

# ── Convert to GGUF ────────────────────────────────────────────────────
echo ""
echo "[8/8] Converting to GGUF (Q4_K_M)..."
echo "       This may take 30-60 minutes."

if [ ! -d llama.cpp ]; then
    echo "ERROR: llama.cpp not found at /root/SuperEzio/llama.cpp."
    echo "This script must not clone from GitHub. Upload or preinstall llama.cpp before running."
    exit 1
fi

if [ ! -f llama.cpp/convert_hf_to_gguf.py ]; then
    echo "ERROR: llama.cpp/convert_hf_to_gguf.py not found."
    echo "Upload a complete llama.cpp tree before running."
    exit 1
fi

if [ ! -x llama.cpp/build/bin/llama-quantize ] && [ ! -x llama.cpp/build/bin/llama-quantize.exe ]; then
    echo "Building uploaded llama.cpp locally..."
    cd llama.cpp
    cmake -B build -DGGML_CUDA=ON
    cmake --build build --config Release -j$(nproc)
    cd ..
fi

python llama.cpp/convert_hf_to_gguf.py \
    /root/SuperEzio/final-merged \
    --outtype q4_k_m \
    --outfile /root/SuperEzio/qwen36-intent-f51.Q4_K_M.gguf

echo ""
echo "============================================"
echo "PIPELINE COMPLETE"
echo "============================================"
echo "GGUF model: /root/SuperEzio/qwen36-intent-f51.Q4_K_M.gguf"
echo ""

ELAPSED=$(($(date +%s) - START_TIME))
echo "Total time: $((ELAPSED / 3600))h $(((ELAPSED % 3600) / 60))m"
echo ""
echo "Download the model:"
echo "  scp -P 29754 root@ssh6.vast.ai:/root/SuperEzio/qwen36-intent-f51.Q4_K_M.gguf ."
echo ""
echo "Then replace the CEO model:"
echo "  cp qwen36-intent-f51.Q4_K_M.gguf models/qwen36-35b-f51.Q4_K_M.gguf"
echo "============================================"
