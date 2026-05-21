# F51 Release Readiness

Updated: 2026-05-21T00:00:00-04:00

## Status

Local runtime tree is clean and uses the merged GGUF CEO model as the production artifact.

## Required Checks

- JSON validation for `.f51` and runtime checkpoints.
- Ruff lint and format check.
- Pytest suite.
- CEO model health and natural-language response check.
- API stream check through `/task/submit`.

## Policy

Disk only. No GitHub operations.
