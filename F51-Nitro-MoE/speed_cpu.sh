#!/bin/bash
pkill -9 llama-server.exe 2>/dev/null
sleep 2

echo "=== Iniciando servidor CPU-only ==="
/mnt/c/llama.cpp/build/bin/llama-server.exe \
  -m "C:\\F51_LAB\\models\\glm\\IQ4_XS\\GLM-4.5-Air-IQ4_XS-00001-of-00002.gguf" \
  --port 8080 -c 64 -np 1 --no-warmup -ngl 0 \
  > /tmp/srv_out.log 2> /tmp/srv_err.log &

echo "Aguardando 60s para load..."
sleep 60

echo ""
echo "=== TESTE DE VELOCIDADE (CPU-only) ==="
START=$(date +%s%N)
RESULT=$(curl -s -m 300 http://localhost:8080/completion \
  -H "Content-Type: application/json" \
  -d '{"prompt":"The capital of France is","n_predict":10,"temperature":0}' 2>/dev/null)
END=$(date +%s%N)
ELAPSED_MS=$(( (END - START) / 1000000 ))
ELAPSED_S=$(( ELAPSED_MS / 1000 ))

echo "Tempo: ${ELAPSED_MS}ms (${ELAPSED_S}s)"
echo "Resposta: $(echo "$RESULT" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('content','')[:200])" 2>/dev/null)"
echo ""
echo "=== SERVER STATUS ==="
grep -E 'listen|timing|token|F51|error' /tmp/srv_err.log | tail -10
