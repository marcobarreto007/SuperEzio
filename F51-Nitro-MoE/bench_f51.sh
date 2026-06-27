#!/bin/bash
# F51 Benchmark — Layer 2 ON vs OFF
HOST="http://localhost:8080"

echo "============================================"
echo "  F51 Nitro-MoE Benchmark"
echo "============================================"

# Aguardar server estar pronto
echo "Aguardando servidor..."
for i in $(seq 1 30); do
    if curl -s "$HOST/health" > /dev/null 2>&1; then
        echo "Servidor online!"
        break
    fi
    sleep 2
done

echo ""
echo "=== WARMUP ==="
for i in 1 2 3; do
    echo "Warmup $i..."
    RESULT=$(curl -s "$HOST/completion" \
        -H "Content-Type: application/json" \
        -d '{"prompt": "The capital of France is", "n_predict": 50, "temperature": 0}' 2>/dev/null)
    TOK_S=$(echo "$RESULT" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('timings',{}).get('predicted_per_second','N/A'))" 2>/dev/null)
    echo "  -> $TOK_S tok/s"
    sleep 1
done

echo ""
echo "=== BENCHMARK: The theory of relativity ==="
RESULT=$(curl -s "$HOST/completion" \
    -H "Content-Type: application/json" \
    -d '{"prompt": "Explain the theory of relativity in simple terms.", "n_predict": 100, "temperature": 0}' 2>/dev/null)

echo "Resultado:"
echo "$RESULT" | python3 -c "
import sys, json
d = json.load(sys.stdin)
t = d.get('timings', {})
print(f'  prompt_tokens:     {t.get(\"prompt_n\", \"N/A\")}')
print(f'  predicted_tokens:  {t.get(\"predicted_n\", \"N/A\")}')
print(f'  prompt_ms:         {t.get(\"prompt_ms\", \"N/A\")}')
print(f'  predicted_ms:      {t.get(\"predicted_ms\", \"N/A\")}')
print(f'  predicted_per_second: {t.get(\"predicted_per_second\", \"N/A\")}')
print(f'  tokens_per_second: {t.get(\"tokens_per_second\", \"N/A\")}')
" 2>/dev/null

echo ""
echo "=== DONE ==="
