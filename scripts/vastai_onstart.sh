#!/bin/bash
# SuperEzio — Qwen3.6-35B Full LoRA 3h Timebox Training on Vast.ai
# GPU: RTX PRO 6000 WS 96GB, CUDA 12.8
# Uses train_qwen36_3h.py — checkpoints every 200 steps, self-healing, email notification
set -euo pipefail

echo "============================================"
echo "SuperEzio Qwen3.6-35B Full LoRA 3h Training"
echo "Started: $(date)"
echo "============================================"

# ── Install PyTorch CUDA 12.4 ───────────────────────────────────────
echo "[1/5] Installing PyTorch..."
pip install --quiet torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu124

# ── Install training deps ──────────────────────────────────────────
echo "[2/5] Installing training packages..."
pip install --quiet "transformers>=4.51.0" "accelerate>=1.0.0" "peft>=0.14.0"
pip install --quiet "datasets>=3.0.0"

# Verify
python -c "
import torch; print(f'PyTorch {torch.__version__} | CUDA: {torch.cuda.is_available()} | GPU: {torch.cuda.get_device_name(0)}')
import transformers; print(f'Transformers {transformers.__version__}')
import peft; print(f'PEFT {peft.__version__}')
import accelerate; print(f'Accelerate {accelerate.__version__}')
print(f'VRAM: {torch.cuda.get_device_properties(0).total_mem / 1e9:.1f} GB')
"

# ── Clone repo ─────────────────────────────────────────────────────
echo "[3/5] Cloning SuperEzio repo..."
cd /root
if [ ! -d "SuperEzio" ]; then
    git clone https://github.com/marcobarreto007/xumoney-local-ai.git SuperEzio
fi
cd SuperEzio
git pull origin main

# ── Verify dataset ─────────────────────────────────────────────────
echo "[4/5] Checking dataset..."
DATASET="F51_Datasets/sft_output/f51_sft_20k.jsonl"
if [ -f "$DATASET" ]; then
    ENTRIES=$(wc -l < "$DATASET")
    echo "Dataset: $ENTRIES entries"
else
    echo "WARNING: Dataset not found at $DATASET"
fi

# ── Start 3h timebox training ──────────────────────────────────────
echo "[5/5] Starting 3h timebox training with checkpoints + self-healing..."
mkdir -p output/qwen36-sft

export PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True

python scripts/train_qwen36_3h.py \
    --model Qwen/Qwen3.6-35B-A3B \
    --dataset F51_Datasets/sft_output/f51_sft_20k.jsonl \
    --output-dir output/qwen36-sft \
    --epochs 1 \
    --batch-size 1 \
    --gradient-accumulation 16 \
    --learning-rate 2e-4 \
    --lora-r 64 \
    --lora-alpha 128 \
    --max-seq-length 4096 \
    --save-steps 200 \
    --timebox-hours 3 \
    --warmup-ratio 0.03 \
    2>&1 | tee output/qwen36-sft/training.log

echo "Training complete: $(date)"
