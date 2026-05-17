# Pipeline Contracts

**Module:** `src/core/pipeline/contracts.py`
**Classification:** pipeline

## PipelineState (TypedDict)

Estado unificado que flui por todos os nós do LangGraph.

### Campos obrigatórios por nó

| Nó | Campos que produz | Campos que consome |
|----|-------------------|--------------------|
| orchestrator | route, intent, action, ticker, intent_confidence, intent_reasons, entities, time_horizon | message |
| collector | data, data_context | route, ticker |
| f51_verdict | f51_verdict | data, route, ticker |
| experts | expert_results, expert_summary | route, ticker, data_context, data |
| neural_decision | neural_decision | route, ticker, data |
| rag_forensics | rag_context | ticker, data |
| ceo_primary | final | message, route, intent, ticker, data_context, expert_summary, neural_decision, rag_context, f51_verdict, pennylab_result |
| explanation | explanation | f51_verdict, final |

### Reducer

`expert_results` usa reducer `_expert_results_reducer` que concatena listas (fan-in de Send).

## Pydantic Models

| Model | Fields | Uso |
|-------|--------|-----|
| `IntentResult` | route, intent, action, ticker, filters, confidence, required_slots, reasons, entities, diary, pennylab, source | Output do orchestrator |
| `CEORequest` | task, ticker, intent, route, data_context, pennylab_context, expert_summary, rag_context, f51_verdict, chart_context, mandamentos, model_family | Input do CEO node |
| `ExpertCall` | role, ticker, context, provider_name, timeout | Invocação de expert individual |

## Invariants

1. PipelineState.route ∈ {"general", "ticker_analysis", "market_scan", "needs_scope"}
2. Se route = "ticker_analysis", ticker deve ser não-vazio.
3. expert_results é sempre uma lista (nunca None após reducer).
4. f51_verdict contém chaves: confidence, passed, factors, hub_risk_score.

## Dependencies

- `langgraph` (TypedDict state, Send, reducer)
- `pydantic` (BaseModel, Field)
- Sem dependências de rede ou modelo
