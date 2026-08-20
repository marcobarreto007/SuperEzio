# SuperEzio E2E Delivery Gate - 2026-05-13

> **HISTORICO / SUPERSEDED.** Evidencia de entrega de 2026-05-13. Nao use como runbook atual; consulte `docs/runbooks/RUNBOOK.md`.

## Scope

Delivery validation for local client handoff on Windows:

- Python quality gates.
- Public contract import.
- Real FastAPI server on `127.0.0.1:8012`.
- API smoke through HTTP.
- Browser flow through Playwright CLI.
- Edge gateway auth/rate behavior on isolated server `127.0.0.1:8013`.

## Commands Run

```powershell
python -m ruff check src tests
python -m ruff format --check src tests
python -m pytest tests/ -q --tb=short
python -c "from f51 import F51Engine, Graph, Node, Context, NodeResult; print('contract ok')"
npx --yes --package @playwright/cli playwright-cli ...
```

## Results

- `ruff check`: passed.
- `ruff format --check`: passed, 177 files already formatted.
- `pytest`: 348 passed, 2 warnings, 206.82s.
- Public `f51` import contract: passed.
- `/health`: 200.
- `/`: 200 HTML.
- `/health/details`: 200.
- `/metrics`: 200 when auth disabled.
- `/capabilities`: 200.
- `/product/manifest`: 200.
- `/api/chart-data/AAPL?timeframe=1M`: 200 with OHLCV payload.
- `/task/submit` vague financial prompt: completed stream and returned `STUDY_MORE` guardrail.
- `/task/submit` lowercase ticker `analise tsla`: completed stream, emitted `CHART_DATA` for `TSLA`, 0 `ERROR` events, 1 CEO `MODEL_MISSING`, 5 explanation chunks, 0 duplicate explanation chunks.
- Frontend browser E2E: loaded `AAPL` chart, completed Decision Desk stream, showed `F51 PASS`, enabled Save to Journal, and hid internal duplicate-skip events from the visible log.
- Gateway auth E2E: `/health` public without key, `/metrics` 401 without key, `/metrics` 200 with `X-API-Key`, `/task/submit` 401 without key.
- Gateway rate E2E: burst requests returned 429 after the limit.

## Known Environment Limits

- Local Sensei CEO on port `8082` was offline during this gate. The system degraded correctly with one `MODEL_MISSING` event and an operator action hint.
- External expert/model providers were not configured for this local run, so expert calls may fail/degrade while the stream still completes.
- Chart data uses live `yfinance`; this gate passed with network available.
- `pyright` is not installed in this environment.
- Pytest emitted 2 dependency warnings from `google._upb` for future Python 3.14 behavior.

## Fixes Landed During Gate

- Made CEO and explanation stream nodes idempotent so graph fan-in cannot duplicate visible answer/explanation text.
- Hid internal duplicate-skip pipeline events from the customer-facing frontend event log.
- Corrected EdgeGateway burst/rate limit status mapping from 400 to 429.
- Added unit tests for duplicate stream guards and EdgeGateway burst status.

## Next Safest Patch

Run the same E2E gate with the local CEO service/API keys configured, then capture a production-mode smoke with `SUPEREZIO_EDGE_AUTH=1`, real API keys, and representative customer tickers.
