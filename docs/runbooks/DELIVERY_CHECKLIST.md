# DELIVERY CHECKLIST — SuperEzio v4.0.0
Date: 2026-05-15

## Bloqueadores (NAO PODE ENTREGAR SEM RESOLVER)

- [ ] **B01** `main.py:116` — `pipeline.shutdown()` crash. CompiledStateGraph nao tem shutdown.
- [ ] **B02** `runtime.py` removido — API publica (`chat`, `chat_sync`, `stream_events`, `get_status`) perdida. Necessario migrar para `graph.py` ou criar wrapper.
- [ ] **B03** Nodes standalone sem DI completa — `financial_agents`, `mandamentos`, `_data_collector`, `_audit` nao injetados via `graph.py`.

## Pre-Demo (resolver antes de demonstrar)

- [ ] Verificar se `python -m agent_server.main` sobe sem crash
- [ ] Verificar se uma request real chega ao CEO node e volta
- [ ] Verificar se o shutdown graciosamente para (B01)
- [ ] Ruff fix: `python -m ruff check --fix src tests`
- [ ] Ruff format: `python -m ruff format src tests`
- [ ] Confirmar que 344 testes continuam passando apos fixes

## Pre-Venda (resolver antes de posicionar comercialmente)

- [ ] Criar `.env.example` com as 55 variaveis e defaults
- [ ] Adicionar smoke test end-to-end do pipeline (graph.astream com input fake)
- [ ] Adicionar teste de contrato para `build_graph()` (verificar nodes e edges)
- [ ] Remover 3 diretorios vazios orfaos (scanner/, mathcore/, evidence/)
- [ ] Decidir: `core/engine/` fica ou migra para `core/math/`
- [ ] Adicionar `shutdown()` ao CompiledStateGraph ou wrapper
- [ ] Documentar API publica do pipeline v4 (o que substituiu `UniversalPipeline.chat()`)
- [ ] Adicionar teste que instancia o pipeline com gateway=None e roda um input

## Pos-Demo (backlog)

- [ ] Consolidar nodes duplicados (escolher: mixin ou standalone)
- [ ] Consolidar prompts duplicados (escolher: ceo_prompts.py ou prompts/builder.py)
- [ ] Cobertura de teste para pipeline/ (target: 80%)
- [ ] Cobertura de teste para agent_runtime/
- [ ] Centralizar config/env vars em schema.py
- [ ] Limpar scripts/server.py orfao
- [ ] Avaliar docs/internal/SECURITY_LEAKED_KEYS.md — rotacionar keys ou remover doc
