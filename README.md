# SuperEzio

SuperEzio is a trading system and investment assistant for asset analysis, charts, portfolio monitoring, and risk-aware decisions. Its deterministic modules collect evidence, calculate mathematical signals, enforce risk invariants, record outcomes, and adjust future behavior. Language models are assistants: they interpret, debate, and explain, but they do not own the execution truth and cannot bypass the deterministic policy.

Version boundary: the installable package and public API currently report `4.0.0`; the independently versioned local runtime and model manifest are `4.2.0`. These identifiers describe different contracts and are not interchangeable.

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

SuperEzio operates a 22-agent army defined in `.claude/agents/` and orchestrated via the `CLAUDE.md` playbook. Agents are specialized for delivery, recon, verification, security, contract validation, runtime checks, code quality, UX review, benchmarking, domain knowledge, release readiness, and durable state. The army runs in waves via `/swarm`, persists state through `/save`, and self-evolves via `/agent-lab`.

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
- External model APIs configured in `config/runtime.yml` power the cognitive layers: if API keys or remote endpoints are unavailable, the organism enters `MAN_AT_WORK` and blocks orders. No local LLM server (`:8080`) is required for operation.

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

Python 3.11 or newer is required. On Windows, use the locked bootstrap and
provide a unique first-operator password through the current process:

```powershell
$env:SUPEREZIO_ADMIN_PASSWORD = "replace-with-a-unique-long-password"
.\setup_superezio.bat
```

The bootstrap installs `requirements-lock.txt`, creates `.env.local`, generates
a JWT secret and installs Playwright Chromium. Never commit or distribute secrets.

## Running

The official launcher starts the SuperEzio API and trading workspace:

```powershell
.\setup_superezio.bat run
```

Open `http://127.0.0.1:8002`. No local model server or GPU is required for cloud
inference. Configure `SUPEREZIO_DEEPSEEK_API_KEY` in the ignored local `.env.local`.
The canonical defaults in `config/runtime.yml` use `deepseek-v4-pro` for the
assistant/orchestrator and `deepseek-v4-flash` for experts, judge and auditor,
at `https://api.deepseek.com`. Provider outages and missing configuration must
be treated as unavailable analysis, never successful analysis or order approval.

See [README_FIRST.md](README_FIRST.md) for the client workflow.

## Authentication

SuperEzio uses JWT authentication with bcrypt password hashing and refresh-token rotation.

- **`/auth/register`** — create a new user account (username, email, password)
- **`/auth/login`** — authenticate and receive an access + refresh token pair
- **`/auth/refresh`** — rotate a refresh token (single-use)
- **`/auth/me`** — return the authenticated user's profile

The Windows bootstrap generates `SUPEREZIO_JWT_SECRET` in `.env.local`. A
secret is required for the deliverable product; anonymous mode is development-only.

```ini
SUPEREZIO_JWT_SECRET=your-strong-random-secret-here
```

### Seeding the first admin

```powershell
$env:SUPEREZIO_ADMIN_PASSWORD = "replace-with-a-unique-long-password"
python scripts/seed_admin.py --username admin --email admin@superezio.com
```

The password is read from `SUPEREZIO_ADMIN_PASSWORD`; it is not accepted on the
command line. The script can also read `SUPEREZIO_ADMIN_USERNAME` and
`SUPEREZIO_ADMIN_EMAIL`.

## Verification

```powershell
python -m ruff check src/ tests/
python -m ruff format --check src/ tests/
python -m pytest tests/ -q
python scripts/browser_smoke.py
```

The browser smoke requires the API on port `8002` and valid external model and
market-data access. Use the current test output as delivery evidence; historical
test counts do not establish readiness. Live-service tests may skip when their
prerequisites are absent, and those skips must be reported separately.

## Safety and repository policy

- Paper/research mode is the default operating posture.
- Do not infer market truth from generated prose; use the structured evidence ledger.
- Do not learn from pending orders or duplicate terminal events.
- Do not use production fallbacks with fabricated market data.
- This repository is operated in disk-only mode: no `git push`, `git pull`, `git fetch`, or GitHub CLI operations.

## Deployment scope

The supported client entrypoint is the Windows launcher above. The existing
Docker deployment files require a separate compatibility review before use with
the cloud runtime; they are not evidence of a verified client installation.

## License

MIT License with attribution. See [LICENSE](LICENSE).
