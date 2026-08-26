<!-- MOVED 2026-08-26 para deprecated/. Canônica: f51-observability (ver .claude/skills/deprecated/README.md) -->
---
name: f51-metrics-dash
description: "Cria endpoint /metrics Prometheus e dashboard mínimo com contadores de ordens, gates, latência e health. Triggers: metrics, prometheus, dashboard, grafana, /metrics, counter, gauge, histogram."
compatibility: "SuperEzio bootstrap layer"
allowed-tools: "Read, Edit, Write, Bash, Grep, Diff"
depends-on: [f51-contracts, f51-runtime, f51-observability]
related-skills: [f51-audit, f51-quality-gate, f51-money-gate]
---

# f51-metrics-dash

## Quando usar

- Sistema não expõe métricas de negócio (só logs textuais)
- Impossível responder "quantas ordens foram bloqueadas hoje?"
- Não há visibilidade de latência do pipeline
- Precisa de alertas básicos (ex: FREEZE está ligado? journal está escrevendo?)

## Nunca fazer

- Expor métricas sem autenticação em endpoint público
- Criar métrica com cardinalidade infinita (ex: label com `run_id`)
- Usar métrica como substituto de log (métrica agrega, log detalha)
- Deixar métrica sem documentação do que significa e qual threshold acionar

## Workflow

1. **Definir métricas de negócio essenciais**: o que o operador precisa saber em 5 segundos?
2. **Implementar endpoint `/metrics`**: usando `prometheus_client` com `generate_latest()`.
3. **Instrumentar pontos críticos**: F51 trade gate, auto_execute_paper, tool_executor, endpoints.
4. **Criar dashboard mínimo**: HTML estático ou console com `curl /metrics | grep`.
5. **Adicionar health check aggregado**: `/health` que consolida todos os health checks.
6. **Testar**: gerar tráfego simulado → verificar métricas incrementam corretamente.

## Métricas obrigatórias

```python
from prometheus_client import Counter, Gauge, Histogram, generate_latest

# Contadores
orders_total = Counter(
    "superezio_orders_total",
    "Total de ordens processadas",
    ["status", "ticker"]  # status: allowed|blocked|error
)
gate_failures_total = Counter(
    "superezio_gate_failures_total",
    "Falhas por gate",
    ["gate", "reason_code"]
)

# Gauges
execution_freeze = Gauge(
    "superezio_execution_freeze",
    "1 se FREEZE está ativo, 0 caso contrário"
)
ibkr_connectivity = Gauge(
    "superezio_ibkr_connectivity",
    "1 se IBKR está reachable, 0 caso contrário"
)
journal_health = Gauge(
    "superezio_journal_health",
    "1 se journal está writable, 0 caso contrário"
)

# Histogramas
pipeline_duration_seconds = Histogram(
    "superezio_pipeline_duration_seconds",
    "Latência do pipeline completo",
    buckets=[0.1, 0.5, 1, 2, 5, 10, 30, 60]
)
gate_evaluation_duration_seconds = Histogram(
    "superezio_gate_evaluation_duration_seconds",
    "Latência da avaliação dos 10 gates"
)
```

## Entregáveis mínimos

```
== F51 METRICS DASH REPORT ==

## Métricas implementadas
- [nome]: [tipo] [labels] [descrição]

## Endpoint /metrics
- URL: [http://localhost:8002/metrics]
- Autenticação: [none / basic / token]
- Formato: [Prometheus text format]

## Dashboard mínimo
- [HTML / console / Grafana]
- Métricas visíveis: [lista]

## Health agregado
- /health: [todos os checks consolidados]

## Alertas sugeridos
- [métrica] [condição] [severidade]

## Checkpoint
- Atualizado em `.f51/checkpoints/latest.json`
```

## Regras

- Métrica sem label de `status` é inútil — precisa saber se foi sucesso ou falha.
- Cardinalidade infinita = proibido. Sem `run_id` como label.
- `/metrics` deve responder em <100ms.
- Toda métrica nova deve ter documentação de: o que mede, qual threshold, o que fazer se disparar.
