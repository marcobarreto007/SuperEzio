---
name: loop
description: Executa um prompt em intervalo recorrente para monitoramento contínuo, polling de estado e tarefas periódicas com guardrails.
---

Use esta skill para tarefas recorrentes e idempotentes.

Antes de montar o loop, defina:
- objetivo
- intervalo
- condição de parada
- timeout
- evidência a registrar
- ação em caso de falha

Preferências:
- loops pequenos e auditáveis
- logs em arquivo
- zero side effect oculto

Responda com:

## LOOP

### Objetivo
[o que monitorar]

### Intervalo
[ex.: a cada 5 min]

### Condição de Parada
- [...]

### Evidência
- [log / arquivo / alerta]

### Riscos
- [...]

### Implementação Recomendada
- [script / task scheduler / agent]