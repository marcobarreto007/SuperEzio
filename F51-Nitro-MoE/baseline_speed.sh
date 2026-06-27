#!/bin/bash
pkill llama-server.exe 2>/dev/null
sleep 1

# Sem F51 - baseline
/mnt/c/llama.cpp/build/bin/llama-server.exe \
  -m "C:\\F51_LAB\\models\\glm\\IQ4_XS\\GLM-4.5-Air-IQ4_XS-00001-of-00002.gguf" \
  --port 8080 -c 2048 -np 4 --no-warmup \
  > /dev/null 2>&1 &

echo "Aguardando server (30s)..."
sleep 30

echo "=== TESTE BASELINE (sem F51) ==="
TIME_START=$(date +%s%N)
RESULT=$(curl -s http://localhost:8080/completion \
  -H "Content-Type: application/json" \
  -d '{"prompt":"The capital of France is","n_predict":20,"temperature":0}' 2>/dev/null)
TIME_END=$(date +%s%N)
ELAPSED=$(( (TIME_END - TIME_START) / 1000000 ))

echo "Tempo: ${ELAPSED}ms"
echo "Resposta: $(echo "$RESULT" | head -c 300)"
echo ""
echo "Timings:"
echo "$RESULT" | grep -o '"timings":{[^}]*}' | head -1
