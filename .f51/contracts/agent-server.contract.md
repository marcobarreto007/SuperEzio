# Agent Server Contract

**Module:** `src/agent_server/main.py`, `src/agent_server/endpoints.py`, `src/agent_server/auth.py` (JWT gate + `/auth/*` routes)
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
| `/health` | GET, HEAD | Public liveness. GET returns a dict with `status=ok` and `auth_required: bool` (true when open access is disabled, false when `SUPEREZIO_OPEN_ACCESS=1`); HEAD returns 200. |
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

## Authentication & Authorization

Identity is single-mechanism: a JWT Bearer access token (HS256). The gate is
`jwt_auth_middleware` in `src/agent_server/auth.py`, mounted on the app at
`main.py:509-511` (`api_jwt_auth_middleware`); the `/auth/*` routes are
registered directly on the app by `register_auth_routes(app)` (`main.py:544`,
definitions `auth.py:494-621`). Users and refresh tokens persist in SQLite at
`runtime/auth.db` (`auth.py:41-42`).

### Modes

| Mode | Trigger | Behaviour | `/health` `auth_required` |
| --- | --- | --- | --- |
| Dev | `SUPEREZIO_JWT_SECRET` empty or unset (`auth.py:264-265`) | Guest identity (`dev_anon`) injected on protected routes; a valid Bearer, if present, is honoured instead. Never 401 (`auth.py:437-446`). | `false` |
| Open access | `SUPEREZIO_OPEN_ACCESS` in `1/true/yes/on` (`auth.py:268-276`) | Guest identity (`guest_open`) injected; same pass-through as dev (`auth.py:437-446`). | `false` |
| Prod-like | Secret set and open access off | Bearer required on every non-public route; 401 otherwise. | `true` |
| Public | `SUPEREZIO_PUBLIC_MODE` in `1/true/yes/on` (`auth.py:302-304`) | Fail-closed startup: secret shorter than 32 chars aborts the boot (`auth.py:315-330`); anonymous surface shrinks to the tightened set below. Registration closed unless `SUPEREZIO_PUBLIC_REGISTRATION=1` (`auth.py:307-312`). | per dev/open-access flags |

`auth_required` is computed by `auth_required_for_clients()` (`auth.py:279-281`)
and emitted by the health endpoint at `main.py:810`.

### Public surface — routes exempt from Bearer

Decision function `_is_public_path` (`auth.py:395-402`); the canonical path sets
live only in `auth.py:376-392` (main.py does not mirror them).

| Path set | Default / dev / open access (`_PUBLIC_EXACT`) | Public mode (`_PUBLIC_EXACT_TIGHTENED`) |
| --- | --- | --- |
| Exact | `/health`, `/health/dashboard`, `/api/health/dashboard-data`, `/favicon.ico`, `/`, `/metrics` | `/health`, `/favicon.ico`, `/` |
| Prefix (`_PUBLIC_PREFIXES`) | `/frontend`, `/css`, `/js` | `/frontend`, `/css`, `/js` |
| Auth endpoints (`_PUBLIC_AUTH_PATHS`) | `/auth/register`, `/auth/login`, `/auth/refresh` | `/auth/register`, `/auth/login`, `/auth/refresh` |

Every other route requires a valid Bearer in prod-like mode. `/auth/me` is
deliberately excluded from the public set (`auth.py:390-392`) and is never
reachable without identity.

### Middleware 401 semantics (prod-like; `auth.py:449-471`)

| Condition | Status | Body |
| --- | --- | --- |
| `Authorization` header missing or not starting with `Bearer ` | 401 | `{"error": "Missing or invalid Authorization header"}` |
| Header present but token empty | 401 | `{"error": "Empty token"}` |
| Token invalid, expired, or `type != "access"` | 401 | `{"error": "Invalid or expired token"}` |

Middleware failures use `{"error": ...}`; failures raised by the `/auth/*`
handlers are FastAPI `HTTPException`s and use `{"detail": ...}`. Consumers must
handle both shapes (the web UI reads both: `frontend/js/api.js`).

### POST /auth/register (`auth.py:508-532`) — public

Request body (`UserCreate`, `auth.py:49-76`):

```json
{"username": "string", "email": "string", "password": "string"}
```

| Field | Validation |
| --- | --- |
| `username` | 3-64 characters after strip |
| `email` | must contain `@`; max 120; stripped |
| `password` | at least 8 characters |

| Status | Body | Notes |
| --- | --- | --- |
| 201 | `UserResponse`: `{"id": int, "username": str, "email": str, "created_at": str}` | `created_at` ISO-8601 UTC (`auth.py:86-92`, `527-532`) |
| 403 | `{"detail": "Registration is disabled by the operator"}` | Policy: registration closed in public mode — accounts are operator-provisioned. `SUPEREZIO_PUBLIC_REGISTRATION=1` re-enables (`auth.py:307-312`, `516-519`). Policy documented, not changed. |
| 409 | `{"detail": "Username already exists"}` / `{"detail": "Email already registered"}` / `{"detail": "Registration conflict"}` | `auth.py:182-187` |
| 422 | Pydantic validation errors | |

### POST /auth/login (`auth.py:534-553`) — public

Request body (`LoginRequest`, `auth.py:79-83`):

```json
{"username": "string", "password": "string"}
```

| Status | Body | Notes |
| --- | --- | --- |
| 200 | `TokenResponse`: `{"access_token": str, "refresh_token": str, "token_type": "bearer", "expires_in": 1800}` | `auth.py:95-101`; access token lifetime 30 min (`auth.py:36`) |
| 401 | `{"detail": "Invalid credentials"}` | Unknown username or wrong password (`auth.py:543`, `547`) |
| 500 | `{"detail": "AuthDB not initialized"}` | `auth.py:490` |

### POST /auth/refresh (`auth.py:555-585`) — public

Request body (`TokenRefresh`, `auth.py:104-107`):

```json
{"refresh_token": "string"}
```

Refresh tokens are opaque, single-use `token_urlsafe(48)` strings valid 7 days
(`auth.py:37`, `345-355`) and stored hashed (SHA-256). Every successful refresh
rotates: the presented token is revoked and a fresh pair is returned.

| Status | Body | Notes |
| --- | --- | --- |
| 200 | `TokenResponse` with a NEW `access_token` and a NEW `refresh_token` | Rotation (`auth.py:559-562`, `585`) |
| 401 | `{"detail": "Invalid or expired refresh token"}` | Unknown or expired (`auth.py:568`) |
| 401 | `{"detail": "Refresh token already used"}` | Reuse after rotation — possible theft indicator (`auth.py:570-575`) |
| 401 | `{"detail": "User not found"}` | Owner no longer exists (`auth.py:578-579`) |

### GET /auth/me (`auth.py:587-621`) — never public

Requires a valid Bearer (guest identity in dev/open access).

| Status | Body | Notes |
| --- | --- | --- |
| 200 | `UserResponse`: `{"id", "username", "email", "created_at"}` | DB profile for real users; dev/open-access guests: `{"id": 0, "username": "dev_anon"/"guest_open", "email": "dev@local"/"guest@open", "created_at": ""}` (`auth.py:600-609`) |
| 401 | `{"detail": "Not authenticated"}` | No identity on the request (`auth.py:591-592`) |
| 404 | `{"detail": "User not found"}` | `auth.py:613-614` |
| 500 | `{"detail": "AuthDB not initialized"}` | |

### Token semantics

- Access tokens: JWT HS256 (`auth.py:35`), payload `{"sub": str(user_id), "username": str, "iat": int, "exp": int, "type": "access"}`, lifetime 30 minutes (`auth.py:36`, `333-342`); decode rejects any token with `type != "access"` (`auth.py:363-364`).
- Clients authenticate as `Authorization: Bearer <access_token>` (`frontend/js/auth.js`, `frontend/js/api.js`).
- Refresh tokens: opaque, single-use, 7-day strings, stored as SHA-256 (`auth.py:37`, `345-355`).
- Storage: SQLite `runtime/auth.db` — `users` + `refresh_tokens` tables (`auth.py:137-159`).

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
10. The canonical public-path set for the JWT gate lives only in `src/agent_server/auth.py` (`_PUBLIC_EXACT`, `_PUBLIC_EXACT_TIGHTENED`, `_PUBLIC_PREFIXES`, `_PUBLIC_AUTH_PATHS`); `main.py` must not mirror it.
11. `/auth/me` must never join a public path set; the always-public auth surface is exactly `/auth/register`, `/auth/login`, `/auth/refresh`.
12. Fail-closed: `SUPEREZIO_PUBLIC_MODE=1` with a `SUPEREZIO_JWT_SECRET` shorter than 32 characters must abort server startup (`validate_public_mode_or_raise`, `auth.py:315-330`).

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
python -m pytest tests/test_auth_middleware_prod_matrix.py tests/test_auth_public_paths_contract.py tests/test_credentials_and_bootstrap_contract.py -q
```
