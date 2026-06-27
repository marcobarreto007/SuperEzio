#!/bin/bash
pkill -9 llama-server.exe 2>/dev/null
sleep 1

echo "=== Iniciando Mixtral Legacy ==="
/mnt/c/Users/marco/Desktop/F51-Nitro-MoE/F51_Nitro_20GB_DualGPU/bin_mixtral_legacy/llama-server.exe \
  -m "C:\\Users\\marco\\Desktop\\F51-Nitro-MoE\\F51_Nitro_20GB_DualGPU\\models\\Mixtral-8x7B-Instruct-v0.1-GGUF\\mixtral-8x7b-instruct-v0.1.Q4_K_M.gguf" \
  --port 8080 -ngl 18 -c 2048 -np 4 \
  > /tmp/mix_out.log 2> /tmp/mix_err.log &

echo "Aguardando 60s..."
sleep 60

echo ""
echo "=== TESTE DE VELOCIDADE ==="
START=$(date +%s%N)
RESULT=$(curl -s -m 300 http://localhost:8080/completion \
  -H "Content-Type: application/json" \
  -d '{"prompt":"The capital of France is","n_predict":20,"temperature":0}' 2>/dev/null)
END=$(date +%s%N)
ELAPSED_MS=$(( (END - START) / 1000000 ))
ELAPSED_S=$(( ELAPSED_MS / 1000 ))

echo "Tempo: ${ELAPSED_MS}ms (${ELAPSED_S}s)"
echo "Resposta crua: $(echo "$RESULT" | head -c 200)"
echo ""
echo "=== TIMINGS ==="
echo "$RESULT" | python3 -c "
import sys,json
d=json.load(sys.stdin)
t=d.get('timings',{})
print(f'  prompt_ms: {t.get(\"prompt_ms\",\"?\")}')
print(f'  predicted_ms: {t.get(\"predicted_ms\",\"?\")}')
print(f'  predicted_per_second: {t.get(\"predicted_per_second\",\"?\")}')
print(f'  tokens_per_second: {t.get(\"tokens_per_second\",\"?\")}')
" 2>/dev/null
echo ""
echo "=== SERVER LOG ==="
grep -E 'listen|timing|token|error|print_info' /tmp/mix_err.log | tail -10
