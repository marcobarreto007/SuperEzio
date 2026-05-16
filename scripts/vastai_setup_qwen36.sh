#!/bin/bash
# =============================================================================
# SuperEzio — Qwen3.6-35B-A3B QLoRA Training Setup for Vast.ai
# =============================================================================
# GPU requirements: 48GB VRAM minimum (A100 80GB, L40S 48GB, or 2x L40S)
# Qwen3.6-35B in 4-bit: ~20GB + LoRA adapters + optimizer = ~35GB
# Estimated time: 10-15h for 1 epoch on 410K samples
#
# Usage (on vast.ai SSH):
#   chmod +x vastai_setup_qwen36.sh
#   ./vastai_setup_qwen36.sh
#   screen -S train
#   python scripts/finetune_qwen36_sft.py --epochs 1 --batch-size 1 --gradient-accumulation 16
#
# Monitor:
#   screen -r train
#   nvidia-smi
#   tail -f output/qwen36-sft/training.log
# =============================================================================

set -euo pipefail

echo "============================================"
echo "SuperEzio Qwen3.6-35B-A3B QLoRA Training Setup"
echo "============================================"

# ── Check GPU ──────────────────────────────────────────────────────────
echo ""
echo "[1/6] Checking GPU..."
nvidia-smi --query-gpu=name,memory.total --format=csv,noheader
GPU_COUNT=$(nvidia-smi --query-gpu=name --format=csv,noheader | wc -l)
echo "GPU count: $GPU_COUNT"

VRAM_MB=$(nvidia-smi --query-gpu=memory.total --format=csv,noheader,nounits | head -1)
VRAM_GB=$((VRAM_MB / 1024))
echo "VRAM: ${VRAM_GB}GB"

if [ "$VRAM_GB" -lt 40 ]; then
    echo "WARNING: Less than 40GB VRAM. Qwen3.6-35B QLoRA needs ~35GB."
    echo "With ${VRAM_GB}GB you may need --batch-size 1 --max-seq-length 2048"
fi

# ── Install CUDA 12.4 PyTorch ──────────────────────────────────────────
echo ""
echo "[2/6] Installing PyTorch with CUDA 12.4..."
pip install --quiet torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu124

# ── Install training dependencies ──────────────────────────────────────
echo ""
echo "[3/6] Installing training packages..."
pip install --quiet transformers>=4.51.0 accelerate>=1.0.0 peft>=0.14.0 bitsandbytes>=0.45.0
pip install --quiet datasets>=3.0.0

# Verify
python -c "
import torch; print(f'PyTorch {torch.__version__} | CUDA: {torch.cuda.is_available()}')
import transformers; print(f'Transformers {transformers.__version__}')
import peft; print(f'PEFT {peft.__version__}')
import bitsandbytes; print(f'BitsAndBytes {bitsandbytes.__version__}')
import accelerate; print(f'Accelerate {accelerate.__version__}')
"

# ── Clone repo (if not already) ────────────────────────────────────────
echo ""
echo "[4/6] Setting up repo..."
cd /root
if [ ! -d "SuperEzio" ]; then
    git clone https://github.com/marcobarreto007/xumoney-local-ai.git SuperEzio
fi
cd SuperEzio
git pull origin main

# ── Verify dataset ─────────────────────────────────────────────────────
echo ""
echo "[5/6] Checking dataset..."
DATASET="F51_Datasets/sft_output/f51_final_sft.jsonl"
if [ -f "$DATASET" ]; then
    ENTRIES=$(wc -l < "$DATASET")
    SIZE=$(du -h "$DATASET" | cut -f1)
    echo "Dataset: $ENTRIES entries, $SIZE"
else
    echo "WARNING: Dataset not found at $DATASET"
    echo "Training will fail. Make sure the repo has the dataset committed with Git LFS."
fi

# ── Create output directory ────────────────────────────────────────────
echo ""
echo "[6/6] Creating output directory..."
mkdir -p output/qwen36-sft

echo ""
echo "============================================"
echo "Setup complete!"
echo ""
echo "Start training:"
echo "  screen -S train"
echo "  cd /root/SuperEzio"
echo "  python scripts/finetune_qwen36_sft.py \\"
echo "    --model Qwen/Qwen3.6-35B-A3B \\"
echo "    --dataset F51_Datasets/sft_output/f51_final_sft.jsonl \\"
echo "    --output-dir output/qwen36-sft \\"
echo "    --epochs 1 --batch-size 1 --gradient-accumulation 16"
echo ""
echo "Multi-GPU (if 2 GPUs available):"
echo "  accelerate launch --num_processes 2 scripts/finetune_qwen36_sft.py ..."
echo ""
echo "Download trained adapter back:"
echo "  scp -r root@<vastai-ip>:/root/SuperEzio/output/qwen36-sft/final/ ."
echo "============================================"
