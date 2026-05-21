# F51 Entrypoint Map

Updated: 2026-05-21T00:00:00-04:00
Session: clean-tree-zero-retired-surface-2026-05-21

## Official Runtime

- API/UI: `python -m agent_server.main`
- CEO model: `powershell -ExecutionPolicy Bypass -File scripts/serve_ceo_llamacpp.ps1 -Port 8082`
- Desktop launcher: `desktop/SuperEzio.bat`

## Operational Endpoints

- `GET /health`
- `GET /health/details`
- `GET /capabilities`
- `GET /product/manifest`
- `POST /task/submit`
- `GET /api/chart-data/{ticker}`
- `GET /api/chart-sse/{ticker}`
