# SDCA-Lite v0.1 Inventory

Date: 2026-05-19

## Files Found

- Runtime/API entrypoint: `src/agent_server/main.py`
  - Creates the FastAPI app, loads config/env, initializes the pipeline in lifespan, and includes `agent_server.endpoints.router`.
- API routes: `src/agent_server/endpoints.py`
  - Existing routes include `/task/submit`, `/capabilities`, `/product/manifest`, `/api/chart-data/{ticker}`, `/experts/neural-decision/predict`.
  - Logging pattern: module-level `logger = logging.getLogger(__name__)`.
- Pipeline graph: `src/core/pipeline/graph.py`
  - LangGraph path: orchestrator -> data -> f51_verdict -> pennylab -> experts -> neural_decision -> rag_forensics -> ceo_primary -> explanation.
- Pipeline state/contracts: `src/core/pipeline/contracts.py`
  - Uses `TypedDict` for LangGraph state and Pydantic `BaseModel` for node I/O contracts.
- Pipeline nodes: `src/core/pipeline/nodes/`
  - Relevant defensive nodes/modules: `guardrails.py`, `f51.py`, `neural_decision.py`, `rag.py`, `ceo.py`.
- Prompt builder: `src/core/pipeline/prompts/builder.py`
  - Converts pipeline evidence into CEO prompt sections and module coverage requirements.
- Risk/veracity/decision modules:
  - `src/f51/gates.py`: `VeracityGate`, `AdversarialCritic`, `ProxyReward`.
  - `src/f51/formulas.py`: unified scoring and decision thresholds.
  - `src/core/investor/fraud_analyst.py`, `fraud_memory.py`, `committee.py`: fraud/investor risk logic.
  - `src/core/rag/fraud_rag.py`: local fraud pattern retrieval.
  - `src/experts/pennylab/experts/veracity_gate.py`: PennyLab veracity gate.
  - `src/experts/neural_decision/neural_decision_expert.py`: technical/risk decision expert, no broker execution.
- Broker/execution modules exist but must not be imported by SDCA:
  - `src/core/trading/broker.py`, `src/core/trading/order_builder.py`, `src/adapters/broker/ibkr_adapter.py`.
- Tests:
  - Main folder: `tests/`.
  - Contract tests: `tests/contracts/`.
  - Shared test path setup: `tests/conftest.py` inserts `src/` into `sys.path`.

## Packaging Constraint

`pyproject.toml` package discovery includes `agent_server*`, `core*`, `data*`, `experts*`, `f51*`, `tools*`, and `adapters*`. There is no existing `src/superezio` package. Creating `src/superezio/risk_firewall` would not be packaged without editing package discovery.

## Recommended Integration Point

Use `src/core/risk_firewall/` for the SDCA-Lite module.

Rationale:

- `core` is already packaged and imported across runtime/tests.
- The feature is a cross-cutting defensive layer, not a domain expert or broker adapter.
- It can remain isolated, deterministic, and reversible.

Minimal runtime integration:

- Add standalone endpoint `POST /api/sdca/evaluate` in `src/agent_server/endpoints.py`.
- Add a small pipeline node after `neural_decision` and before `rag_forensics` to attach `sdca_firewall` evidence to state for ticker-analysis flows.
- Add SDCA evidence to the CEO prompt builder so BLOCK/REVIEW is visible to the final answer without changing existing public stream contracts.

## Risks of Integration

- The existing CEO prompt currently pushes BUY/SELL/HOLD language aggressively. SDCA evidence must explicitly mark BLOCK/REVIEW as a defensive constraint to avoid being ignored.
- The pipeline has broker modules in the repo. SDCA must not import `core.trading`, `adapters.broker`, or any execution module.
- The new node must be deterministic and must not call an LLM or network API.
- Adding a graph node can affect stream event ordering; keep the event additive (`SDCA_FIREWALL`) and do not remove existing events.
- Experience retrieval must not overfit only to high `delta_r`; scoring must include similarity, regime similarity, and evidence quality.

## Files to Create

- `src/core/risk_firewall/__init__.py`
- `src/core/risk_firewall/sdca_contracts.py`
- `src/core/risk_firewall/experience_memory.py`
- `src/core/risk_firewall/sdca_lite.py`
- `src/core/pipeline/nodes/sdca_firewall.py`
- `data/sdca_experience_memory.jsonl`
- `tests/test_sdca_lite.py`
- `docs/SDCA_LITE_MONEY_GATE.md`
- `reports/sdca_lite_audit.json`

## Files to Alter

- `src/agent_server/endpoints.py`
- `src/core/pipeline/contracts.py`
- `src/core/pipeline/graph.py`
- `src/core/pipeline/nodes/__init__.py`
- `src/core/pipeline/prompts/builder.py`
- `.f51/checkpoints/latest.json`

## Final Architecture Decision

Implement SDCA-Lite v0.1 as `core.risk_firewall`: a pure, deterministic F51 Cognitive Risk Firewall with stable Pydantic contracts, local JSONL experience memory, heuristic rumination, consequence scoring, a public evaluation API, and one additive pipeline integration point. The module will not execute trades, import broker adapters, predict prices, call external APIs, or refactor existing trading/risk systems.
