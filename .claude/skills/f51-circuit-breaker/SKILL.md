---
name: f51-circuit-breaker
description: "Implementa circuit breaker com tenacity para chamadas externas (IBKR, DataHub, journal). Evita cascata de falhas e adiciona graceful degradation. Triggers: circuit breaker, retry, backoff, tenacity, resilience, graceful degradation, fallback."
compatibility: "SuperEzio bootstrap layer"
allowed-tools: "Read, Edit, Write, Bash, Grep, Diff"
depends-on: [f51-contracts, f51-runtime]
related-skills: [f51-idempotency, f51-audit]
---

# f51-circuit-breaker

## Quando usar

- Chamadas externas (IBKR, DataHub) falham e o sistema não tem retry inteligente
- Falha em um serviço externo bloqueia todas as ordens (sem graceful degradation)
- Não existe backoff exponencial — retry imediato sobrecarrega serviço
- Precisa de fallback (ex: cache de preço quando DataHub offline)

## Nunca fazer

- Retry infinito sem limite de tempo
- Circuit breaker que nunca fecha de volta (precisa de half-open)
- Fallback que retorna dado stale sem avisar que é stale
- Usar retry para erro de negócio (só para erro transitório)

## Workflow

1. **Auditar chamadas externas**: listar todas as dependências externas e seus modos de falha.
2. **Classificar erros**: `TRANSIENT` (timeout, conexão recusada) vs `PERMANENT` (dados inválidos, auth falhou).
3. **Configurar tenacity**: `@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=10), retry=retry_if_exception_type(TransientError))`.
4. **Implementar circuit breaker state**: CLOSED → OPEN (após N falhas) → HALF_OPEN (após timeout) → CLOSED (se sucesso).
5. **Adicionar fallback por dependência**: DataHub offline → usa cache de preço (TTL 5min). IBKR offline → enfileira ordem para quando voltar. Journal offline → dead letter queue.
6. **Expor métricas**: `circuit_breaker_state{service="ibkr|datahub|journal"} 0|1|2`.
7. **Testar**: desconectar serviço → circuito abre → half-open → fecha.

## Portões de decisão

- Se retry é aplicado a erro permanente (ex: ticker inválido): bloqueado.
- Se fallback não avisa que dado é stale: bloqueado.
- Se circuit breaker não tem half-open: bloqueado.

## Padrão de implementação

```python
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
    before_log,
    after_log,
)

class TransientError(Exception): ...
class PermanentError(Exception): ...

@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=10),
    retry=retry_if_exception_type(TransientError),
    before=before_log(logger, logging.WARNING),
    after=after_log(logger, logging.DEBUG),
)
async def fetch_price_with_retry(ticker: str) -> float | None:
    ...
```

## Entregáveis mínimos

```
== F51 CIRCUIT BREAKER REPORT ==

## Dependências externas
- [serviço]: [TRANSIENT errors] [PERMANENT errors] [fallback]

## Circuit breakers implementados
- [serviço]: [CLOSED/OPEN/HALF_OPEN] [threshold N falhas] [timeout Ts]

## Fallbacks
- [serviço]: [cache / queue / dead_letter]

## Métricas
- [nome]: [tipo] [labels]

## Testes
- [test_circuit_opens_on_failure]: [PASS / FAIL]
- [test_half_open_recovery]: [PASS / FAIL]
- [test_fallback_serves_stale_with_warning]: [PASS / FAIL]

## Checkpoint
- Atualizado em `.f51/checkpoints/latest.json`
```

## Regras

- Retry só para erro transitório.
- Circuit breaker sem half-open é só um kill switch glorificado.
- Todo fallback deve logar `stale=True` explicitamente.
- Métricas de circuit breaker são obrigatórias — sem visibilidade, sem segurança.
