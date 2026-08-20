# SuperEzio — Documentação Final
# Versão: v4.0 | Data: 2026-06-16 | Nota: 9.5/10

> **HISTORICO / SUPERSEDED.** Esta documentacao final v4.0 preserva o estado de 2026-06-16. Para o contrato atual use `docs/runbooks/RUNBOOK.md`.

---

## Arquitetura

```
CEO (Qwen3-Next-80B :8082) — Decide, soberano, abliterated
  ├─ Genie (Gemini 3.5 :cloud) — Sentimento, informação privilegiada
  ├─ Deep (DeepSeek V4 :cloud) — Matemática financeira, 6 experts
  └─ Bob Codex (GLM 5.2) — Implementador (Claude Code)

Pipeline: orchestrator → coleta → MathHub → 6 experts → F51 → 
          Neural → SDCA → RAG → 30 guardrails → Trinity → Bob → IBKR
```

## Módulos Entregues

| Módulo | Arquivo | Status |
|---|---|---|
| MathHub (12 módulos) | src/core/math/math_hub.py | ✅ |
| GuardrailHub (30 guardrails) | src/core/pipeline/nodes/guardrail_hub.py | ✅ |
| DecisionTrace (audit) | src/core/audit/decision_trace.py | ✅ |
| Trinity (Bob↔Genie↔Deep) | src/core/pipeline/nodes/trinity.py | ✅ |
| ExpertDialogue | src/core/pipeline/nodes/expert_dialogue.py | ✅ |
| FeedbackLoop | src/core/trading/feedback_loop.py | ✅ |
| Penny Scanner (< $5) | src/core/scanner/penny_scanner.py | ✅ |
| LiveMonitor (sentimento) | src/core/sentiment/live_monitor.py | ✅ |
| Cockpit (5 painéis) | frontend/js/*.js | ✅ |
| Memory System (5 camadas) | src/core/memory/ | ✅ |

## Trading Real (Comprovado)

- IBKR paper: $100K conectado
- SMWB: 1100 shares via pipeline (BOB encontrou, analisou, comprou)
- SNDL: 10 shares via bridge direta
- Ordens GTC: sem cancelamento TWS
- Ponte: pipeline → subprocess → ib_insync → TWS (verificada)

## Como Iniciar

1. Abrir TWS Workstation (porta 7497, paper)
2. Duplo clique em `start_all.bat`
3. Aguardar CEO carregar (~30s) + API subir (~3s)
4. Abrir http://127.0.0.1:8002

## Como Testar

```powershell
python -m pytest tests/ -q           # suíte completa (1250 testes)
python scripts/browser_smoke.py      # smoke test do frontend
```

## Roadmap 10/10

Pendente (3 itens — Marco):
- M1: TWS presets (desmarcar TIF automático)
- M2: Testar CEO fallback (GLM assume se Qwen cair)
- M3: Rodar paper trading real (5 ordens, observar pipeline)
