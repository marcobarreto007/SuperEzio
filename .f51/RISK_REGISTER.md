# F51 Risk Register — SuperEzio

> Atualizado: 2026-05-19 | Sessão: f51-inventory-full-scan | Branch: main

---

## Riscos Ativos

### R8 — proxy_reward ternário → FALSO POSITIVO (CLOSED)
- **O que:** Reportado que ternário engolia a fórmula inteira quando `has_ground_truth=False`.
- **Verificação:** O ternário `(0.2 * clamp(ground_truth_bonus) if has_ground_truth else 0.0)` só afeta o termo `ground_truth_bonus`. A fórmula base (consensus + critic + sanity - diversity) é sempre computada. **Comportamento correto.**
- **Resolução:** Falso positivo confirmado em auditoria 2026-05-19. Testes existentes validam o comportamento.

### R9 — GatewayConfig duplicado com campos idênticos (MEDIUM)
- **O que:** `GatewayConfig` definido em `src/core/config/schema.py:44` e `src/core/model_serving/providers.py:41`. Mesmo nome, mesmos 5 campos, mesmos defaults. `providers.py` version faz shadow via `src/core/__init__.py`.
- **Impacto:** Se campos divergirem no futuro, bugs silenciosos aparecem. `UniversalConfig.gateway` usa `schema.py`, `build_default_providers()` usa `providers.py`.
- **Mitigação:** Consolidar em uma única definição em `schema.py`, importar em `providers.py`.
- **Urgência:** Média — campos idênticos hoje, mas arquitetura frágil.

### R10 — Indicadores técnicos duplicados em data_collector/professional.py (MEDIUM)
- **O que:** `_compute_rsi`, `_compute_ema`, `_compute_macd`, `_compute_bollinger` duplicados entre `src/core/data_collector/professional.py` e `src/core/math/financial_engine.py`.
- **Impacto:** Bug fix em um não se propaga ao outro. Divergência silenciosa de cálculos financeiros.
- **Mitigação:** Professional.py deve importar de `core.math.financial_engine`.
- **Urgência:** Média — funcional mas frágil.

### R1 — Config Stale (HIGH → LOW)
- **O que:** `config/model_manifest.json` referencia Gemma-4-26B. `config/runtime.yml` não tem CEO local.
- **Impacto:** Gateway pode tentar inicializar com modelo errado se ler esses arquivos.
- **Mitigação:** Atualizar ambos para Qwen3.6-35B F51.
- **Urgência:** Baixa — o `.env` e o script `serve_ceo_llamacpp.ps1` são a fonte real. Configs parecem não ser lidos em runtime.

### R2 — VeracityGate Triplicado → PARCIALMENTE RESOLVIDO (MEDIUM)
- **O que:** Era 3 implementações. `core/investor/veracity_gate.py` REMOVIDO em 2026-05-17. Restam 2: `src/f51/gates.py` (canônico) e `src/experts/pennylab/experts/veracity_gate.py` (PennylabVeracityGate — propósito diferente).
- **Impacto:** Reduzido. PennylabVeracityGate não é duplicata — é classe diferente.
- **Mitigação:** Nenhuma adicional necessária.

### R3 — prompts/gemma.py shim → RESOLVIDO (CLOSED)
- **O que:** `src/core/pipeline/prompts/gemma.py` definia `GEMMA_SYSTEM_PROMPT = QWEN_SYSTEM_PROMPT`.
- **Resolução:** Removido em 2026-05-17. Constantes migradas para `_prompts.py`.

### R4 — core/trading/ Desconectado (MEDIUM)
- **O que:** `src/core/trading/` (10 módulos: broker, kill_switch, order_builder, RL...) não está integrado ao pipeline principal.
- **Impacto:** Código mantido mas não exercitado. Pode apodrecer.
- **Mitigação:** Conectar ao pipeline ou arquivar como experimental.
- **Nota:** 5 arquivos de teste (~113 testes) cobrem o módulo. Código é testado mas experimental.

### R5 — technical_neural Desconectado (LOW)
- **O que:** `src/experts/technical_neural/` (torch_mlp.py, neural_expert.py) não integrado ao pipeline.
- **Impacto:** Código morto funcional.
- **Mitigação:** Integrar ao pipeline ou arquivar.

### R6 — Archive com Código Vivo (LOW)
- **O que:** `archive/deprecated/` e `archive/quarantine/` contêm SpiderSense e EpisodeMemory antigos.
- **Impacto:** Nenhum — não são importados.
- **Mitigação:** Nenhuma necessária.

### R7 — .env com API Keys no Disco (HIGH)
- **O que:** `.env` contém 12+ API keys em plaintext.
- **Impacto:** Se o arquivo vazar (git, backup, screen share), todas as keys são comprometidas.
- **Mitigação:** `.env` está no `.gitignore`. `.env.example` não tem secrets.

### R11 — `_now_iso()` copiado em 4 módulos (LOW)
- **O que:** Função `_now_iso()` duplicada em collector, professional, storage, debug_logger.
- **Impacto:** Baixo risco funcional, mas manutenção dispersa.
- **Mitigação:** Extrair para utilitário compartilhado.

### R12 — 5 módulos sem testes (MEDIUM)
- **O que:** `core/investor/`, `core/config/`, `core/observability/`, `core/security/`, `experts/technical_neural/` sem cobertura de teste.
- **Impacto:** Regressões podem passar despercebidas.
- **Mitigação:** Priorizar `config/` (impacto em runtime) e `security/`.

---

## Riscos Mitigados

- ~~Branch paralela `f51/reclamation-runtime`~~ — Deletada 2026-05-17.
- ~~Modelos velhos (Gemma 31B, Qwen3.6-27B)~~ — Movidos para `Desktop/modelos antigos/`.
- ~~GGUF sem MTP~~ — SHA256 confirmado: GGUF novo com tensores MTP.
- ~~R3 — gemma.py shim~~ — Removido em 2026-05-17.
- ~~R2 — VeracityGate triplicado~~ — Parcialmente resolvido: core/investor versão removida.

---

## Sumário

| ID | Descrição | Severidade | Status |
|----|-----------|------------|--------|
| R8 | proxy_reward ternário | — | FALSO POSITIVO (closed) |
| R9 | GatewayConfig duplicado | MEDIUM | Aberto |
| R10 | Indicadores técnicos duplicados | MEDIUM | Aberto |
| R1 | Config stale | LOW | Aberto |
| R2 | VeracityGate | LOW | Parcialmente resolvido |
| R4 | core/trading/ desconectado | MEDIUM | Aberto |
| R5 | technical_neural desconectado | LOW | Aberto |
| R6 | Archive com código vivo | LOW | Seguro |
| R7 | .env com API keys | HIGH | Mitigado (gitignored) |
| R11 | `_now_iso()` 4x | LOW | Aberto |
| R12 | 5 módulos sem testes | MEDIUM | Aberto |

**Total:** 10 riscos ativos (1 HIGH, 4 MEDIUM, 5 LOW)
