# F51 Tasks — SuperEzio v3.0.1

**Data**: 2026-05-13
**Status**: Planejamento P1/P2 fechado

## P1 — Correcoes de produto e seguranca

### [x] P1.1 — Corrigir ticker lowercase PT-BR

- **Arquivos**: `src/core/pipeline/intents.py`, `tests/test_intents.py`
- **Resultado**: `tsla`, `aapl`, `nvda`, `petr4`, `mglu3` detectam em caixa baixa/mista sem transformar palavras comuns em ticker.
- **Verificacao**: `tests/test_intents.py` passou na suite completa.

### [x] P1.2 — Gateway cobre rotas sensiveis

- **Arquivos**: `src/core/agent_runtime/edge/gateway.py`, `src/agent_server/main.py`
- **Resultado**: `/task/submit` continua com body guard; demais rotas sensiveis exigem rate/auth; `/health` e assets estaticos seguem publicos.

### [x] P1.3 — Defaults seguros de bind/auth

- **Arquivos**: `src/core/config/schema.py`, `.env.example`, `README.md`
- **Resultado**: loopback por default; dev local documentado; producao exige auth/secret/API key.

### [x] P1.4/P2.2 — Remover falhas silenciosas de alto impacto

- **Arquivos**: `src/core/pipeline/nodes.py`, `src/agent_server/main.py`, `src/agent_server/endpoints.py`, `src/core/engine/__init__.py`, `src/data/data_hub.py`, `src/f51/memory.py`, `src/core/f51_adapter/adapter.py`, `src/core/observability/notifications.py`, `src/core/rl/rewards.py`, `src/experts/crisis/expert/crisis_expert.py`
- **Resultado**: falhas best-effort continuam sem derrubar o sistema, mas agora ficam visiveis em log/erro estruturado.

### [x] P1.5 — PennyLab sem fallback falso

- **Arquivos**: `src/core/pipeline/runtime.py`, `src/core/pipeline/ceo_prompts.py`
- **Resultado**: falha do PennyLab vira `decision=None`; o prompt do CEO omite esse bloco.

## P2 — Honestidade, limpeza e docs

### [x] P2.1 — CrisisMath com labels honestos

- **Arquivos**: `src/experts/crisis/models/*`, `tests/test_crisis.py`
- **Resultado**: Markov/IMF expõem implementação heuristica; BIS marca fallback degradado; LPPLS nao cria falso positivo em serie constante.

### [x] P2.3 — Limpeza de artefatos

- **Arquivos**: `scripts/legacy/*`, `scratch/*`, `reports/*`, `preview.html`
- **Resultado**: scripts sem caller movidos para `scripts/legacy`; scratch/preview/report antigo removidos.

### [x] P2.5 — Docs sincronizados

- **Arquivos**: `README.md`, `docs/internal/audits/*`, `docs/internal/SECURITY_LEAKED_KEYS.md`, `docs/claude-ops-catalog.md`, `.claude/mcp-catalog.json`, `.claude/skills/*`
- **Resultado**: README reflete comandos reais, relatorios internos movidos, risco de chaves historicas documentado sem prefixos de segredo.

## Gate final

- [x] `python -m pytest tests/ -q --tb=short` — 345 passed.
- [x] `python -m ruff check src tests` — passed.
- [x] `python -m ruff format --check src tests` — passed.
- [x] Import publico F51 — passed.
- [x] Contrato `F51Engine.run()` — passed.
- [x] Import `agent_server.main` — passed.
- [ ] `pyright .` — nao instalado no ambiente.

## Proxima tarefa operacional

Rotacionar chaves antigas indicadas em `docs/internal/SECURITY_LEAKED_KEYS.md`.
