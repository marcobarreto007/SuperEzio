# SuperEzio — Mapa de Comunicacao do Pipeline

## Pipeline Flow



## 7 Problemas de Comunicacao

| # | Problema | Impacto | Nos afetados |
|---|---|---|---|
| 1 | State plano — Bob nao ve proveniencia dos dados | Decisao sem contexto de fonte | agent, todos |
| 2 | Experts single-provider (DeepSeek) | Sem fallback se API cair | experts (6x) |
| 3 | Erros sao lista plana sem no de origem | Debugging impossivel em producao | todos |
| 4 | Sem latencia por no | Otimizacao cega | todos |
| 5 | Override do Bob nao registrado | Impossivel auditar decisao final | agent |
| 6 | Tool executor nao loga resultado | Falha silenciosa invisivel | tool_executor |
| 7 | Memory context injetado mas sem feedback | Bob pode ignorar memoria | agent |
