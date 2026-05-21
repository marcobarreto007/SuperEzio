# F51 Config Map

Updated: 2026-05-21T20:30:00-04:00
Session: f51-inventory-full-sweep

## Runtime Configuration Files

### 1. `config/runtime.yml`

| Property | Value |
|----------|-------|
| Classification | config |
| Purpose | Canonical runtime configuration |
| Content | Server host/port, model definitions (CEO, orchestrator, experts, fallback), gateway settings, health check URLs, storage paths, launch sequence, test commands |
| Risk | HIGH — changes affect all runtime behavior |

### 2. `config/model_manifest.json`

| Property | Value |
|----------|-------|
| Classification | config |
| Purpose | Model metadata: CEO persona "Bob", quantization Q4_K_M, tool_calling enabled, 12 expert roles |
| Risk | MEDIUM — must match runtime.yml model definitions |

### 3. `config/mandamentos.json`

| Property | Value |
|----------|-------|
| Classification | config |
| Purpose | Operational rules/config loaded into the pipeline |
| Risk | LOW — advisory, not structural |

## Build Configuration

### 4. `pyproject.toml`

| Property | Value |
|----------|-------|
| Classification | config |
| Purpose | Build system (setuptools), dependencies, ruff config, pytest markers, package discovery |
| Key settings | Python >=3.11, line-length 100, lf line endings, 7 pytest packages |
| Risk | HIGH — dependency changes affect runtime |

### 5. `Dockerfile`

| Property | Value |
|----------|-------|
| Classification | config |
| Purpose | Multi-stage build (build -> cpu -> gpu) |
| Version label | 3.0.0 (mismatch with pyproject.toml 4.0.0) |
| Risk | MEDIUM — version label is stale |

### 6. `requirements-ci.txt`

| Property | Value |
|----------|-------|
| Classification | config |
| Purpose | CI dependencies (pytest, ruff, fastapi, data libs) |
| Risk | LOW — CI only |

## Environment Configuration

### 7. `.env.example` / `.env`

| Property | Value |
|----------|-------|
| Classification | config |
| Purpose | 97-line env var template across 7 sections |
| Sections | Pipeline runtime, model serving, data providers, infrastructure, observability, PennyLab rules, miscellaneous |
| Key vars | `SUPEREZIO_CEO_BASE_URL`, `SUPEREZIO_HOST`, `SUPEREZIO_PORT`, `SUPEREZIO_DEEPSEEK_API_KEY` |
| Risk | HIGH — missing keys cause runtime failure |

## CI/CD Configuration

### 8. `.github/workflows/ci.yml`

| Property | Value |
|----------|-------|
| Classification | config |
| Purpose | GitHub Actions CI |
| Runner | windows-2022, Python 3.12 |
| Steps | Install deps -> ruff lint tests/ -> ruff format tests/ -> pytest |
| Risk | MEDIUM — does not lint src/ |

### 9. `Makefile`

| Property | Value |
|----------|-------|
| Classification | config |
| Purpose | Local dev targets: install-deps, test, test-windows, verify |
| Risk | LOW — convenience only |

## Policy Configuration

### 10. `.f51/GITHUB_POLICY.json`

| Property | Value |
|----------|-------|
| Classification | config |
| Purpose | Hard-blocks all GitHub operations (DISK ONLY mode) |
| Risk | HIGH — must never be removed without explicit Marco checkpoint |

### 11. `pytest.ini` (embedded in pyproject.toml)

| Property | Value |
|----------|-------|
| Classification | config |
| Purpose | pytest config: minversion 8.0, asyncio_mode auto, markers |
| Risk | LOW |

## IDE Configuration

### 12. `.vscode/settings.json`

| Property | Value |
|----------|-------|
| Classification | config |
| Purpose | VS Code workspace settings |
| Risk | LOW |

### 13. `.vscode/extensions.json`

| Property | Value |
|----------|-------|
| Classification | config |
| Purpose | Recommended extensions |
| Risk | LOW |

## F51 Operational Config

### 14. `.f51/checkpoints/latest.json`

| Property | Value |
|----------|-------|
| Classification | config |
| Purpose | Last checkpoint state |
| Status | Completed (Agentic_Pipeline_Refactor) |
| Risk | MEDIUM — next_step unconfirmed |

### 15. `.f51/INVENTORY_TEMPLATE.json`

| Property | Value |
|----------|-------|
| Classification | config |
| Purpose | Template for inventory generation |
| Risk | LOW |

## Data Configuration

### 16. `data/macro_dataset/dataset_index.json`

| Property | Value |
|----------|-------|
| Classification | config |
| Purpose | Index of macro parquet datasets (Canada credit, debt, GDP, policy rate) |
| Risk | LOW |

### 17. `data/fraud_patterns/fraud_patterns.json`

| Property | Value |
|----------|-------|
| Classification | config |
| Purpose | Fraud pattern definitions for RAG |
| Risk | LOW |

### 18. `data/fraud_patterns/red_flag_rules.json`

| Property | Value |
|----------|-------|
| Classification | config |
| Purpose | Red flag detection rules |
| Risk | LOW |

## Config Inconsistencies

| Issue | Detail | Severity |
|-------|--------|----------|
| Dockerfile version | Label says 3.0.0, pyproject.toml says 4.0.0 | LOW |
| CI scope | CI only lints/tests tests/, not src/ | MEDIUM |
| Black vs Ruff | Makefile runs both, CI only ruff | LOW |
| Nurse model | .env.example references SUPEREZIO_NURSE_MODEL and SUPEREZIO_NURSE_LORA_PATH but no nurse code found in src/ | UNKNOWN |
