# Roadmap 10/10 — Distribuição de Tarefas

## Estado Atual: 8.0/10

---

## 🔴 MARCO (3 tarefas — o que só tu pode fazer)

| # | Tarefa | Por que tu | Esforço |
|---|---|---|---|
| M1 | **TWS Presets** — desmarcar TIF automático no Global Configuration | Só tu tem acesso à interface do TWS | 2 min |
| M2 | **Testar CEO fallback** — derrubar Qwen e ver se GLM assume | Precisa de acesso físico à máquina | 10 min |
| M3 | **Rodar ciclo de paper trading real** — 5 ordens, observar pipeline | Validação operacional | 30 min |

---

## 🟢 CODEX (3 tarefas — código rápido e repetitivo)

| # | Tarefa | Arquivo | Esforço |
|---|---|---|---|
| C1 | **Penny scanner integrado ao collector** — usar `penny_scanner.scan_penny_stocks()` como fallback quando OpenBB não acha < $5 | `src/core/pipeline/nodes/collector.py` | 20 linhas |
| C2 | **check_before_trade no tool_executor** — chamar `feedback_loop.check_before_trade()` antes de `submit_paper_order` | `src/core/pipeline/nodes/tool_executor.py` | 15 linhas |
| C3 | **Deep Panel coluna própria** — mover de dentro do chart-workspace pra uma coluna dedicada no grid | `frontend/index.html` + `frontend/css/cockpit.css` | 30 linhas |

---

## 🟡 DEEP (3 tarefas — integração e revisão)

| # | Tarefa | Arquivo | Esforço |
|---|---|---|---|
| D1 | **Calibrate no SYSTEM STATUS** — injetar `calibrate_confidence()` nas observações do Bob | `src/core/pipeline/nodes/agent.py` | 10 linhas |
| D2 | **IBKR Mirror funcional** — garantir que ordens do TWS aparecem (timeout + dedup) | `src/agent_server/endpoints.py` | 15 linhas |
| D3 | **Histórico de sentimento** — SQLite table + persistir cada poll do LiveMonitor | `src/core/sentiment/live_monitor.py` | 30 linhas |

---

## Ordem de Execução

```
1. M1 (TWS presets) — 2 min, desbloqueia tudo
2. C1 (Penny scanner integrado) — Codex
3. C2 (check_before_trade) — Codex
4. D1 (Calibrate no SYSTEM STATUS) — Deep
5. D2 (IBKR Mirror) — Deep
6. C3 (Deep Panel) — Codex
7. D3 (Histórico sentimento) — Deep
8. M2 (CEO fallback test) — Marco
9. M3 (Paper trading real) — Marco
10. Deep revisa tudo
```

## Alvo: 10/10
