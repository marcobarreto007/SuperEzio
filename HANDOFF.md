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
- **Modelos**: 100% cloud model APIs. Bob/CEO e orquestrador via Z.ai GLM-5.3
  (ou DeepSeek V4 Pro) preservando a persona executiva e mandamentos; experts
  financeiros, judge e auditor via DeepSeek V4 Pro HTTPS API oficial. Não requer
  nem roda servidor local em :8080. API/UI/chat única em `:8002`
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
