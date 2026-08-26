---
name: f51-observability
description: "Instala e configura structured logging (structlog), métricas Prometheus e trace_id em todos os módulos críticos. Triggers: observability, logging, metrics, trace, structlog, prometheus, monitor, dashboard, telemetry."
compatibility: "SuperEzio bootstrap layer"
allowed-tools: "Read, Edit, Write, Bash, Grep, Glob, Diff"
depends-on: [f51-contracts, f51-runtime]
related-skills: [f51-refactor]
---

# f51-observability

## Quando usar

- Sistema não tem logging estruturado (só `logging.getLogger` puro)
- Não existe trace_id/correlation_id propagado entre módulos
- Métricas de negócio não são expostas (ordens, gates, latência)
- Precisa diagnosticar falha em produção sem grep manual

## Nunca fazer

- Trocar comportamento de negócio durante instrumentação
- Adicionar logging que vaza dados sensíveis (token, senha, PII)
- Criar métrica sem definir o que fazer quando o valor disparar
- Instrumentar sem testar que os logs saem no formato correto

## Workflow

1. **Auditar estado atual**: quantos arquivos usam `logging.getLogger` sem structlog? Onde `trace_id` deveria existir e não existe?
2. **Instalar structlog**: configurar `structlog.configure()` com formato JSON + timestamps UTC + `trace_id` vinculado automaticamente.
3. **Propagar trace_id**: injetar `run_id` como `trace_id` no início do pipeline e propagá-lo via `structlog.contextvars.bind_contextvars(trace_id=...)`.
4. **Instrumentar módulos críticos**: `f51_trade_gate.py`, `auto_execute_paper.py`, `tool_executor.py`, `endpoints.py`, `paper_journal.py`.
5. **Verificar**: rodar pipeline, capturar logs, validar que cada linha tem `trace_id`, `timestamp`, `module`, `event`.
6. **Atualizar checkpoint** com before/after dos formatos de log.

## Portões de decisão

- Se o log novo quebrar parsing existente (ex: alguém faz `grep` em formato antigo): adicionar flag de transição.
- Se `trace_id` não for propagado em todos os branches do pipeline: bloqueado.

## Entregáveis mínimos

```
== F51 OBSERVABILITY REPORT ==

## Módulos instrumentados
- [arquivo]: [structlog / prometheus / trace_id]

## Formato de log (before/after)
- Before: `logging.info("mensagem %s", var)`
- After: `logger.info("event_name", extra={"key": "value"})`

## Métricas expostas
- [nome_da_métrica]: [tipo: counter/gauge/histogram] — [descrição]

## Trace ID propagation
- [fluxo]: [OK / BROKEN]

## Evidência
- [comando rodado + output de amostra de log]

## Checkpoint
- Atualizado em `.f51/checkpoints/latest.json`
```

## Regras

- Log estruturado é JSON. Sem exceção.
- `trace_id` é obrigatório em todo log de pipeline.
- Métrica sem alerta definido é dívida futura — documentar o threshold.
- Nunca logar secrets, tokens, ou PII.
