# CEO Node Contract

**Module:** `src/core/pipeline/nodes/agent.py` (ativo), `src/core/pipeline/prompts/builder.py`
**Classification:** pipeline

## Public API

| Function | Signature | Returns | Contract |
|----------|-----------|---------|----------|
| `node_agent` | `async (state: dict) -> dict` | `{"final": str, ...}` | NÃ³ ativo do grafo v4. ReAct + CEO local via llama.cpp. |
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

CEO deve referenciar explicitamente cada mÃ³dulo disponÃ­vel:
- DATA, PENNYLAB, EXPERTS, NEURAL_DECISION, RAG_FORENSICS, F51_VERDICT

## Invariants

1. CEO responde no idioma do usuario; o gate V1 valida respostas em portugues quando o prompt esta em portugues.
2. Modelo canonico: `Qwen3.8-27B-Q4_K_M.gguf`, servido localmente em `http://127.0.0.1:8080/v1`.
3. Temperatura: 0.3, max_tokens: 8192, timeout: 300s e contexto efetivo: 8192 tokens.
4. `_strip_thinking` remove blocos `<think>...</think>` do output.
5. Se rota = "general" sem dados financeiros, usa persona casual (nÃ£o formato de anÃ¡lise).
6. Horizon constraint: TIMEFRAME deve corresponder ao time_horizon do state.

## Dependencies

- `src/core/pipeline/prompts/builder.py` â€” build_ceo_prompt
- `src/core/pipeline/prompts/_prompts.py` â€” QWEN_SYSTEM_PROMPT, QWEN_PERSONA, MODEL_PROMPTS
- servidor llama.cpp local em `:8080`
- NÃ£o depende de rede externa (modelo local)
