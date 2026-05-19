#!/bin/bash
# SuperEzio — Complete Rebuild Pipeline (CEO merge → Intent train → Merge → GGUF)
# For RTX PRO 6000 (Blackwell sm_120) / H100 (Hopper sm_90)
set -euo pipefail

CEPO_ADAPTER="${1:-checkpoint-2600}"
INTENT_DATA="${2:-intent_training.jsonl}"
FINAL_GGUF="${3:-qwen36-intent-f51.Q4_K_M.gguf}"

echo "============================================"
echo "SuperEzio Full Rebuild Pipeline"
echo "Started: $(date)"
echo "GPU: $(nvidia-smi --query-gpu=name --format=csv,noheader 2>/dev/null || echo '?')"
echo "VRAM: $(nvidia-smi --query-gpu=memory.free --format=csv,noheader 2>/dev/null || echo '?')"
echo "Disk: $(df -h / | tail -1 | awk '{print $4}') available"
echo "============================================"

# ── Detect GPU arch ─────────────────────────────────────────────────────
COMPUTE_CAP=$(nvidia-smi --query-gpu=compute_cap --format=csv,noheader | head -1)
echo "Compute Capability: $COMPUTE_CAP"

if [ "$COMPUTE_CAP" -ge 120 ]; then
    echo "Blackwell GPU detected (sm_120) — using PyTorch nightly"
    pip install --quiet torch torchvision torchaudio --index-url https://download.pytorch.org/whl/nightly/cu130
else
    echo "Hopper/Ampere GPU — using PyTorch stable"
    pip install --quiet torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu124
fi

pip install --quiet "transformers>=4.51.0" "accelerate>=1.0.0" "peft>=0.14.0"
pip install --quiet "datasets>=3.0.0" "sentencepiece"

python -c "
import torch; print(f'PyTorch {torch.__version__} | CUDA: {torch.cuda.is_available()}')
import transformers; print(f'Transformers {transformers.__version__}')
import peft; print(f'PEFT {peft.__version__}')
"

# ── Extract code tarball (disk-only — NO git clone) ─────────────────────
cd /root
if [ ! -d "SuperEzio" ]; then
    tar -xzf /tmp/superezio-code.tar.gz -C /root
    mv /root/superezio-code /root/SuperEzio 2>/dev/null || true
    # fallback: tarball may extract directly to SuperEzio
    [ -d "SuperEzio" ] || tar -xzf /tmp/superezio-code.tar.gz
fi
cd SuperEzio

# Apply patches
sed -i 's/output_dir=ns.output,/output_dir=ns.output_dir,/' scripts/finetune_qwen36_sft.py
sed -i 's/attn_implementation="flash_attention_2"/attn_implementation="sdpa"/' scripts/finetune_qwen36_sft.py

# ── Step 1: Merge CEO LoRA ──────────────────────────────────────────────
echo ""
echo "[1/5] Merging CEO LoRA into base model..."
python scripts/run_merge_patched.py \
    --base Qwen/Qwen3.6-35B-A3B \
    --adapter "$CEPO_ADAPTER" \
    --output merged-ceo \
    --dtype fp16

echo "Merged CEO model size:"
du -sh merged-ceo

# ── Step 2: Train Intent LoRA ───────────────────────────────────────────
echo ""
echo "[2/5] Training Intent Classifier LoRA..."

# Monkey-patch for PEFT compatibility
cat > /tmp/run_intent_train.py << 'PYEOF'
import sys, os
os.chdir('/root/SuperEzio')
from transformers.core_model_loading import WeightConverter
_orig_wc_init = WeightConverter.__init__
def _patched_wc_init(self, source_patterns, target_patterns, operations, **kwargs):
    _orig_wc_init(self, source_patterns, target_patterns, operations)
WeightConverter.__init__ = _patched_wc_init
import peft.utils.transformers_weight_conversion as twc
_orig_build = twc.build_peft_weight_mapping
def _patched_build(weight_conversions, adapter_name=None, peft_config=None):
    try:
        return _orig_build(weight_conversions, adapter_name=adapter_name, peft_config=peft_config)
    except TypeError as e:
        if 'distributed_operation' in str(e):
            return weight_conversions
        raise
twc.build_peft_weight_mapping = _patched_build
sys.argv = ['finetune', '--model', '/root/SuperEzio/merged-ceo', '--dataset', 'data/intent_training.jsonl', '--output-dir', 'output/qwen36-intent', '--lora-r', '32', '--lora-alpha', '64', '--lora-dropout', '0.05', '--epochs', '2', '--batch-size', '1', '--gradient-accumulation', '16', '--save-steps', '50', '--learning-rate', '2e-4', '--max-seq-length', '4096']
import runpy
runpy.run_path('scripts/finetune_qwen36_sft.py', run_name='__main__')
PYEOF

python /tmp/run_intent_train.py

echo "Intent adapter size:"
du -sh output/qwen36-intent/final

# ── Step 3: Merge Intent into CEO ───────────────────────────────────────
echo ""
echo "[3/5] Merging Intent LoRA into CEO model..."
python scripts/run_merge_patched.py \
    --base merged-ceo \
    --adapter output/qwen36-intent/final \
    --output final-merged \
    --dtype fp16

echo "Final merged model size:"
du -sh final-merged

# ── Step 4: Convert to GGUF Q4_K_M ──────────────────────────────────────
echo ""
echo "[4/5] Building llama.cpp and converting to GGUF Q4_K_M..."

if [ ! -d "llama.cpp" ]; then
    git clone --depth 1 https://github.com/ggerganov/llama.cpp.git
fi
cd llama.cpp
cmake -B build -DGGML_CUDA=ON
cmake --build build --config Release -j$(nproc)
cd ..

python llama.cpp/convert_hf_to_gguf.py \
    final-merged \
    --outfile /tmp/qwen36-intent-f51.F16.gguf \
    --outtype f16

echo "FP16 GGUF:"
ls -lh /tmp/qwen36-intent-f51.F16.gguf

llama.cpp/build/bin/llama-quantize \
    /tmp/qwen36-intent-f51.F16.gguf \
    "/root/SuperEzio/$FINAL_GGUF" \
    Q4_K_M

echo ""
echo "Final Q4_K_M GGUF:"
ls -lh "/root/SuperEzio/$FINAL_GGUF"
sha256sum "/root/SuperEzio/$FINAL_GGUF"

# ── Step 5: Start HTTP server for download ──────────────────────────────
echo ""
echo "[5/5] Starting HTTP server for download..."
echo "URL: http://$(hostname -I | awk '{print $1}'):8080/$FINAL_GGUF"
cd /root/SuperEzio
python -m http.server 8080 &
echo "HTTP server PID: $!"

echo ""
echo "============================================"
echo "Pipeline complete! $(date)"
echo "GGUF: /root/SuperEzio/$FINAL_GGUF"
echo "HTTP: http://$(hostname -I | awk '{print $1}'):8080/$FINAL_GGUF"
echo "============================================"
