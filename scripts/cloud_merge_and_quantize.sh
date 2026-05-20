#!/bin/bash
# SuperEzio — Cloud Merge + GGUF Q4_K_M Quantization
# Runs on vast.ai instance with RTX PRO 6000 S (98GB VRAM, 500GB disk)
set -euo pipefail

MODEL="Qwen/Qwen3.6-35B-A3B"
ADAPTER="checkpoint-2600"
MERGED_DIR="merged-qwen36-fp16"
GGUF_DIR="gguf-output"
GGUF_FILE="superezio-ceo-intent-merged.Q4_K_M.gguf"

echo "============================================"
echo "SuperEzio Cloud Merge + Q4_K_M Quantization"
echo "Started: $(date)"
echo "GPU: $(nvidia-smi --query-gpu=name --format=csv,noheader)"
echo "VRAM free: $(nvidia-smi --query-gpu=memory.free --format=csv,noheader)"
echo "Disk: $(df -h / | tail -1 | awk '{print $4}') available"
echo "============================================"

# ── Install Python deps ─────────────────────────────────────────────
echo ""
echo "[1/5] Installing Python deps..."
pip install --quiet "peft>=0.14.0" "transformers>=4.51.0" "sentencepiece"

# ── Merge LoRA → base model (bf16, 98GB VRAM) ──────────────────────
echo ""
echo "[2/5] Merging LoRA adapter into base model..."
python merge_qwen36_lora.py \
    --base "$MODEL" \
    --adapter "$ADAPTER" \
    --output "$MERGED_DIR" \
    --dtype fp16

echo "Merge complete. Merged model size:"
du -sh "$MERGED_DIR"

# ── Clone & build llama.cpp ─────────────────────────────────────────
echo ""
echo "[3/5] Building llama.cpp..."
if [ ! -d "llama.cpp" ]; then
    git clone --depth 1 https://github.com/ggerganov/llama.cpp.git
fi
cd llama.cpp
cmake -B build -DGGML_CUDA=ON
cmake --build build --config Release -j$(nproc)
cd ..

# ── Convert HF → GGUF FP16 ─────────────────────────────────────────
echo ""
echo "[4/5] Converting merged model to GGUF..."
python llama.cpp/convert_hf_to_gguf.py \
    "$MERGED_DIR" \
    --outfile "$GGUF_DIR/superezio-ceo-intent-merged-F16.gguf" \
    --outtype f16

echo "FP16 GGUF created:"
ls -lh "$GGUF_DIR/superezio-ceo-intent-merged-F16.gguf"

# ── Quantize to Q4_K_M ─────────────────────────────────────────────
echo ""
echo "[5/5] Quantizing to Q4_K_M..."
mkdir -p "$GGUF_DIR"
llama.cpp/build/bin/llama-quantize \
    "$GGUF_DIR/superezio-ceo-intent-merged-F16.gguf" \
    "$GGUF_DIR/$GGUF_FILE" \
    Q4_K_M

echo ""
echo "============================================"
echo "Done! Final GGUF:"
ls -lh "$GGUF_DIR/$GGUF_FILE"
echo ""
echo "SHA256:"
sha256sum "$GGUF_DIR/$GGUF_FILE"
echo "============================================"
echo "Completed: $(date)"
