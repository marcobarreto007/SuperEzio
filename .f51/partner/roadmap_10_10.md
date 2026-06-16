# Roadmap 10/10 — Distribuição de Tarefas

## Estado Atual: 9.5/10

> **Última atualização:** 2026-06-16
> **Suíte:** 1250 passed, 0 failed
> **Commits na sessão:** 7

---

## 🔴 MARCO (3 tarefas — o que só tu pode fazer)

| # | Tarefa | Por que tu | Esforço |
|---|---|---|---|
| M1 | **TWS Presets** — desmarcar TIF automático no Global Configuration | Só tu tem acesso à interface do TWS | 2 min |
| M2 | **Testar CEO fallback** — derrubar Qwen e ver se GLM assume | Precisa de acesso físico à máquina | 10 min |
| M3 | **Rodar ciclo de paper trading real** — 5 ordens, observar pipeline | Validação operacional | 30 min |

---

## 🟢 CODEX (3 tarefas — código rápido e repetitivo) ✅

| # | Tarefa | Arquivo | Esforço | Status |
|---|---|---|---|---|
| C1 | **Penny scanner integrado ao collector** — usar `penny_scanner.scan_penny_stocks()` como fallback quando OpenBB não acha < $5 | `src/core/pipeline/nodes/collector.py` | 20 linhas | ✅ DONE |
| C2 | **check_before_trade no tool_executor** — chamar `feedback_loop.check_before_trade()` antes de `submit_paper_order` | `src/core/pipeline/nodes/tool_executor.py` | 15 linhas | ✅ DONE |
| C3 | **Deep Panel coluna própria** — mover de dentro do chart-workspace pra uma coluna dedicada no grid | `frontend/index.html` + `frontend/css/cockpit.css` | 30 linhas | ✅ DONE |

---

## 🟡 DEEP (3 tarefas — integração e revisão) ✅

| # | Tarefa | Arquivo | Esforço | Status |
|---|---|---|---|---|
| D1 | **Calibrate no SYSTEM STATUS** — injetar `calibrate_confidence()` nas observações do Bob | `src/core/pipeline/nodes/agent.py` | 10 linhas | ✅ DONE |
| D2 | **IBKR Mirror funcional** — garantir que ordens do TWS aparecem (timeout + dedup) | `src/agent_server/endpoints.py` | 15 linhas | ✅ DONE |
| D3 | **Histórico de sentimento** — SQLite table + persistir cada poll do LiveMonitor | `src/core/sentiment/live_monitor.py` | 30 linhas | ✅ DONE |

---

## 🔧 BUG FIXES (extra)

| # | Bug | Arquivo | Status |
|---|---|---|---|
| F1 | `_resolve_evidence_file` sem `return` → sempre retornava None | `src/agent_server/endpoints.py` | ✅ FIXED |
| F2 | ApprovalGate tests quebrados após `max_auto_approve_amount` mudar de 0→500 | `tests/test_trading_loop3.py` | ✅ FIXED |
| F3 | **D3 CRÍTICO:** `_persist_to_db` 100% quebrado — `Path` e `json` não importados, `NameError` engolido por `except Exception: pass`. Tabela `sentiment_history` nunca foi criada. | `src/core/sentiment/live_monitor.py` | ✅ FIXED |

---

## 🆕 EXTRAS (entregues além do roadmap)

| # | Feature | Arquivo | Status |
|---|---|---|---|
| E1 | **Endpoint `/sentiment/history/{ticker}/db`** — consulta SQLite histórico de sentimento (longo prazo, até 365 dias) | `src/agent_server/endpoints.py` | ✅ DONE |
| E2 | **`db_rows` no cockpit summary** — count de `sentiment_history` exposto no `/cockpit/summary` | `src/agent_server/endpoints.py` | ✅ DONE |
| E3 | **Testes D3:** `test_persist_to_db_creates_table_and_inserts_row` + `test_persist_to_db_non_critical_failure_does_not_raise` | `tests/test_sentiment_live_monitor.py` | ✅ DONE |
| E4 | **Stress test 25 ordens** — script `scripts/stress_test_25.py` com 5 tiers (micro→extreme) | `scripts/stress_test_25.py` | ✅ DONE |

---

## Ordem de Execução

```
✅ 1. C1 (Penny scanner integrado) — Codex
✅ 2. C2 (check_before_trade) — Codex
✅ 3. D1 (Calibrate no SYSTEM STATUS) — Deep
✅ 4. D2 (IBKR Mirror) — Deep
✅ 5. C3 (Deep Panel) — Codex
✅ 6. D3 (Histórico sentimento) — Deep
✅ 7. F1+F2+F3 (Bug fixes) — Extra
✅ 8. E1+E2 (Sentiment DB endpoint + cockpit) — Extra
✅ 9. E3 (Testes D3) — Extra
✅ 10. E4 (Stress test 25 ordens) — Extra
⬜ 11. M1 (TWS presets) — Marco
⬜ 12. M2 (CEO fallback test) — Marco
⬜ 13. M3 (Paper trading real — 25 ordens stress) — Marco
```

## Alvo: 10/10

## Resultado dos Testes
- **1250 passed, 0 failed**
- 7 bugs corrigidos (1 crítico D3, 1 evidence, 5 approval)
- 2 endpoints novos
- Lint: All checks passed
- Stress test: 25 ordens pipeline (micro→small→medium→large→extreme)
