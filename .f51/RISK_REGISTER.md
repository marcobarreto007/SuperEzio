# F51 Risk Register — SuperEzio

> Atualizado: 2026-05-20 | Commit: `02a64ca` | 653/653 testes passam

---

## Severidade

| Nível | Critério |
|-------|----------|
| **CRITICAL** | Bloqueia produção ou corrompe dados |
| **HIGH** | Degradação significativa com workaround possível |
| **MEDIUM** | Risco latente sem sintoma atual |
| **LOW** | Dívida técnica, sem impacto operacional imediato |

---

## Riscos Ativos

### R1 — CEO GGUF precisa de patches binários manuais [HIGH]

**O que**: O `convert_hf_to_gguf.py` escreve `block_count=41` esperando tensores MTP (blk.40), mas o modelo merged tem 40 blocos (0-39). Dois patches binários manuais: offset 346 (`block_count` 41→40) e offset 1328 (`nextn_predict_layers` 1→0).

**Impacto**: Se re-quantizar o modelo, os patches precisam ser re-aplicados ou o llama-server não carrega.

**Mitigação**: Documentado em `.f51/checkpoints/latest.json`. Script `scripts/convert_gguf.sh` inclui os patches. PR #22673 no llama.cpp corrige a extração MTP — quando mergeado, elimina os patches.

---

### R2 — MTP speculative decoding ausente [MEDIUM]

**O que**: Qwen3.6 tem MTP nativo (1 camada, 19 tensores). Os tensores MTP foram perdidos na conversão. `nextn_predict_layers=0` desabilita speculative decoding.

**Impacto**: Perda de ~70% speedup. CEO responde em ~5-50s vs ~2-15s com MTP.

**Mitigação**: PR #22673 no llama.cpp corrige extração MTP. Re-quantizar quando disponível.

---

### R3 — Gated Delta Net fusion sem suporte CUDA [MEDIUM]

**O que**: Layer 0 do Qwen3.6-35B-A3B usa Gated Delta Net (SSD). llama.cpp não suporta aceleração CUDA para essa layer — cai para CPU.

**Impacto**: Mínimo com config atual (28/40 GPU layers). Layer 0 já ficaria na CPU.

**Mitigação**: Monitorar futuras versões do llama.cpp para suporte CUDA a GatedDeltaNet.

---

### R4 — `experts/technical_neural/expert/` sem `__init__.py` [MEDIUM]

**O que**: Diretório contém `neural_expert.py` (125 linhas) e `torch_mlp.py` (174 linhas) mas NÃO tem `__init__.py`. Subpacote não pode ser importado como módulo Python.

**Impacto**: `from experts.technical_neural.expert import ...` falha com `ModuleNotFoundError`.

**Mitigação**: Criar `__init__.py` no diretório.

---

### R5 — GatewayConfig definido 2x com campos divergentes [MEDIUM]

**O que**: `GatewayConfig` em `src/core/config/schema.py` (Pydantic: max_attempts, timeout_s, retry_delay_s) e `src/core/model_serving/providers.py` (Dataclass: max_fallbacks, timeout_s, retry_attempts, retry_delay_s, quality_threshold). `providers.py` importa de `schema.py`, mas o dataclass sombreia com campos diferentes.

**Impacto**: Se campos divergirem mais no futuro, bugs silenciosos. Hoje `UniversalConfig.gateway` usa `schema.py`, `build_default_providers()` usa `providers.py`.

**Mitigação**: Consolidar em `schema.py`, importar em `providers.py`.

---

### R6 — Indicadores técnicos duplicados (RSI, EMA, MACD, Bollinger) [MEDIUM]

**O que**: `_compute_rsi`, `_compute_ema`, `_compute_macd`, `_compute_bollinger` duplicados entre `src/core/data_collector/professional.py` e `src/core/math/financial_engine.py`.

**Impacto**: Bug fix em um não propaga ao outro. Divergência silenciosa de cálculos financeiros.

**Mitigação**: Professional.py deve importar de `core.math.financial_engine`.

---

### R7 — `.env` com 12+ API keys em plaintext no disco [HIGH]

**O que**: `.env` contém API keys da DeepSeek, Alpha Vantage, Twelve Data, Wolfram, NewsAPI, HuggingFace, OpenAI, CoinGecko, Market Data, Odds API em texto puro.

**Impacto**: Se o arquivo vazar (git, backup, screen share), todas as keys são comprometidas.

**Mitigação**: `.env` está no `.gitignore`. `.env.example` não tem secrets. GitHub bloqueado (DISK ONLY).

---

### R8 — Cache do ProfessionalCollector cresce sem limite [LOW]

**O que**: `.f51/cache/collector/` tem 90+ arquivos JSON de cache TTL sem política de evicção automática.

**Impacto**: Disco pode encher se não for limpo periodicamente.

**Mitigação**: Limpeza manual ou TTL cleanup no ProfessionalCollector.

---

### R9 — Sem backup off-disk do modelo merged [LOW]

**O que**: Modelo de 19.71 GB, checkpoints de treinamento, e código fonte existem apenas no disco local. GitHub bloqueado.

**Impacto**: Falha de disco = perda total do modelo merged.

**Mitigação**: Backup local em `SuperEzio_LOCAL_BACKUPS/`. Sem backup externo ou cloud.

---

### R10 — `_now_iso()` copiado em 4 módulos [LOW]

**O que**: Função `_now_iso()` duplicada em `collector.py`, `professional.py`, `storage.py`, `debug_logger.py`.

**Impacto**: Baixo risco funcional, manutenção dispersa.

**Mitigação**: Extrair para utilitário compartilhado.

---

### R11 — 5 módulos sem cobertura de teste [MEDIUM]

**O que**: `core/investor/`, `core/config/`, `core/observability/`, `core/security/`, `experts/technical_neural/` sem testes dedicados.

**Impacto**: Regressões podem passar despercebidas.

**Mitigação**: Priorizar `config/` (impacto em runtime) e `security/`.

---

### R12 — `core/trading/` desconectado do pipeline [MEDIUM]

**O que**: 10 módulos (broker, kill_switch, order_builder, RL...) não integrados ao pipeline principal. 132 testes cobrem o módulo mas ele não é exercitado em produção.

**Impacto**: Código mantido mas não usado. Pode apodrecer.

**Mitigação**: Integração planejada para Money Gate F4.

---

### R13 — `clamp()` com 4 assinaturas diferentes [LOW]

**O que**: `clamp` definida em `core/math/utils.py`, `crisis/logic/normalization.py`, `risk_firewall/experience_memory.py`, `risk_firewall/sdca_lite.py` com nomes de parâmetros diferentes.

**Impacto**: Confusão de API, inconsistência de parâmetros.

**Mitigação**: Todos deveriam importar de `core.math.utils`.

---

## Riscos Mitigados

| ID | Descrição | Data |
|----|-----------|------|
| R0-orphan-scripts | Scripts órfãos (`financial_quality_benchmark.py`, `gate1_download_test.sh`) | 2026-05-19 |
| R0-env-vars | 6 env vars órfãs + vars ausentes no `.env.example` | 2026-05-19 |
| R0-model-refs | 22+ referências ao modelo antigo `qwen36-35b-f51` | 2026-05-20 |
| R0-orchestrator-cloud | Orquestrador ia pra DeepSeek cloud, não pro modelo local | 2026-05-20 |
| R0-dead-imports | EpisodeMemory importado de módulo inexistente | 2026-05-19 |
| R0-agent-runtime | QuantEngine via stub de módulo inexistente | 2026-05-19 |
| R0-checkpoints | 12 checkpoints intermediários (~2.3 GB) | 2026-05-19 |
| R0-legacy-func | `_legacy_detect_market_scan_intent()` morta (20 linhas) | 2026-05-19 |
| R0-traceback | `traceback.print_exc()` trocado por `_log_event` | 2026-05-19 |
| R3-gemma-shim | `prompts/gemma.py` shim removido | 2026-05-17 |
| R2-veracity | VeracityGate triplicado → resolvido (core/investor removido) | 2026-05-17 |
| R8-proxy-reward | Falso positivo confirmado em auditoria | 2026-05-19 |

---

## Sumário

| ID | Descrição | Severidade | Status |
|----|-----------|------------|--------|
| R1 | CEO GGUF patches binários | HIGH | Aberto |
| R7 | .env com API keys | HIGH | Mitigado (gitignored) |
| R2 | MTP speculative decoding ausente | MEDIUM | Aberto |
| R3 | Gated Delta Net sem CUDA | MEDIUM | Aberto |
| R4 | technical_neural/expert sem __init__ | MEDIUM | Aberto |
| R5 | GatewayConfig 2x | MEDIUM | Aberto |
| R6 | Indicadores técnicos duplicados | MEDIUM | Aberto |
| R11 | 5 módulos sem testes | MEDIUM | Aberto |
| R12 | core/trading/ desconectado | MEDIUM | Aberto |
| R8 | Cache collector sem limite | LOW | Aberto |
| R9 | Sem backup off-disk | LOW | Aberto |
| R10 | `_now_iso()` 4x | LOW | Aberto |
| R13 | `clamp()` 4 assinaturas | LOW | Aberto |

**Total**: 13 riscos ativos (2 HIGH, 7 MEDIUM, 4 LOW)
