# FINAL AUDIT — SuperEzio v4.0.0
Date: 2026-05-15 | Auditor: F51 Hostile Audit | Commit: 260ba3c

## VEREDICTO: NAO APTO PARA DEMO COMERCIAL

---

## BLOQUEADORES (P0) — Impedem demonstração

### B01. Pipeline graph nao tem `shutdown()` — crash no stop do servidor
- **File:** `src/agent_server/main.py:116`
- **Detail:** `app.state.pipeline.shutdown()` chamado no lifespan shutdown, mas `build_graph()` retorna `CompiledStateGraph` que nao tem `.shutdown()`.
- **Impact:** Toda vez que o servidor para (Ctrl+C, redeploy), crasha com `AttributeError`.
- **Fix:** Adicionar try/except ou wrapper com `.shutdown()`.

### B02. `runtime.py` (900+ linhas) deletado sem migracao completa
- **File:** `src/core/pipeline/runtime.py` — REMOVIDO do disco e do git
- **Detail:** O commit `260ba3c` removeu `runtime.py` (UniversalPipeline, create_pipeline, chat, chat_sync, stream_events, data collection helpers, CEO provider selection, scan execution). A substituição (`graph.py`, 132 linhas) NAO implementa:
  - `chat()` / `chat_sync()` / `stream_events()` — API publica do pipeline
  - `_hybrid_intent_plan()` — intent classification com LLM fallback
  - `_run_scan()` — market scan
  - `_collect_all_hard_timeout()` — data collection com timeout
  - `_enrich_scan_candidates()` — price enrichment
  - Provider helpers (`_provider`, `_provider_ready`, `_init_gateway`, `_init_memory`)
  - Tool registration (`_register_hub_tools`)
  - `get_status()` — health endpoint
- **Impact:** Quem quer que use `UniversalPipeline.chat()` ou `stream_events()` (contract tests, future integrations) quebra.
- **Evidence:** `git ls-files src/core/pipeline/runtime.py` retorna vazio.

### B03. `_mixin.py` removido, nodes standalone sem DI completa
- **File:** `src/core/pipeline/nodes/_mixin.py` — REMOVIDO
- **Detail:** O mixin tinha acesso a `self.gateway`, `self.financial_agents`, `self.mandamentos`, `self.config`, `self._data_collector`, `self._audit`, etc. Os nodes standalone recebem `gateway` e `config` via kwargs do `graph.py`, mas NAO recebem:
  - `financial_agents` (fan-out de experts)
  - `mandamentos` (passado ao CEO mas nao ao orchestrator)
  - `_data_collector` / `_collect_professional` (collector node)
  - `_audit` (decision logging)
- **Impact:** Nodes parcialmente cegos a dependencias.

---

## CRITICAL (P1) — Degradação silenciosa

### C01. `f51/scoring.py:166` — exception engolida silenciosamente
- **File:** `src/f51/scoring.py:166`
- **Code:** `except Exception: continue`
- **Risk:** RiskEngine rules que falham sao ignoradas sem log. Em producao, regras de risco podem estar desabilitadas sem ninguem saber.

### C02. `mem0_client.py` — 6 blocos `except Exception` que silenciam falhas de memoria
- **File:** `src/core/storage/mem0_client.py` (linhas 59, 148, 158, 169, 200, 213, 252, 265, 300)
- **Risk:** Memoria persistente falha silenciosamente para local file, redis, e API. Usuario nunca sabe que memoria esta degradada.

### C03. `time.sleep()` em codigo de producao
- **Files:** `data/wolfram_provider.py:76`, `data_collector/professional.py:368`, `model_serving/gateway.py:348`
- **Risk:** `gateway.py:348` esta dentro de um generator `chat_completion_stream()`. Se chamado em async context, bloqueia o event loop.

### C04. `tools/custom_tools.py:8` — type hint `...` (Ellipsis) em producao
- **File:** `src/tools/custom_tools.py:8`
- **Code:** `registry = ...  # objeto com método register(...)`
- **Risk:** Docstring com sintaxe invalida. Se alguém importar e executar, `registry` vira Ellipsis.

---

## HIGH (P2)

### H01. 3 diretorios vazios orfaos
- `src/core/scanner/` — referenciado por runtime (removido) com ImportError fallback
- `src/core/mathcore/` — zero referencias
- `src/core/evidence/` — zero referencias

### H02. `core/engine/` deprecated mas importado por 2 consumidores
- `src/agent_server/endpoints.py:14` importa `calc_sma, calc_ema, calc_rsi, calc_macd, calc_bollinger`
- `src/core/data_collector/collector.py:23` importa `FinancialEngine`
- `core/math/indicators.py` tem equivalentes. Engine e legado.

### H03. 60 de 117 modulos sem teste
- Pipeline inteiro (graph, nodes, contracts, prompts): zero testes
- agent_runtime: zero testes
- investor/: zero testes
- data/ (9 providers): zero testes

### H04. `f51/__init__.py` try/except esconde ImportError
- **File:** `src/f51/__init__.py:51`
- **Detail:** Wrap de import com `except Exception` que pode mascarar dependencias faltando.

---

## MEDIUM (P3)

### M01. 55 env vars sem .env.example
- Espalhadas por 20+ arquivos. Sem centralizacao. Sem defaults documentados.

### M02. `scripts/server.py` orfao
- Nao referenciado em nenhum lugar. Nao e entrypoint registrado.

### M03. `docs/internal/SECURITY_LEAKED_KEYS.md`
- Documenta keys vazadas. Se keys foram rotacionadas, o doc e lixo. Se nao, e risco.

### M04. Ruff: 11 erros (5 unused imports, 5 E402, 1 lambda)
- Nao bloqueia runtime mas indica descuido.

### M05. Ruff format: 32 arquivos desformatados

---

## EVIDENCIA: Testes
```
344 passed, 2 skipped, 0 failed (9.16s)
```
Os testes passam porque **nenhum teste importa o pipeline**. A cobertura do pipeline e zero.

## EVIDENCIA: Pipeline
```
Graph built OK: CompiledStateGraph
Nodes: __start__, orchestrator_primary, data, f51_verdict, pennylab,
       run_expert, collect_experts, rag_forensics, ceo_primary,
       explanation, respond_blocked
```
O graph compila. Mas:
- Nao tem `shutdown()` — crash no stop
- Nao tem `chat()` / `stream_events()` — API publica removida
- Nodes nao recebem DI completa (audit, data_collector, financial_agents)

## MOCKS EM PRODUCAO
Nenhum mock encontrado em src/. PASS.

## API KEYS HARDCODED
Nenhuma. Todas usam `os.getenv()`. PASS.

## BARE EXCEPT
Nenhum `except:` (bare). Apenas `except Exception` e `except ImportError`. PASS com ressalvas.
