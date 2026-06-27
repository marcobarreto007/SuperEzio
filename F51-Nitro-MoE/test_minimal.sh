#!/bin/bash
pkill llama-server.exe 2>/dev/null
sleep 1

export F51_MOE_CACHE=1
export F51_CACHE_CAP=26
export F51_DEBUG=1
export F51_LAYER2_ENABLED=1

/mnt/c/llama.cpp/build/bin/llama-server.exe \
  -m "C:\\F51_LAB\\models\\glm\\IQ4_XS\\GLM-4.5-Air-IQ4_XS-00001-of-00002.gguf" \
  --port 8080 -c 128 -np 1 --no-warmup \
  > /mnt/c/F51_LAB/f51_stdout.log \
  2> /mnt/c/F51_LAB/f51_stderr.log &

echo "Aguardando 45s..."
sleep 45

echo "=== TESTE ==="
curl -s -m 90 http://localhost:8080/completion \
  -H "Content-Type: application/json" \
  -d '{"prompt":"The capital of France is","n_predict":5,"temperature":0}' \
  2>/dev/null

echo ""
echo "=== F51 LOG ==="
tail -10 /mnt/c/F51_LAB/f51_stderr.log | grep -E 'F51|listen|error|timing|token'
