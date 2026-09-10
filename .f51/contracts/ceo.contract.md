# CEO Node Contract

**Module:** `src/core/pipeline/nodes/agent.py` (ativo), `src/core/pipeline/prompts/builder.py`
**Classification:** pipeline

## Public API

| Function | Signature | Returns | Contract |
|----------|-----------|---------|----------|
| `node_agent` | `async (state: dict) -> dict` | `{"final": str, ...}` | NÃ³ ativo do grafo v4. ReAct + CEO no tier DeepSeek em nuvem. |
| `build_ceo_prompt` | `(state: PipelineState, mandamentos: list \| None) -> str` | `str` | Monta prompt completo para o CEO. |
| `ceo_system_prompt` | `() -> str` | `str` | Retorna system prompt do CEO (`deepseek-v4-flash`). |
| `missing_ceo_text` | `(ticker="", route="general", local_ready=False) -> str` | `str` | Texto de erro quando o provider do CEO nao esta pronto (fail-closed). |

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
2. Modelo canonico: `deepseek-v4-flash` na API HTTPS oficial `https://api.deepseek.com` (backend `openai_compatible`, chave em `SUPEREZIO_DEEPSEEK_API_KEY`), o mesmo tier de todos os papeis. Nao existe modelo local no caminho de resposta.
3. Temperatura: 0.3, max_tokens: 1800 e timeout: 180s (`config/runtime.yml`, secao `models.agent`). O limite de saida mantem a geracao no orcamento do gateway.
4. O prompt final e limitado a 24.000 caracteres (`LOCAL_AGENT_INPUT_CHAR_BUDGET`), com relatorio/observacoes truncados antes dos contratos binding, para reservar a janela da resposta no orcamento de saida.
4. `_strip_thinking` remove blocos `<think>...</think>` do output.
5. Se rota = "general" sem dados financeiros, usa persona casual (nÃ£o formato de anÃ¡lise).
6. Horizon constraint: TIMEFRAME deve corresponder ao time_horizon do state.

## Dependencies

- `src/core/pipeline/prompts/builder.py` â€” build_ceo_prompt
- `src/core/pipeline/prompts/_prompts.py` â€” QWEN_SYSTEM_PROMPT, QWEN_PERSONA, MODEL_PROMPTS
- depende de rede externa: nao existe servidor de modelo local no runtime
