#!/bin/bash
echo "=== TESTE DE VELOCIDADE MIXTRAL ==="
START=$(date +%s%N)
RESULT=$(curl -s -m 120 http://localhost:8080/completion \
  -H "Content-Type: application/json" \
  -d '{"prompt":"The capital of France is","n_predict":20,"temperature":0}' 2>/dev/null)
END=$(date +%s%N)
ELAPSED_MS=$(( (END - START) / 1000000 ))
ELAPSED_S=$(( ELAPSED_MS / 1000 ))

echo "Tempo total: ${ELAPSED_MS}ms (${ELAPSED_S}s)"
echo ""
echo "=== RESPOSTA ==="
echo "$RESULT" | python3 -c "
import sys,json
d=json.load(sys.stdin)
t=d.get('timings',{})
c=d.get('content','')
print('Conteudo:', c[:300])
print()
print('prompt_ms:', t.get('prompt_ms'))
print('predicted_ms:', t.get('predicted_ms'))
print('predicted_n:', t.get('predicted_n'))
print('predicted_per_second:', t.get('predicted_per_second'))
"
