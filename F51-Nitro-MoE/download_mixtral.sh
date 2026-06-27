#!/bin/bash
export HF_TOKEN="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"

mkdir -p /mnt/c/F51_LAB/models/mixtral-new
cd /mnt/c/F51_LAB/models/mixtral-new

echo "Baixando Mixtral 8x7B Q4_K_M - 24GB"
echo "Destino: /mnt/c/F51_LAB/models/mixtral-new/"

curl -L --progress-bar \
  -H "Authorization: Bearer $HF_TOKEN" \
  -o mixtral-8x7b-instruct-v0.1-Q4_K_M.gguf \
  "https://huggingface.co/bartowski/Mixtral-8x7B-Instruct-v0.1-GGUF/resolve/main/Mixtral-8x7B-Instruct-v0.1-Q4_K_M.gguf"

echo "Download concluido!"
ls -lh mixtral-8x7b-instruct-v0.1-Q4_K_M.gguf
