# Two-Phase Paper Order — Execução Imediata + Validação Assíncrona

## Problema

Pipeline completo (experts cloud + Trinity + guardrails) = 60-120s.
HTTP timeout mata a conexão antes da ordem chegar no IBKR.
Usuário pede "compra X" e nunca vê a ordem executar.

## Solução: Two-Phase Commit Financeiro

### Fase 1: EXECUÇÃO IMEDIATA (bloqueante, <2s)

```
Usuário: "compra 100 shares AAPL paper"
  → POST /trade/execute
  → 1. Extrai ticker, qty, ação da mensagem
  → 2. PositionSizer rápido (sem esperar pipeline)
  → 3. KillSwitch check (síncrono, <1ms)
  → 4. submit_paper_order → IBKR
  → 5. Retorna IMMEDIATAMENTE: {"order_id": 52, "status": "Submitted"}
  → 6. Dispara pipeline em background (asyncio.create_task)
```

### Fase 2: VALIDAÇÃO ASSÍNCRONA (background, 60-120s)

```
Background task:
  → 7. Pipeline completo (experts + MathHub + Trinity + guardrails)
  → 8. Se guardrails ALLOW → ordem mantida, registro no journal
  → 9. Se guardrails BLOCK → cancela ordem no IBKR, notifica
  → 10. Resultado visível no cockpit (polling ou SSE)
```

## Implementação

### Novo endpoint: POST /trade/execute

```python
@router.post("/trade/execute")
async def execute_trade(payload: dict):
    # Fase 1: Execução imediata
    ticker = payload.get("ticker")
    action = payload.get("action", "buy")
    qty = int(payload.get("qty", 1))
    limit_price = float(payload.get("limit_price", 0))
    
    # Submit AGORA
    result = await _submit_paper_order(state, {
        "ticker": ticker, "action": action, 
        "qty": qty, "limit_price": limit_price,
        "order_type": "LMT"
    })
    
    # Pipeline em background
    asyncio.create_task(_run_pipeline_background(
        message=payload.get("message"),
        order_result=result,
        session_id=payload.get("session_id")
    ))
    
    return result  # Retorna em <2s
```

### Status tracking: GET /trade/status/{order_id}

```python
@router.get("/trade/status/{order_id}")
async def trade_status(order_id: str):
    # Retorna: submitted → validating → confirmed | cancelled
```

## Tradeoffs

- Vantagem: ordem executa em 2s, sem esperar pipeline
- Vantagem: guardrails ainda podem cancelar se detectarem problema
- Risco: ordem executada ANTES da análise completa (aceitável em paper)
- Risco: cancelamento depende do pipeline terminar (pode levar 120s)
