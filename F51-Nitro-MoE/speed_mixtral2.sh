#!/bin/bash
pkill -9 llama-server.exe 2>/dev/null
sleep 1

cd /mnt/c/Users/marco/Desktop/F51-Nitro-MoE/F51_Nitro_20GB_DualGPU/bin_mixtral_legacy/

echo "=== Iniciando Mixtral Legacy (do diretorio) ==="
./llama-server.exe \
  -m "C:\\Users\\marco\\Desktop\\F51-Nitro-MoE\\F51_Nitro_20GB_DualGPU\\models\\Mixtral-8x7B-Instruct-v0.1-GGUF\\mixtral-8x7b-instruct-v0.1.Q4_K_M.gguf" \
  --port 8080 -ngl 18 -c 2048 -np 4 \
  > /tmp/mix_out.log 2> /tmp/mix_err.log &

echo "Aguardando 60s..."
sleep 60

# Check if alive
pgrep -a llama-server.exe > /dev/null 2>&1 && echo "SERVER VIVO!" || echo "SERVER MORTO!"

echo ""
echo "=== TESTE ==="
START=$(date +%s%N)
RESULT=$(curl -s -m 300 http://localhost:8080/completion \
  -H "Content-Type: application/json" \
  -d '{"prompt":"The capital of France is","n_predict":20,"temperature":0}' 2>/dev/null)
END=$(date +%s%N)
ELAPSED_MS=$(( (END - START) / 1000000 ))
ELAPSED_S=$(( ELAPSED_MS / 1000 ))

echo "Tempo: ${ELAPSED_MS}ms (${ELAPSED_S}s)"
CONTENT=$(echo "$RESULT" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('content','')[:300])" 2>/dev/null)
echo "Resposta: ${CONTENT:-vazia}"
echo ""
echo "=== TIMINGS ==="
echo "$RESULT" | python3 -c "
import sys,json
d=json.load(sys.stdin)
t=d.get('timings',{})
print(f'  prompt_ms: {t.get(\"prompt_ms\",\"?\")}')
print(f'  predicted_ms: {t.get(\"predicted_ms\",\"?\")}')
print(f'  predicted_per_second: {t.get(\"predicted_per_second\",\"?\")}')
" 2>/dev/null
echo ""
echo "=== ULTIMAS LINHAS DO LOG ==="
tail -10 /tmp/mix_err.log
