# Agent Server Contract

**Module:** `src/agent_server/main.py`, `src/agent_server/endpoints.py`
**Classification:** app
**Runtime role:** official FastAPI API surface for SuperEzio.

## Public Entrypoint

| Item | Contract |
| --- | --- |
| Command | `python -m agent_server.main` |
| Python path | `src` must be importable |
| Bind | `127.0.0.1:8002` unless explicitly overridden by runtime env |
| Frontend | `/` serves `frontend/index.html` when present |
| Static assets | `/frontend` mounts the local `frontend/` directory when present |

## Public Routes

| Route | Method | Contract |
| --- | --- | --- |
| `/` | GET | Returns frontend HTML or a small service object if the frontend is missing. |
| `/health` | GET, HEAD | Public liveness. GET returns a dict with `status=ok`; HEAD returns 200. |
| `/health/details` | GET | Readiness details for GPU, local models, Redis, providers, and cost guard. |
| `/metrics` | GET | Returns service metrics from the observability layer. |
| `/neural/logs` | GET | Streams observability logs as SSE. |
| `/api/chart-data/{ticker}` | GET | Returns normalized OHLCV, profile, price, and indicators from DataHub. |
| `/api/chart-sse/{ticker}` | GET | Streams chart snapshots, candle updates, errors, and heartbeat events. |
| `/task/submit` | POST | Accepts an A2A `TASK.SUBMIT` envelope and streams NDJSON pipeline events. |
| `/capabilities` | GET | Returns product capability metadata. |
| `/product/manifest` | GET | Returns public product metadata plus runtime pipeline status when initialized. |
| `/api/sdca/evaluate` | POST | Evaluates a decision candidate with SDCA-Lite. It must not execute trades. |
| `/experts/neural-decision/predict` | POST | Runs NeuralDecisionExpert and returns prediction or validation error. |
| `/trade/td-commission-free` | GET | Returns the dated TD Direct Investing commission-free ETF research universe and its official source. |
| `/trade/td-draft` | POST | Creates an authenticated, single-use-token, local draft. Always returns `ok=false`, `ready_for_execution=false`; never connects to TD or submits an order. |

## Runtime Invariants

1. Importing `agent_server.main:app` must not start CEO, API, browser, or external services.
2. The canonical API command remains `python -m agent_server.main`.
3. `/task/submit` must require `MessageType.TASK_SUBMIT`.
4. `/task/submit` output is newline-delimited JSON events, not fake SSE text.
5. Errors emitted through `/task/submit` must redact secret-like environment values.
6. `PRODUCT_MANIFEST.safe_actions` must stay non-executing; no broker/order route is introduced here.
7. TD credentials and account numbers are forbidden. TD access remains manual through official TD platforms.
8. A caller-supplied quote is untrusted evidence and cannot promote a TD draft to execution-ready.
9. Commission-free eligibility is a dated research filter, not an investment recommendation; the operator must confirm the TD order preview.

## Dependencies

- `fastapi`, `uvicorn`, `sse-starlette`
- `core.pipeline.build_graph`
- `core.model_serving.gateway.create_gateway`
- `data.data_hub.hub`
- `frontend/index.html` for browser UI

## Verification

Minimum checks:

```powershell
python -m pytest tests/contracts/test_contract_main.py tests/contracts/test_contract_endpoints.py tests/contracts/test_contract_runtime_official.py -q
python -m pytest tests/test_runtime_smoke.py -q
```
