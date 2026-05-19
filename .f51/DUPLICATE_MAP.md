# Duplicate Map — SuperEzio

> Atualizado: 2026-05-19 | Branch: main | Session: f51-inventory-full-scan

---

## Duplicatas Resolvidas (2026-05-17)

### D1 — VeracityGate core/investor → REMOVIDO
```
src/f51/gates.py                              ← CANÔNICO (mantido)
src/core/investor/veracity_gate.py             ← REMOVIDO (nenhum import)
src/experts/pennylab/experts/veracity_gate.py  ← PennylabVeracityGate (classe DIFERENTE)
```
- **Resolução:** `core/investor/veracity_gate.py` deletado.
- **PennylabVeracityGate mantido** — propósito diferente, nome diferente.

### D2 — gemma.py shim → REMOVIDO
```
src/core/pipeline/prompts/_prompts.py   ← NOVO (constantes Qwen3.6)
src/core/pipeline/prompts/gemma.py      ← REMOVIDO (shim GEMMA=QWEN)
```

---

## Duplicatas Ativas em src/ — HIGH PRIORITY

### D3 — GatewayConfig definido 2x com campos diferentes

| Local | Tipo | Campos |
|-------|------|--------|
| `src/core/config/schema.py:44` | Pydantic | max_attempts, timeout_s, retry_delay_s |
| `src/core/model_serving/providers.py:41` | Dataclass | max_fallbacks, timeout_s, retry_attempts, retry_delay_s, quality_threshold |

**Risco:** Nomenclatura idêntica, comportamento divergente. Se módulo errado importar, configuração incorreta é aplicada.

### D4 — `_now_iso()` copiado 4x

| Local |
|-------|
| `src/core/data_collector/collector.py:110` |
| `src/core/data_collector/professional.py:79` |
| `src/core/investor/storage.py:34` |
| `src/core/observability/debug_logger.py:74` |

**Ação:** Extrair para `src/core/paths/time_utils.py` ou similar.

### D5 — Indicadores técnicos duplicados (RSI, EMA, MACD, Bollinger)

| Função | Local 1 | Local 2 |
|--------|---------|---------|
| `_compute_rsi()` | `src/core/data_collector/professional.py:1028` | `src/core/math/financial_engine.py:124` |
| `_compute_ema()` | `src/core/data_collector/professional.py:1046` | `src/core/math/financial_engine.py:142` |
| `_compute_macd()` | `src/core/data_collector/professional.py:1056` | `src/core/math/financial_engine.py:152` |
| `_compute_bollinger()` | `src/core/data_collector/professional.py:1068` | `src/core/math/financial_engine.py:161` |

**Canônico:** `src/core/math/financial_engine.py`. Professional.py deveria importar de lá.

### D6 — `clamp()` com assinaturas diferentes (4 cópias)

| Local | Assinatura |
|-------|------------|
| `src/core/math/utils.py:21` | `clamp(x, lo=0.0, hi=1.0)` |
| `src/experts/crisis/logic/normalization.py:11` | `clamp(value, min_value=0.0, max_value=100.0)` |
| `src/core/risk_firewall/experience_memory.py:22` | `_clamp(value, lo=0.0, hi=1.0)` |
| `src/core/risk_firewall/sdca_lite.py:23` | `_clamp(value, lo=0.0, hi=1.0)` |

**Canônico:** `src/core/math/utils.py`.

### D7 — `_safe_float` / `_safe_int` duplicados

| Função | Local 1 | Local 2 |
|--------|---------|---------|
| `_safe_float()` | `src/core/f51_adapter/adapter.py:42` | `src/experts/pennylab/data_provider.py:26` |
| `_safe_int()` | `src/core/f51_adapter/adapter.py:51` | `src/experts/pennylab/data_provider.py:35` |

### D8 — `_sentiment()` duplicado

| Local |
|-------|
| `src/data/newsapi_provider.py:111` |
| `src/data/news_feed.py:113` |

### D9 — `_log_event()` duplicado

| Local |
|-------|
| `src/data/alpha_vantage.py:6` |
| `src/data/twelve_data.py:6` |

---

## Duplicatas em Arquivos (nomes idênticos, propósitos diferentes)

| Filename | Local 1 | Local 2 | Risco |
|----------|---------|---------|-------|
| `collector.py` | `src/core/data_collector/` | `src/core/pipeline/nodes/` | LOW — propósito diferente |
| `engine.py` | `src/core/explanation/` | `src/core/rag/` | LOW — domínios diferentes |
| `graph.py` | `src/core/pipeline/` | `src/f51/` | LOW — abstrações diferentes |
| `pipeline_hook.py` | `src/experts/pennylab/` | `src/experts/technical_neural/` | LOW — hooks específicos |
| `protocol.py` | `src/agent_server/` | `src/core/ports/` | LOW — camadas diferentes |
| `schemas.py` | `src/experts/crisis/contracts/` | `src/experts/pennylab/` | LOW — schemas de domínio |
| `scoring.py` | `src/experts/crisis/logic/` | `src/f51/` | LOW — scoring diferente |

---

## Duplicatas em Scripts de Treinamento

4 scripts de fine-tuning compartilham boilerplate:

| Função/Classe | Arquivos |
|---------------|----------|
| `StreamingJSONLDataset` | `finetune_gemma_sft.py`, `finetune_qwen36_sft.py`, `train_qwen36_3h.py`, `finetune_glm_sft.py` |
| `TrainingArgs` | `finetune_gemma_sft.py`, `finetune_qwen36_sft.py` |
| `count_trainable_params` | `finetune_gemma_sft.py`, `finetune_qwen36_sft.py`, `train_qwen36_3h.py` |
| `collate_pad` | `finetune_gemma_sft.py`, `finetune_qwen36_sft.py`, `train_qwen36_3h.py` |
| `parse_args` | `finetune_gemma_sft.py`, `finetune_qwen36_sft.py`, `train_qwen36_3h.py` |

**Ação:** Extrair comum para `scripts/_finetune_common.py`. Prioridade baixa.

---

## Duplicatas em F51_Datasets

`grok_transfusion.py` e `grok_transfusion_python.py` são near-duplicates:

| Função | Arquivo 1 | Arquivo 2 |
|--------|-----------|-----------|
| `generate_system_prompt` | `grok_transfusion.py:79` | `grok_transfusion_python.py:288` |
| `generate_user_prompt` | `grok_transfusion.py:97` | `grok_transfusion_python.py:310` |
| `gen_meta_prompt` | `grok_transfusion.py:197` | `grok_transfusion_python.py:327` |
| `build_entry` | `grok_transfusion.py:317` | `grok_transfusion_python.py:438` |
| `quality_check` | `grok_transfusion.py:339` | `grok_transfusion_python.py:461` |
| `save_checkpoint` | `grok_transfusion.py:469` | `grok_transfusion_python.py:568` |

**Ação:** Consolidar com parâmetro de domínio. Prioridade baixa.

---

## Arquivados (seguro, sem ação)

| Item | Local | Status |
|------|-------|--------|
| SpiderSense shim | `archive/deprecated/core/math/detectors.py` | Re-export de `f51.detectors` |
| EpisodeMemory | `archive/quarantine/f51/memory.py` | Arquivado |
| MathCore base | `archive/deprecated/core/mathcore/base.py` (338 linhas) | Cópia morta de `core/math/*` |
| Shims (4) | `archive/deprecated/core/math/{gates,scoring,detectors,f51_formulas}.py` | Re-exports |
| MarketScanner antigo | `archive/quarantine/core/scanner/` | Arquivado |
| RL PolicyLearner | `archive/quarantine/core/rl/policy.py` vs `rl/rl/policy.py` | Full vs stub |
| Near-duplicate scripts | `archive/experimental/training/{hf_glm,hf_glm2,reddit_deep,reddit_deep2}.py` | Pares |

---

## Sumário

| Severidade | Count | Itens |
|------------|-------|-------|
| HIGH | 2 | GatewayConfig 2x, indicadores técnicos 4 funções 2x |
| MEDIUM | 5 | `_now_iso` 4x, `clamp` 4x, `_safe_float/int` 2x, `_sentiment` 2x, `_log_event` 2x |
| LOW | 7 | Nomes de arquivo idênticos (propósitos diferentes) |
| INFO | 3 | Boilerplate em scripts de treino, Grok transfusion, arquivados |

**Estado:** Zero duplicatas de classe ativa. Duplicatas de função ativas identificadas e prontas para consolidação via `f51-refactor`.
