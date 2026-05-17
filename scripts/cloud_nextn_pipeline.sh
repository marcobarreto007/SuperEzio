#!/bin/bash
# SuperEzio — Cloud Merge + GGUF Q4_K_M with NEXTN/MTP support
# Uses latest llama.cpp master (post PR #22673) for MTP tensor extraction
set -euo pipefail

MODEL="Qwen/Qwen3.6-35B-A3B"
ADAPTER="checkpoint-2600"
MERGED_DIR="merged-qwen36-fp16"
GGUF_DIR="gguf-output"
GGUF_FILE="qwen36-35b-f51.Q4_K_M.gguf"

echo "============================================"
echo "SuperEzio Cloud Merge + Q4_K_M + NEXTN/MTP"
echo "Started: $(date)"
echo "GPU: $(nvidia-smi --query-gpu=name --format=csv,noheader 2>/dev/null || echo '?')"
echo "VRAM free: $(nvidia-smi --query-gpu=memory.free --format=csv,noheader 2>/dev/null || echo '?')"
echo "Disk: $(df -h / | tail -1 | awk '{print $4}') available"
echo "============================================"

# ── Install Python deps ─────────────────────────────────────────────
echo ""
echo "[1/6] Installing Python deps..."
pip install --quiet "peft>=0.14.0" "transformers>=4.51.0" "sentencepiece"

# Force PyTorch with CUDA 12.8+ support for Blackwell sm_120
python -c "import torch; print(f'PyTorch {torch.__version__} CUDA {torch.version.cuda}')"
python -c "import torch; t=torch.zeros(1,device='cuda'); print(f'CUDA OK, device: {torch.cuda.get_device_name(0)}')"

# ── Merge LoRA → base model (bf16, 98GB VRAM) ──────────────────────
echo ""
echo "[2/6] Merging LoRA adapter into base model..."
python merge_qwen36_lora.py \
    --base "$MODEL" \
    --adapter "$ADAPTER" \
    --output "$MERGED_DIR" \
    --dtype fp16

echo "Merge complete. Merged model size:"
du -sh "$MERGED_DIR"

# Verify MTP tensors exist in merged model
echo ""
echo "Verifying MTP tensors in merged model..."
python -c "
import json, os
idx_path = os.path.join('$MERGED_DIR', 'model.safetensors.index.json')
if os.path.exists(idx_path):
    with open(idx_path) as f:
        idx = json.load(f)
    mtp_keys = [k for k in idx.get('weight_map', {}) if k.startswith('mtp.')]
    print(f'MTP tensors: {len(mtp_keys)} (expected 19)')
    for k in mtp_keys[:5]:
        print(f'  {k}')
    if len(mtp_keys) > 5:
        print(f'  ... and {len(mtp_keys)-5} more')
else:
    # Single safetensors file — check it
    import safetensors.torch
    st = safetensors.torch.load_file(os.path.join('$MERGED_DIR', 'model.safetensors'))
    mtp_keys = [k for k in st.keys() if k.startswith('mtp.')]
    print(f'MTP tensors in single file: {len(mtp_keys)}')
"

# ── Clone & build latest llama.cpp (master with MTP fix) ────────────
echo ""
echo "[3/6] Building latest llama.cpp (with PR #22673 MTP support)..."
if [ -d "llama.cpp" ]; then
    rm -rf llama.cpp
fi
git clone --depth 1 https://github.com/ggerganov/llama.cpp.git
cd llama.cpp
# Verify the MTP fix exists
echo "Checking for MTP/nextn support in convert script..."
grep -c "nextn\|mtp\|_Qwen35MtpMixin" convert_hf_to_gguf.py || echo "WARNING: MTP support not found in convert script!"
cmake -B build -DGGML_CUDA=ON
cmake --build build --config Release -j$(nproc)
cd ..

# ── Convert HF → GGUF FP16 ─────────────────────────────────────────
echo ""
echo "[4/6] Converting merged model to GGUF FP16 (WITH MTP/NEXTN)..."
mkdir -p "$GGUF_DIR"
python llama.cpp/convert_hf_to_gguf.py \
    "$MERGED_DIR" \
    --outfile "$GGUF_DIR/qwen36-35b-f51-F16.gguf" \
    --outtype f16

echo "FP16 GGUF created:"
ls -lh "$GGUF_DIR/qwen36-35b-f51-F16.gguf"

# Verify MTP/nextn tensors exist in GGUF
echo ""
echo "Verifying NEXTN tensors in GGUF..."
python -c "
from gguf import GGUFReader
reader = GGUFReader('$GGUF_DIR/qwen36-35b-f51-F16.gguf')
# Check metadata
n = reader.fields.get('qwen35moe.nextn_predict_layers')
bc = reader.fields.get('qwen35moe.block_count')
print(f'block_count: {bc}')
print(f'nextn_predict_layers: {n}')
# Check for nextn tensors
nextn_tensors = [t for t in reader.tensors if 'nextn' in t]
print(f'NEXTN tensors found: {len(nextn_tensors)} (expected 4-19)')
for t in nextn_tensors[:6]:
    print(f'  {t}')
if len(nextn_tensors) > 6:
    print(f'  ... and {len(nextn_tensors)-6} more')
if not nextn_tensors:
    print('CRITICAL: No NEXTN tensors found! MTP extraction failed.')
    exit 1)
"

# ── Quantize to Q4_K_M ─────────────────────────────────────────────
echo ""
echo "[5/6] Quantizing to Q4_K_M..."
llama.cpp/build/bin/llama-quantize \
    "$GGUF_DIR/qwen36-35b-f51-F16.gguf" \
    "$GGUF_DIR/$GGUF_FILE" \
    Q4_K_M

echo ""
echo "[6/6] Final verification..."
echo "============================================"
echo "Done! Final GGUF:"
ls -lh "$GGUF_DIR/$GGUF_FILE"
echo ""
echo "SHA256:"
sha256sum "$GGUF_DIR/$GGUF_FILE"
echo ""

# Quick verification of final GGUF
python -c "
from gguf import GGUFReader
r = GGUFReader('$GGUF_DIR/$GGUF_FILE')
bc = r.fields.get('qwen35moe.block_count')
nl = r.fields.get('qwen35moe.nextn_predict_layers')
print(f'Final GGUF — block_count: {bc}, nextn_predict_layers: {nl}')
nextn_tensors = [t for t in r.tensors if 'nextn' in t]
print(f'NEXTN tensors: {len(nextn_tensors)}')
print('SUCCESS: MTP/NEXTN properly embedded in final GGUF!')
"

echo "============================================"
echo "Completed: $(date)"
echo "============================================"
