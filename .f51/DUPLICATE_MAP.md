# Duplicate Map — SuperEzio

> Atualizado: 2026-05-20 | Commit: `02a64ca`

---

## Duplicatas Resolvidas

### D1 — VeracityGate triplicado → RESOLVIDO
- `src/f51/gates.py` — CANÔNICO (mantido)
- `src/core/investor/veracity_gate.py` — REMOVIDO (2026-05-17)
- `src/experts/pennylab/experts/veracity_gate.py` — PennylabVeracityGate (classe DIFERENTE, mantida)

### D2 — gemma.py shim → RESOLVIDO
- `src/core/pipeline/prompts/_prompts.py` — CANÔNICO (mantido)
- `src/core/pipeline/prompts/gemma.py` — REMOVIDO (2026-05-17)

---

## Duplicatas Ativas — HIGH

### D3 — GatewayConfig definido 2x com campos divergentes

| Local | Tipo | Campos |
|-------|------|--------|
| `src/core/config/schema.py` | Pydantic BaseModel | max_attempts, timeout_s, retry_delay_s |
| `src/core/model_serving/providers.py` | `@dataclass` (importada de schema.py) | max_fallbacks, timeout_s, retry_attempts, retry_delay_s, quality_threshold |

**Nota**: `providers.py` já importa `GatewayConfig` de `config.schema`. O risco é moderado — o import unifica, mas `build_default_providers()` instancia diretamente com campos que podem divergir do BaseModel.

### D4 — Indicadores técnicos duplicados (4 funções, 2 locais)

| Função | Local 1 (canônico) | Local 2 (duplicata) |
|--------|---------------------|----------------------|
| `_compute_rsi()` | `core/math/financial_engine.py` | `core/data_collector/professional.py` |
| `_compute_ema()` | `core/math/financial_engine.py` | `core/data_collector/professional.py` |
| `_compute_macd()` | `core/math/financial_engine.py` | `core/data_collector/professional.py` |
| `_compute_bollinger()` | `core/math/financial_engine.py` | `core/data_collector/professional.py` |

**Ação**: Professional.py deve importar de `core.math.financial_engine`.

---

## Duplicatas Ativas — MEDIUM

### D5 — `_now_iso()` copiado 4x

| Local |
|-------|
| `src/core/data_collector/collector.py` |
| `src/core/data_collector/professional.py` |
| `src/core/investor/storage.py` |
| `src/core/observability/debug_logger.py` |

**Ação**: Extrair para utilitário compartilhado (`core/paths/time_utils.py`).

### D6 — `clamp()` com assinaturas diferentes (4 cópias)

| Local | Assinatura |
|-------|------------|
| `src/core/math/utils.py` | `clamp(x, lo=0.0, hi=1.0)` — CANÔNICO |
| `src/experts/crisis/logic/normalization.py` | `clamp(value, min_value=0.0, max_value=100.0)` |
| `src/core/risk_firewall/experience_memory.py` | `_clamp(value, lo=0.0, hi=1.0)` |
| `src/core/risk_firewall/sdca_lite.py` | `_clamp(value, lo=0.0, hi=1.0)` |

**Ação**: Todos devem importar de `core.math.utils`.

### D7 — `_safe_float` / `_safe_int` duplicados

| Função | Local 1 | Local 2 |
|--------|---------|---------|
| `_safe_float()` | `src/core/f51_adapter/adapter.py` | `src/experts/pennylab/data_provider.py` |
| `_safe_int()` | `src/core/f51_adapter/adapter.py` | `src/experts/pennylab/data_provider.py` |

### D8 — `_sentiment()` duplicado

| Local |
|-------|
| `src/data/newsapi_provider.py` |
| `src/data/news_feed.py` |

### D9 — `_log_event()` duplicado em data providers

| Local |
|-------|
| `src/data/alpha_vantage.py` |
| `src/data/twelve_data.py` |

**Nota**: Ambos importam lazy de `core.observability.neural_log`. O `_log_event` local é um wrapper que logging.warning no fallback. Padrão questionável — deveriam usar `core.observability.neural_log.log_event` diretamente.

---

## Duplicatas em Arquivos (nomes idênticos, propósitos diferentes)

| Filename | Local 1 | Local 2 | Risco |
|----------|---------|---------|-------|
| `collector.py` | `src/core/data_collector/` | `src/core/pipeline/nodes/` | LOW — propósitos diferentes |
| `engine.py` | `src/core/explanation/` | `src/core/rag/` | LOW — domínios diferentes |
| `graph.py` | `src/core/pipeline/` | `src/f51/` | LOW — LangGraph vs F51 graph |
| `pipeline_hook.py` | `src/experts/pennylab/` | `src/experts/technical_neural/` | LOW — hooks específicos |
| `protocol.py` | `src/agent_server/` | `src/core/ports/` | LOW — implementação vs contrato |
| `schemas.py` | `src/experts/crisis/contracts/` | `src/experts/pennylab/` | LOW — domínios diferentes |
| `scoring.py` | `src/experts/crisis/logic/` | `src/f51/` | LOW — crise vs F51 scoring |

---

## Duplicatas em Scripts de Treinamento

4 scripts compartilham boilerplate de fine-tuning:

| Função/Classe | Arquivos |
|---------------|----------|
| `StreamingJSONLDataset` | `finetune_gemma_sft.py`, `finetune_qwen36_sft.py`, `train_qwen36_3h.py`, `finetune_glm_sft.py` |
| `TrainingArgs` | `finetune_gemma_sft.py`, `finetune_qwen36_sft.py` |
| `count_trainable_params` | `finetune_gemma_sft.py`, `finetune_qwen36_sft.py`, `train_qwen36_3h.py` |
| `collate_pad` | `finetune_gemma_sft.py`, `finetune_qwen36_sft.py`, `train_qwen36_3h.py` |
| `parse_args` | `finetune_gemma_sft.py`, `finetune_qwen36_sft.py`, `train_qwen36_3h.py` |

**Ação**: Extrair comum para `scripts/_finetune_common.py`. Prioridade baixa.

---

## Duplicatas em F51_Datasets

`grok_transfusion.py` e `grok_transfusion_python.py` são near-duplicates (6 funções com implementações quase idênticas, diferindo apenas no domínio dos dados).

**Ação**: Consolidar com parâmetro de domínio. Prioridade baixa.

---

## Arquivados (seguro, sem ação)

| Item | Local | Status |
|------|-------|--------|
| SpiderSense shim | `archive/deprecated/core/math/detectors.py` | Re-export de `f51.detectors` |
| EpisodeMemory antigo | `archive/quarantine/f51/memory.py` | Arquivado |
| MathCore base | `archive/deprecated/core/mathcore/base.py` (338 linhas) | Cópia morta |
| Shims (4) | `archive/deprecated/core/math/` | Re-exports |
| MarketScanner antigo | `archive/quarantine/core/scanner/` | Arquivado |
| RL PolicyLearner | `archive/quarantine/core/rl/` | Full vs stub |

---

## Sumário

| Severidade | Count | Itens |
|------------|-------|-------|
| HIGH | 2 | GatewayConfig 2x, indicadores técnicos 4 funções 2x |
| MEDIUM | 5 | `_now_iso` 4x, `clamp` 4x, `_safe_float/int` 2x, `_sentiment` 2x, `_log_event` 2x |
| LOW | 7 | Arquivos com mesmo nome em diretórios diferentes |
| INFO | 3 | Boilerplate scripts treino, Grok transfusion, archive |

**Status**: Zero duplicatas de classe. Duplicatas de função utilitária identificadas e documentadas.
