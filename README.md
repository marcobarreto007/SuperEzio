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
| `src/data` | Routed market-data acquisition and payload validation |
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

## Verification

```powershell
python -m ruff check src/ tests/
python -m ruff format --check src/ tests/
python -m pytest tests/ -q
python scripts/browser_smoke.py
```

The browser smoke requires the API on port `8002`. Its chat step may use the configured model-provider cascade. Tests that require live services are marked `integration` and skip when those services are absent.

## Safety and repository policy

- Paper/research mode is the default operating posture.
- Do not infer market truth from generated prose; use the structured evidence ledger.
- Do not learn from pending orders or duplicate terminal events.
- Do not use production fallbacks with fabricated market data.
- This repository is operated in disk-only mode: no `git push`, `git pull`, `git fetch`, or GitHub CLI operations.

## License

MIT License with attribution. See [LICENSE](LICENSE).
