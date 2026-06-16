# Roadmap 10/10 — Distribuição de Tarefas

## Estado Atual: 9.2/10

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

---

## Ordem de Execução

```
✅ 1. C1 (Penny scanner integrado) — Codex
✅ 2. C2 (check_before_trade) — Codex
✅ 3. D1 (Calibrate no SYSTEM STATUS) — Deep
✅ 4. D2 (IBKR Mirror) — Deep
✅ 5. C3 (Deep Panel) — Codex
✅ 6. D3 (Histórico sentimento) — Deep
✅ 7. F1+F2 (Bug fixes) — Extra
⬜ 8. M1 (TWS presets) — Marco
⬜ 9. M2 (CEO fallback test) — Marco
⬜ 10. M3 (Paper trading real) — Marco
```

## Alvo: 10/10

## Resultado dos Testes
- **1244 passed**, 4 failed (integration — requer servidor live)
- 5 bugs pré-existentes corrigidos
- Lint: All checks passed
