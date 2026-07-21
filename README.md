# SuperEzio

SuperEzio is an adaptive financial-analysis organism. Its deterministic modules collect evidence, calculate mathematical signals, enforce risk invariants, record outcomes, and adjust future behavior. Language models are assistants: they interpret, debate, and explain, but they do not own the execution truth and cannot bypass the deterministic policy.

## Operating model

```text
past outcomes + current market evidence
                  |
                  v
        data validation and math
                  |
                  v
       deterministic expert consensus
                  |
                  v
     risk, sizing, freeze, and evidence gates
                  |
          BLOCK / PAPER ORDER
                  |
                  v
       terminal outcome ledger (exactly once)
                  |
                  v
      expert weights and policy adaptation
```

The feedback loop learns only from terminal outcomes. An order submission is not treated as success. Rewards are tied to the risk known at decision time, including transaction friction, and each terminal event has an immutable idempotency key.

## Agent army

SuperEzio operates a 14-agent army defined in `.claude/agents/` and orchestrated via the CLAUDE.md playbook. Agents are specialized for recon, verification, security, contract validation, runtime checks, code quality, UX review, benchmarking, and domain knowledge. The army runs in waves via `/swarm`, persists state through `/save`, and self-evolves via `/agent-lab`.

## Mangala Engine

The Mangala Engine (`src/core/pipeline/nodes/mangala.py`) is a multi-agent simulation layer that drives consensus, crisis detection, and adaptive trading signals. It polls expert outputs, runs deterministic risk invariants, and feeds results into the execution policy. The Mangala Tracker (`src/core/pipeline/nodes/mangala_tracker.py`) records terminal outcomes and adjusts strategy weights accordingly.

## Current invariants

- Crisis scores use one canonical `[0, 1]` scale.
- Provider payloads must satisfy capability-specific validation before they are accepted.
- Every paper-order path passes through the shared adaptive execution policy.
- Learned consensus can block an order; an LLM recommendation cannot override it.
- Position size and stop distance remain bounded by deterministic risk rules.
- Security claims must cite structured evidence for the same symbol and price.
- RAG persistence uses checksummed generations and never loads NumPy pickle data.
- Durable files use same-directory temporary writes followed by atomic replacement.
- Live execution is fail-safe disabled unless the explicit safety configuration allows it.
- The local CEO/model process is optional for core containment: if it is unavailable, the organism enters diagnostic mode and blocks orders.

The detailed July 2026 verification is in [docs/audit/phase10_organism_truth_and_remediation_2026-07-19.md](docs/audit/phase10_organism_truth_and_remediation_2026-07-19.md).

## Architecture

| Area | Primary responsibility |
|---|---|
| `src/core/math` | Deterministic calculations and crisis integration |
| `src/data` | Routed market-data acquisition and payload validation via DataHub (15 providers, capability-based routing with fallback chain) |
| `src/core/pipeline/nodes/mangala.py` | Mangala Engine — multi-agent simulation for consensus, crisis detection, and adaptive trading signals |
| `src/core/pipeline/nodes/mangala_tracker.py` | Mangala Tracker — outcome-ledger integration and strategy adaptation |
| `src/experts` | Domain signals and crisis ensemble |
| `src/core/pipeline` | Intent, orchestration, evidence, tools, and response flow |
| `src/core/trading` | Journal, outcome learning, XP, rewards, and execution policy |
| `src/core/evidence` | Structured grounding and auditable run evidence |
| `src/core/rag` | Verified retrieval persistence |
| `src/agent_server` | FastAPI runtime and browser-facing endpoints |
| `frontend` | Cockpit, charts, diagnostics, and chat |

## Installation

Python 3.11 or newer is required.

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -e .
python -m playwright install chromium
```

Configuration is read from environment variables. Copy `.env.example` only if you need a local configuration file. Never commit secrets.

## Running

The API and cockpit run on `127.0.0.1:8002` by default:

```powershell
python -m agent_server.main
```

Then open `http://127.0.0.1:8002`.

The optional local model gateway runs on port `8082`:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/serve_agent_llamacpp.ps1 -Port 8082
```

If the package has not been installed in editable mode, use this development-only launch:

```powershell
$env:PYTHONPATH = "src"
python -m agent_server.main
```

## Authentication

SuperEzio uses JWT authentication with bcrypt password hashing and refresh-token rotation.

- **`/auth/register`** — create a new user account (username, email, password)
- **`/auth/login`** — authenticate and receive an access + refresh token pair
- **`/auth/refresh`** — rotate a refresh token (single-use)
- **`/auth/me`** — return the authenticated user's profile

When `SUPEREZIO_JWT_SECRET` is not configured the server runs in **dev mode** and injects an anonymous user for all non-public routes.  In production, set a strong secret via `.env.local`:

```ini
SUPEREZIO_JWT_SECRET=your-strong-random-secret-here
```

### Seeding the first admin

```powershell
python scripts/seed_admin.py --username admin --email admin@superezio.com --password StrongPass123!
```

The script accepts `--db-path` to point to a custom location and falls back to environment variables `SUPEREZIO_ADMIN_USERNAME`, `SUPEREZIO_ADMIN_EMAIL`, and `SUPEREZIO_ADMIN_PASSWORD`.

## Verification

```powershell
python -m ruff check src/ tests/
python -m ruff format --check src/ tests/
python -m pytest tests/ -q
python scripts/browser_smoke.py
```

The browser smoke requires the API on port `8002`. A full run executes **1,611 tests** (collected July 2026). Its chat step may use the configured model-provider cascade. Tests that require live services are marked `integration` and skip when those services are absent.

## Safety and repository policy

- Paper/research mode is the default operating posture.
- Do not infer market truth from generated prose; use the structured evidence ledger.
- Do not learn from pending orders or duplicate terminal events.
- Do not use production fallbacks with fabricated market data.
- This repository is operated in disk-only mode: no `git push`, `git pull`, `git fetch`, or GitHub CLI operations.

## Docker Quick Start

```powershell
docker compose up -d                                  # Start all services (bob-ceo, api-server, watchdog)
docker compose logs -f                                # Tail logs from all services
docker compose ps                                     # Check health status of each service
docker compose exec api-server python -m pytest -q    # Run tests inside the api container
docker compose down -v                                # Stop and remove volumes (caution: deletes data)
```

See `docker-compose.yml` for service topology, networks, and healthcheck configuration.

## License

MIT License with attribution. See [LICENSE](LICENSE).
