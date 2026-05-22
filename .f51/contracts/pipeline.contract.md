# Pipeline Contracts

**Module:** `src/core/pipeline/contracts.py`
**Classification:** pipeline

## PipelineState (TypedDict)

Estado unificado que flui por todos os nós do LangGraph no runtime v4.

### Grafo v4 Ativo (ReAct Loop)

```
START → orchestrator_primary → data (collector) → agent ⇄ tool_executor
                                               ↘ explanation (condicional) → END
                                               ↘ respond_blocked (condicional) → END
```

### Nós do Grafo e Invocação de Tools

Os nós do grafo LangGraph e seus fluxos de estado no runtime v4 são:

| Nó | Campos que produz | Campos que consome |
|----|-------------------|--------------------|
| orchestrator_primary | route, intent, action, ticker, intent_confidence, intent_reasons, entities, time_horizon | message |
| data | data, data_context | route, ticker, message |
| agent | agent_tool_call, agent_iterations | message, ticker, data_context, expert_summary, neural_decision, sdca_firewall, pennylab_result, scan |
| tool_executor | (Conforme a ferramenta chamada - ver abaixo) | agent_tool_call |
| explanation | final (ou chunk via stream) | final, f51_verdict |
| respond_blocked | final | errors |

### Ferramentas executadas via `tool_executor`

O nó `tool_executor` é responsável por executar ferramentas invocadas pelo `agent` no ciclo ReAct:

| Ferramenta / Função Interna | Campos Produzidos | Campos Consumidos |
|-----------------------------|--------------------|-------------------|
| `collect_data` / `node_collector` | data, data_context | ticker, route |
| `f51_firewall` / `node_f51_verdict` | f51_verdict | data, route, ticker |
| `run_experts` / `node_expert` + `node_collect_experts` | expert_results, expert_summary | route, ticker, data_context, data |
| `neural_decision` / `node_neural_decision` | neural_decision | route, ticker, data |
| `sdca_firewall` / `node_sdca_firewall` | sdca_firewall | route, ticker, data |
| `rag_forensics` / `node_rag_forensics` | rag_context | ticker, data |
| `pennylab` / `_pennylab_stub` | pennylab | ticker |
| `market_scan` / `node_collector` | scan | query / message |

## Pydantic Models

| Model | Fields | Uso |
|-------|--------|-----|
| `IntentResult` | route, intent, action, ticker, filters, confidence, required_slots, reasons, entities, diary, pennylab, source | Output do orchestrator |
| `CEORequest` | task, ticker, intent, route, data_context, pennylab_context, expert_summary, rag_context, f51_verdict, chart_context, mandamentos, model_family | Input estruturado |
| `ExpertCall` | role, ticker, context, provider_name, timeout | Invocação de expert individual |

## Invariants

1. PipelineState.route ∈ {"general", "ticker_analysis", "market_scan", "needs_scope"}
2. Se route = "ticker_analysis", ticker deve ser não-vazio.
3. expert_results é sempre uma lista (nunca None).
4. f51_verdict contém chaves: confidence, passed, factors, hub_risk_score.

## Dependencies

- `langgraph` (TypedDict state, StateGraph)
- `pydantic` (BaseModel)
