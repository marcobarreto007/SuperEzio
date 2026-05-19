# Arqueologista — Relatório de Escavação

> Data: 2026-05-19 | Branch: main | Session: arqueologista-full-scan

---

## Resumo

| Categoria | Count |
|-----------|-------|
| Módulos totalmente órfãos | 7 |
| Funções sem caller | 4 |
| Classes nunca instanciadas | 8 |
| Imports quebrados (guardados) | 2 |
| `__all__` exportando `None` | 2 |
| Env vars não documentadas | 12 |
| Env vars documentadas não usadas | 6 |
| Configs órfãs | 1 (model_manifest.json) |
| Scripts órfãos | 2 |
| Espaço recuperável | ~5.8 GB |
| Pastas vazias | 11 |

---

## CRÍTICO — Pode quebrar import/runtime

### C1 — `EpisodeMemory` e `Episode` exportados como `None`

```
src/f51/__init__.py:87-88
```

- `src/f51/memory.py` **não existe** (foi arquivado). O `try/except` seta `EpisodeMemory = None` e `Episode = None`.
- `__all__` ainda lista ambos. Qualquer `from f51 import EpisodeMemory` retorna `None`.
- **Risco:** `AttributeError` em runtime se alguém tentar usar.
- **Ação:** Remover de `__all__` e do try/except, ou recriar o módulo.

### C2 — Imports para pacote deletado `core.agent_runtime`

```
src/core/data_collector/collector.py:26 — from core.agent_runtime.ml.quant_engine import QuantEngine
src/core/data_collector/collector.py:74 — from core.agent_runtime.financial_suite.adapters import ...
```

- `core/agent_runtime/` **não existe**. Guardados por `try/except`, mas o código morto define stubs que nunca são exercitados.
- **Ação:** Remover os try/except blocks e os stubs.

### C3 — `model_manifest.json` órfão

- `config/model_manifest.json` — **ZERO referências em código.** Nenhum módulo lê este arquivo.
- Conteúdo stale (referencia Gemma-4-26B).
- **Ação:** Atualizar conteúdo E conectar ao código, ou deletar.

---

## MÉDIO — Código morto, entulho, desconectado

### M1 — `core/trading/` inteiro desconectado do pipeline

- 10 módulos, ~20 classes, **zero instanciação em produção**.
- Só `tests/test_trading_loop{1-5}.py` referencia.
- **Ação:** Integrar ao pipeline (Money Gate F4) ou mover para `archive/experimental/`.

### M2 — `core/investor/` parcialmente morto

- `InvestorCommittee`, `FraudPatternAnalyst`, `FraudManipulationMemory`, `InvestorStorage` — nunca instanciados.
- Só `CostGuard` é vivo (usado em `agent_server/main.py`).
- `core/investor/prompts.py` — 7 prompt templates sem consumidor externo.

### M3 — Módulos totalmente órfãos (zero callers)

| Módulo | Linhas | Define |
|--------|--------|--------|
| `core/audit/decision_logger.py` | ~150 | `DecisionLogger` — audit trail JSONL |
| `core/math/financial_engine.py` | ~170 | `FinancialEngine` — indicadores técnicos |
| `core/prompts/financial_prompts.py` | ~215 | 10+ system prompts para agentes financeiros |
| `core/pipeline/security.py` | ~353 | `SecurityContext`, rate limiting, PII filter, input validation |
| `core/data_collector/scraper.py` | ~50 | `ScraperAdapter` |
| `tools/custom_tools.py` | ~244 | Web search tool, code executor, calculator |
| `experts/crisis/adapters/tool_adapter.py` | ~30 | `tool_analyze_systemic_risk` |

**Destaque:** `core/pipeline/security.py` (353 linhas) é um módulo de segurança production-ready completamente inutilizado.

### M4 — Funções/classes mortas em módulos vivos

| Item | Local | Problema |
|------|-------|----------|
| `_legacy_detect_market_scan_intent()` | `core/pipeline/intents.py:999` | Legacy, nunca chamada |
| `reload_config()` | `core/config/schema.py:294` | Exportada, nunca chamada |
| `get_investor_storage()` | `core/investor/storage.py:275` | Nunca chamada fora do módulo |
| `get_fraud_memory()` | `core/investor/fraud_memory.py:154` | Nunca chamada fora do módulo |
| `RedisStreamsHub` | `core/observability/event_hub.py:140` | Nunca instanciada |
| `create_event_hub()`, `get_event_hub()`, `set_event_hub()` | `core/observability/event_hub.py` | Nunca chamadas |
| `SecurityContext` | `core/pipeline/security.py:258` | Nunca instanciada |
| `AlpacaPaperAdapter` | `core/trading/broker.py:73` | Nunca instanciada |
| `InvestorCommittee` | `core/investor/committee.py:71` | Nunca instanciada |

### M5 — Env vars lidas mas não documentadas

| Variável | Local |
|----------|-------|
| `ALPACA_API_KEY` | `core/trading/broker.py:86` |
| `ALPACA_SECRET_KEY` | `core/trading/broker.py:87` |
| `IBKR_HOST/PORT/CLIENT_ID` | `adapters/broker/ibkr_adapter.py` |
| `SMTP_HOST/USER/PASS/FROM/TO` | `core/trading/alerter.py` |
| `SUPEREZIO_DEEPSEEK_MAX_TOKENS` | `core/model_serving/providers.py:103` |
| `SUPEREZIO_RAG_INDEX_DIR` | `core/rag/engine.py:25` |

### M6 — Env vars documentadas mas não usadas

| Variável |
|----------|
| `EXPLANATION_MODEL_PATH` |
| `EXPLANATION_LORA_PATH` |
| `SUPEREZIO_EXPERT_CONCURRENCY` |
| `SUPEREZIO_FORCE_ALL_EXPERTS_ON_PARTIAL` |
| `SUPEREZIO_ORCHESTRATOR_TIMEOUT` |
| `UNIVERSAL_SKIP_GATEWAY` |

---

## LEVE — Limpeza fina, cosmético

### L1 — `traceback.print_exc()` em produção

```
src/core/scanner/__init__.py:91 — traceback.print_exc()
```

- Debug leftover. Deveria ser `logger.error(...)`.

### L2 — Scripts totalmente órfãos

| Script | Referências |
|--------|-------------|
| `scripts/gate1_download_test.sh` | Zero |
| `scripts/financial_quality_benchmark.py` | Zero |

### L3 — Espaço recuperável em output/

| Alvo | Tamanho | Ação |
|------|---------|------|
| `output/qwen36-sft/checkpoint-*` (13 intermediários) | ~2.5 GB | Deletar — `best/` e `final/` preservados |
| `data/fraud_datasets/` | ~3.3 GB | Avaliar — pode ser usado em treinamento futuro |

### L4 — Pastas vazias

- `.f51/tmp/causal-conv1d-src/.git/{objects/info,refs/heads,refs/tags}`
- `.f51/tmp/mamba-ssm-src/.git/{objects/info,refs/heads,refs/tags}`
- `.f51/tmp/causal-conv1d-src/build/bdist.win-amd64`
- `data/cache/quant`, `data/vectors`, `output/runtime`, `tmp/pdfs`

---

## Ação Recomendada (priorizada por impacto)

1. **Fix C1:** Remover `EpisodeMemory`/`Episode` de `__all__` em `src/f51/__init__.py`
2. **Fix C2:** Limpar try/except de `agent_runtime` em `collector.py`
3. **Fix M5:** Adicionar 12 env vars ao `.env.example`
4. **Decidir M1:** Integrar `core/trading/` ao pipeline ou arquivar
5. **Decidir M3:** Integrar `core/pipeline/security.py` (353 linhas de segurança pronta) ou arquivar
6. **Limpar L3:** Deletar checkpoints intermediários (~2.5 GB)
