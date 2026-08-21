# F51 Release Readiness

Updated: 2026-08-20

## Status

**PASS FOR THE LOCAL WINDOWS RESEARCH COPILOT; INVESTMENT SKILL NOT PROVEN.** The active code, configuration,
launchers, contracts and documentation target the same canonical zero-cloud runtime.
Real-capital execution remains NO-GO. Docker configuration is contract-valid but its image
build/boot still needs a run with Docker Desktop available.

## Canonical Runtime

- Shared local Qwen3.8-27B-Q4_K_M llama-server: `127.0.0.1:8080`.
- FastAPI and browser UI: `127.0.0.1:8002`.
- All LLM roles use the shared local endpoint; no cloud-LLM fallback exists.
- If the local model server is unavailable, the system must enter `MAN_AT_WORK` and block order submission.
- Agent army: 22 versioned agents.
- Test discovery snapshot: 1,885 tests collected on 2026-08-20. Always record the current collection and outcome.

Canonical operational sources: `config/runtime.yml`, `config/model_manifest.json`, and `docs/runbooks/RUNBOOK.md`.

## Required Checks

```powershell
python -m ruff check src/ tests/
python -m ruff format --check src/ tests/
python scripts/check_agents.py
python -m pytest tests/ -q
```

With the local model and API running:

```powershell
curl.exe -fsS http://127.0.0.1:8080/health
curl.exe -fsS http://127.0.0.1:8080/v1/models
curl.exe -fsS http://127.0.0.1:8002/health
curl.exe -fsS http://127.0.0.1:8002/health/details
python scripts/browser_smoke.py
```

Readiness also requires proof that stopping `:8080` produces fail-closed `MAN_AT_WORK` behavior without a cloud-LLM call, followed by successful recovery when the local server returns.

## Sign-off Record

- Date: 2026-08-20 (America/Toronto).
- Source commits: `4013d23..46cd73e` for the multiasset investment-quality correction.
- Static gates: Ruff check PASS; Ruff format PASS (399 files); agent contract PASS
  (22 agents, 32 skills); Docker Compose config PASS.
- Full suite: `1907 passed, 10 skipped` in 551.38 seconds; 66% coverage.
- Live runtime: official isolated launcher; local Qwen3.8-27B on `:8080`; API healthy on
  `:8002`. The former AAPL-only proof has been superseded by the configurable multiasset
  matrix.
- Response-form telemetry now exposes scorer provenance and explicitly states that it does
  not measure investment accuracy. The previous heuristic score 0.87 is not release evidence.
- Real investment gate: 8 assets x 3 horizons, five years of observed data, 24/24 available,
  0/24 models qualified; verdict `INVESTMENT_SKILL_NOT_PROVEN`.
- Real penny backtest: 4 assets x 1,254 candles, next-open causal execution, fees/slippage
  and benchmarks; 0 trades, verdict `NO_TRADE`.
- Browser smoke: PASS; TD.TO returned 123 candles, 7 canvases and zero console errors.
- Validation evidence: `runtime/validation/20260820-150840`.
- Docker limitation: image build/boot NOT RUN because the Docker Desktop daemon was offline.

## Policy

DISK ONLY. Never run `git push`, `git pull`, `git fetch`, or `gh`.
