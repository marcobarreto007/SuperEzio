# DELIVERY CHECKLIST — SuperEzio v4.0.0
**Date:** 2026-05-17T16:30:00-04:00 | **Auditor:** F51 Hostile Auditor

---

## 🔴 Bloqueadores (CRITICAL — devem ser resolvidos antes de demo/venda)

- [ ] **C1 — proxy_reward bug**: `formulas.py:109-133` ternário engole fórmula. `ProxyReward.calculate()` retorna 0.0 sem ground truth. Afeta F51Engine, AdversarialCritic. **Fix: 1 linha — adicionar parênteses no ternário.**
- [ ] **C2 — Endpoints 500**: `/capabilities` e `/product/manifest` retornam Internal Server Error.
- [ ] **C3 — Demo latency**: CEO responde em 52s. Pipeline completo ~2min. Inviável para demo ao vivo. Opções: (a) pré-calcular respostas, (b) reduzir context length, (c) usar modelo menor para demo.

---

## 🟡 Pré-Demo (devem ser resolvidos antes de mostrar para alguém)

- [ ] **D1 — .env.example vs .env**: Clone fresco não tem `.env`. Demo tem que prover `.env.example` funcional ou script que gera `.env` mínimo.
- [ ] **D2 — NeuralDecisionExpert documentação vs realidade**: `NEURAL_EXPERT_ARCHITECTURE.md` promete LSTM treinado on-the-fly. Código real é rule-based com probabilidades hardcoded. Alinhar documento ou implementar ML real.
- [ ] **D3 — Launcher testado**: `desktop/SuperEzio.bat` não foi testado nesta auditoria (servidores iniciados manualmente). Testar duplo clique e confirmar que sobe em < 5 min.
- [ ] **D4 — DeepSeek API key**: Demo requer `DEEPSEEK_API_KEY` no `.env`. Sem ela, experts não respondem e pipeline fica incompleto.

---

## 🟢 Pré-Venda (antes de aceitar dinheiro)

- [ ] **V1 — GitHub remoto**: Repositório GitHub deletado. Criar novo remote ou backup alternativo.
- [ ] **V2 — CI funcional**: GitHub Actions quebrado (ddgs version, CI yaml). Reparar ou substituir.
- [ ] **V3 — API keys seguras**: `.env` com 12+ API keys em plaintext no disco. Sem criptografia. Aceitável para máquina local, mas documentar risco.
- [ ] **V4 — Startup automático**: Confirmar que `SuperEzio.bat` sobe CEO + API sem intervenção manual.
- [ ] **V5 — Testes completos passing**: `python -m pytest tests/ -q` com 0 falhas.

---

## ⚙️ Pós-Venda (manutenibilidade)

- [ ] Consolidar `os.getenv()` espalhados em 30+ arquivos em config central.
- [ ] Remover `load_dotenv()` de dentro de função em `pipeline_hook.py`.
- [ ] Atualizar `INVENTORY.json` (ainda referencia Gemma-4-26B).
- [ ] `test_rag_engine_smoke.py` — converter de script print para teste pytest real.
- [ ] `neural_log.py:31` — `warnings.filterwarnings("ignore", category=DeprecationWarning)` silencia warnings globalmente. Restringir escopo.
- [ ] Remover `.venv/.env` duplicado.

---

## 📊 Quality Gate Status (2026-05-17)

| Check | Status | Evidência |
|---|---|---|
| **ruff check** | ✅ PASS | Zero novos erros |
| **ruff format** | ✅ PASS | Formatação correta |
| **pytest contracts** | ✅ PASS | 158/158 |
| **pytest smoke** | ✅ PASS | 20/20 |
| **pytest integration** | 🟡 5/7 | 2 endpoints 500 |
| **pipeline live** | ✅ PASS | AAPL 14d → HOLD |
| **CEO live** | ✅ PASS | :8082/health OK |
| **API live** | ✅ PASS | :8002/health OK |
| **launcher .bat** | ❌ NÃO TESTADO | — |
| **GitHub Actions** | ❌ QUEBRADO | ddgs version, CI yaml |
