# HANDOFF — mapa de entrada para sessões novas

> A verdade durável vive em `.f51/checkpoints/latest.json` e nos demais
> arquivos de `.f51/`. Este arquivo é só o mapa de entrada — se você abriu uma
> sessão nova, comece por aqui e siga os ponteiros.

## Estado em 2026-09-03

- **Execução**: live execution FROZEN. Broker é `BROKER_NEUTRAL_VALIDATION_ONLY`
  (nunca envia ordem real). Ordens do cockpit viram tickets `PENDING_VALIDATION`;
  execução paper sai só do pipeline (`auto_execute_paper`) com journal
  append-only, idempotency cross-restart e dead letter queue com replay manual
  (`scripts/replay_dead_letters.py`).
- **Modelos**: boca local `:8080` = Ornith-1.0-9B-Q4_K_M (llama-server,
  texto-only, NÃO abliterado — recusa dele não é decisão do sistema).
  Watchdog do CEO: `scripts/watchdog_ceo.ps1`. Experts externos DeepSeek:
  pinned, fail-closed, sem fallback para o local. API/UI/chat: `:8002`
  (`agent_server.main`, porta única).
- **Mercado**: DataHub (roteador multi-provider com cache) + IBKRService
  (posições/equity; degraded usa fast-path com cache quente) + scan Mangala
  (`data/mangala_daily.json`).
- **Exército**: ver `AGENTS.md`; fluxo canônico captain → orchestrator →
  implementer → verificadores → release → savekeeper (único editor de docs).

## Onde ler

| Quero saber | Vou em |
|---|---|
| O que foi feito/provado na última sessão | `.f51/checkpoints/latest.json` |
| Runbooks operacionais | `docs/runbooks/RUNBOOK.md` |
| Regras e arquitetura | `CLAUDE.md` |
| Decisões de dinheiro | `.f51/MONEY_GATE.md` |
| Logs e trilhas | `runtime/logs/`, `data/*.jsonl`, `journal/` |
| Teses de mercado (scorecards) | `runtime/theses/` (ver README) |
