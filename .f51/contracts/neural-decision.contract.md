# NeuralDecisionExpert Contract

**Module:** `src/core/pipeline/nodes/neural_decision.py`
**Classification:** pipeline

## Public API

| Function | Signature | Returns | Contract |
|----------|-----------|---------|----------|
| `node_neural_decision` | `async (state: dict) -> dict` | `{"neural_decision": {...}}` | Nó do LangGraph. Produz directional forecast + regime. |

### neural_decision output dict

```python
{
    "direction_prob": {"up": float, "down": float, "sideways": float},
    "expected_return": float,
    "drawdown_risk": float,
    "uncertainty": float,
    "regime": str,          # "trend_real", "mean_reverting", "chaotic", etc.
    "recommendation": str,  # "alerta_forte", "hold", etc.
    "veto": bool,
    "reason": str,
    "timeframe": str,
}
```

## Invariants

1. `direction_prob.up + direction_prob.down + direction_prob.sideways ≈ 1.0`
2. `drawdown_risk ∈ [0, 1]`
3. `uncertainty ∈ [0, 1]`
4. `veto` = True se `drawdown_risk > 0.8` ou `uncertainty > 0.9`
5. Se route != "ticker_analysis" ou sem ticker, retorna `{}` (skipped).
6. Dedup guard: mesmo `run_id` nunca executa 2x.

## Dependencies

- `src/experts/neural_decision/neural_decision_expert.py` — NeuralDecisionExpert
- `src/experts/technical_neural/` — PriceMLP, PriceTorchMLP (fallback)
- Dados do PipelineState.data (technicals, price)

## Routing

- `route_after_neural_decision` → "rag_forensics" se route ticker_analysis, senão "collect_experts"
