# CEO Node Contract

**Module:** `src/core/pipeline/nodes/agent.py` (ativo), `src/core/pipeline/prompts/builder.py`
**Classification:** pipeline

## Public API

| Function | Signature | Returns | Contract |
|----------|-----------|---------|----------|
| `node_agent` | `async (state: dict) -> dict` | `{"final": str, ...}` | Nó ativo do grafo v4. ReAct + CEO local via llama.cpp. |
| `build_ceo_prompt` | `(state: PipelineState, mandamentos: list \| None) -> str` | `str` | Monta prompt completo para o CEO. |
| `ceo_system_prompt` | `() -> str` | `str` | Retorna system prompt do modelo local. |
| `missing_ceo_text` | `(ticker="", route="general", local_ready=False) -> str` | `str` | Texto de erro quando CEO offline. |

### CEO output format (mandatory)

```
VERDICT: BUY / SELL / HOLD
CONFIDENCE: 0-100%
TIMEFRAME: <user's horizon>
ENTRY: <current price>
TARGET: <expected price at end of timeframe>
MOVEMENT: <expected % gain or drop>
STOP LOSS: <suggested stop level>
```

### Module coverage

CEO deve referenciar explicitamente cada módulo disponível:
- DATA, PENNYLAB, EXPERTS, NEURAL_DECISION, RAG_FORENSICS, F51_VERDICT

## Invariants

1. CEO sempre responde em inglês (enforced via prompt + _strip_thinking).
2. Modelo usado: Qwen3-Next-80B-A3B Abliterated IQ4_XS GGUF (F51 Nitro MoE), servidor em `http://127.0.0.1:8082/v1`.
3. MoE: 512 experts, 10 ativos + 1 compartilhado por token. Temperatura: 0.3, max_tokens: 16384, timeout: 300s. Contexto: 256K tokens.
4. `_strip_thinking` remove blocos `<think>...</think>` do output.
5. Se rota = "general" sem dados financeiros, usa persona casual (não formato de análise).
6. Horizon constraint: TIMEFRAME deve corresponder ao time_horizon do state.

## Dependencies

- `src/core/pipeline/prompts/builder.py` — build_ceo_prompt
- `src/core/pipeline/prompts/_prompts.py` — QWEN_SYSTEM_PROMPT, QWEN_PERSONA, MODEL_PROMPTS
- servidor llama.cpp externo em `:8082`
- Não depende de rede externa (modelo local)
