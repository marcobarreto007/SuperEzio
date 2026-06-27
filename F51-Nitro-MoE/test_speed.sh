#!/bin/bash
export F51_MOE_CACHE=1
export F51_CACHE_CAP=26
export F51_DEBUG=1
export F51_LAYER2_ENABLED=1

# Matar qualquer server antigo
pkill llama-server.exe 2>/dev/null
sleep 1

# Iniciar server
/mnt/c/llama.cpp/build/bin/llama-server.exe \
  -m "C:\\F51_LAB\\models\\glm\\IQ4_XS\\GLM-4.5-Air-IQ4_XS-00001-of-00002.gguf" \
  --port 8080 \
  -c 2048 \
  -np 4 \
  --no-warmup \
  > /mnt/c/F51_LAB/f51_stdout.log \
  2> /mnt/c/F51_LAB/f51_stderr.log &

echo "Server PID=$!"

# Aguardar server ficar pronto
echo "Aguardando server..."
for i in $(seq 1 30); do
  if curl -s http://localhost:8080/completion -H "Content-Type: application/json" -d '{"prompt":"Hi","n_predict":1}' > /dev/null 2>&1; then
    echo "Server ONLINE!"
    break
  fi
  sleep 2
done

echo ""
echo "=== TESTE DE VELOCIDADE ==="
START=$(date +%s%N)
RESULT=$(curl -s http://localhost:8080/completion \
  -H "Content-Type: application/json" \
  -d '{"prompt":"The capital of France is","n_predict":50,"temperature":0}')
END=$(date +%s%N)
ELAPSED=$(( (END - START) / 1000000 ))

echo "Tempo total: ${ELAPSED}ms"
echo ""
echo "Resposta:"
echo "$RESULT" | head -c 500
echo ""
echo ""
echo "=== F51 CACHE LOG ==="
tail -5 /mnt/c/F51_LAB/f51_moe_cache.log 2>/dev/null
echo ""
echo "=== SERVER LOG ==="
tail -10 /mnt/c/F51_LAB/f51_stderr.log 2>/dev/null | grep -E 'F51|listen|slot|timing'
