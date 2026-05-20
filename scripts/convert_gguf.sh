#!/bin/bash
# Convert HF merged model → GGUF Q4_K_M on A100
set -euo pipefail

log() { echo "=== [$(date '+%H:%M:%S')] $1 ==="; }

log "Building llama.cpp with CUDA..."
cd /root
if [ ! -d llama.cpp ]; then
    git clone --depth 1 https://github.com/ggerganov/llama.cpp.git
fi
cd llama.cpp
cmake -B build -DGGML_CUDA=ON -DCMAKE_BUILD_TYPE=Release
cmake --build build -j$(nproc) --config Release

log "Converting HF model to GGUF FP16..."
python convert_hf_to_gguf.py /root/final-merged --outtype f16 --outfile /root/final-merged-f16.gguf

log "FP16 GGUF size:"
ls -lh /root/final-merged-f16.gguf

log "Quantizing to Q4_K_M..."
./build/bin/llama-quantize /root/final-merged-f16.gguf /root/superezio-ceo-intent-merged.Q4_K_M.gguf Q4_K_M

log "Final GGUF size:"
ls -lh /root/superezio-ceo-intent-merged.Q4_K_M.gguf

log "Computing SHA256..."
sha256sum /root/superezio-ceo-intent-merged.Q4_K_M.gguf > /root/superezio-ceo-intent-merged.Q4_K_M.gguf.sha256
cat /root/superezio-ceo-intent-merged.Q4_K_M.gguf.sha256

log "DONE"
