# FINAL AUDIT — SuperEzio v4.0.0
**Date:** 2026-05-17T16:30:00-04:00 | **Auditor:** F51 Hostile Auditor (Deep)
**Status:** **OPERACIONAL COM RESSALVAS** 🟡

---

## 1. METODOLOGIA

Auditoria hostil de produção e entrega comercial. Nove categorias inspecionadas com ferramentas automatizadas e verificação manual. Nenhuma suposição — só evidência de disco e runtime.

---

## 2. HALLAZGOS POR CATEGORIA

### 2.1 Arquivo Órfão

| Arquivo | Status | Risco |
|---------|--------|-------|
| `src/core/investor/veracity_gate.py` | **DELETADO** | ✅ Resolvido |
| `src/core/pipeline/prompts/gemma.py` | **DELETADO** | ✅ Resolvido |
| `src/experts/technical_neural/pipeline_hook.py` | Existe, importa `dotenv` dentro de função | 🟡 Side effect escondido |
| `src/core/prompts/` | Diretório com `financial_prompts.py` — é referenciado? | 🟡 Verificar se ainda é usado |

### 2.2 Mock em Caminho de Produção

| Local | Problema | Severidade |
|-------|---------|------------|
| `neural_decision_expert.py:198` | Comentário "# Mocking real distribution matching the regime..." — probabilidades são hardcoded (0.33/0.33/0.34 default), não ML real | **HIGH** |
| `neural_decision_expert.py:199-201` | `up_prob = 0.33; down_prob = 0.33; sideways_prob = 0.34` — fallback hardcoded, não inferido | **HIGH** |

**Veredito:** NeuralDecisionExpert é rule-based com probabilidades heurísticas, não ML treinado. O documento `NEURAL_EXPERT_ARCHITECTURE.md` promete LSTM/600 barras; a realidade é regime detection + hardcoded probabilities.

### 2.3 Contrato Frágil

| Contrato | Fragilidade | Severidade |
|----------|------------|------------|
| `proxy_reward()` em `formulas.py:109-133` | Ternário `X if has_ground_truth else 0.0` engole TODA a fórmula — retorna 0.0 sem ground truth | **CRITICAL** |
| `DataHub.collect_full_mesh` | Não existe no DataHub real — o método está documentado mas não implementado | MEDIUM |
| `NeuralDecisionExpert.predict()` | Contrato de API diferente do que os testes esperavam — 4 args, não 7 | MEDIUM |

### 2.4 Runtime Duplicado

| Item | Status |
|------|--------|
| `config/model_manifest.json` vs `config/runtime.yml` | Model manifest tem CEO Qwen3.6-35B (correto). Runtime.yml atualizado em 2026-05-17 (correto). |
| `desktop/SuperEzio.bat` vs manual startup | Launcher .bat é o canônico. Script `serve_ceo_llamacpp.ps1` está correto. |
| Múltiplos `os.getenv()` | 30+ arquivos chamam `os.getenv()` diretamente — **config espalhada** |

### 2.5 Config Espalhada

| Problema | Evidência |
|----------|-----------|
| 30+ arquivos com `os.getenv()` | Cada módulo lê seu próprio env var sem centralização |
| Nomenclatura mista | `A2A_PORT` (legacy), `SUPEREZIO_PORT` (atual) — ambos ativos |
| `.env` na raiz, `.venv/.env` também | Duplicação de .env |
| `load_dotenv()` dentro de função | `pipeline_hook.py:18` — carrega .env toda vez que a função é chamada |

### 2.6 Teste Fake

| Teste | Problema |
|-------|---------|
| `test_rag_engine_smoke.py` | É um script com `print()`, não um teste pytest — não asserta nada |
| `test_proxy_reward_calculate_with_critic` (original) | Esperava retorno > 0.5, mas o bug retorna 0.0 — teste ajustado para `has_ground_truth=True` como workaround |

**Veredito:** Nenhum teste deliberadamente fake encontrado. Mas `test_rag_engine_smoke.py` não é um teste real — é um script de print.

### 2.7 Dependência Escondida

| Dependência | Onde | Problema |
|------------|------|---------|
| `dotenv` | `pipeline_hook.py:17` | Import dentro de função — falha silenciosa se não instalado |
| `faiss` | `core/rag/engine.py` | Import condicional — fallback para keyword search |
| `sentence_transformers` | `core/rag/engine.py` | Import condicional |
| `ib_insync` | `adapters/broker/ibkr_adapter.py` | Import condicional — broker IBKR |
| `opentelemetry` | `core/observability/neural_log.py` | Import condicional — OTEL |
| `ddgs` | `data/news_feed.py` | `_DDGS = None` — import condicional |
| `llama-server.exe` | `scripts/serve_ceo_llamacpp.ps1` | Dependência externa não versionada — compilada de llama.cpp |
| `qwen36-35b-f51.Q4_K_M.gguf` | `models/` | 20.22GB — não versionado, essencial para funcionamento |

### 2.8 Documentação Insuficiente

| Documento | Status |
|-----------|--------|
| `docs/runbooks/RUNBOOK.md` | ✅ Atualizado 2026-05-17 |
| `docs/architecture/ARCHITECTURE_TEMPLATE.md` | 🟡 Template, não preenchido |
| `.f51/NEURAL_EXPERT_ARCHITECTURE.md` | ❌ Promete LSTM/600 barras — código real é rule-based |
| `docs/decision-tree.txt` | ✅ Existe |

### 2.9 Risco de Demo Quebrar

| Risco | Probabilidade | Impacto |
|-------|--------------|---------|
| CEO 52s latency — demo parece travada | **ALTA** | Usuário fecha o navegador |
| DeepSeek API falhar (quota, rede) — pipeline sem experts | MÉDIA | Verdict sem opinião de experts |
| Alpha Vantage circuit breaker aberto — dados incompletos | MÉDIA | Dados faltando, confiança reduzida |
| `/capabilities` e `/product/manifest` retornam 500 | **ALTA** | Demo de API quebrada se alguém clicar |
| `.env` não existe no clone fresco — servidor não sobe | **ALTA** | Demo falha na primeira tentativa |

---

## 3. EVIDÊNCIA DE RUNTIME

```
curl :8082/health → OK
curl :8002/health → OK (agent_server v3.0.0)
POST /task/submit AAPL 14d → pipeline completo (52s)
python -m pytest tests/ -q → 510 tests collected (nem todos executados nesta auditoria)
python -m pytest tests/test_runtime_smoke.py tests/contracts/ tests/test_integration_runtime.py -q → 183 passed, 2 skipped
```

---

## 4. SUMÁRIO DE SEVERIDADE

| Severidade | Contagem | Itens |
|-----------|---------|-------|
| CRITICAL | 1 | R8: proxy_reward formula bug |
| HIGH | 3 | NeuralDecisionExpert hardcoded, 2 endpoints 500, demo latency 52s |
| MEDIUM | 5 | Config espalhada, load_dotenv() escondido, test_rag_engine_smoke print-only, INVENTORY stale, DataHub.collect_full_mesh inexistente |
| LOW | 4 | __pycache__ em src/, .venv/.env duplicado, pipeline_hook órfão, nomenclatura env var mista |

---

## 5. VEREDITO FINAL

**O sistema funciona.** O pipeline executa ponta a ponta. O CEO responde. Os módulos produzem output.

**Mas não está pronto para demo pública nem venda.** Há 1 bug crítico (proxy_reward), 2 endpoints quebrados (500), e latência de 52s que torna a demo inviável. A documentação promete mais do que o código entrega (NeuralDecisionExpert "ML" vs rule-based).

Correções necessárias antes de demo/venda: ver Seção 6.
