# SuperEzio - Evidence Index

This index separates verified evidence from claims that still need a fresh proof run before sale.

## Current Source Of Truth

| Evidence | Location | Status |
|----------|----------|--------|
| Packaging checkpoint | `.f51/checkpoints/latest.json` | Current local checkpoint |
| Packaging commit | `fd8429e chore(packaging): harden portable buyer kit` | Local commit, no GitHub push |
| Frontpage audit | `docs/internal/audits/frontpage_correspondence_audit_2026-06-03.md` | Current UI correspondence audit |
| Final packaging plan | `docs/runbooks/FINAL_PACKAGING_PLAN.md` | Current packaging gate |
| Browser smoke screenshot | `output/playwright/superezio-browser-smoke-20260603-101308.png` | Exists locally, generated output |

## Verified In The Latest Packaging Checkpoint

These results are recorded in `.f51/checkpoints/latest.json` and should be refreshed before a buyer handoff:

| Command Or Probe | Recorded Result |
|------------------|-----------------|
| `git diff --check` | Passed |
| PowerShell parser checks | `config.ps1`, `check.ps1`, `start.ps1`, and `scripts/serve_agent_llamacpp.ps1` parse OK |
| `config.ps1` live probe | Python `.venv`, `C:\llama.cpp\build-cuda\bin\llama-server.exe`, model present, ports free |
| `powershell -File .\check.ps1` | 16 passed, 0 warnings, 0 failed |
| `powershell -File .\start.ps1 -SkipBrowser` | CEO healthy on 8082; API healthy on 8002 |
| `python -u scripts\browser_smoke.py --skip-chat --timeout-ms 180000` | OK; AAPL chart 130 candles; canvas nonblank; console errors empty |
| `powershell -File .\stop.ps1` | Stopped official CEO/API processes; ports 8082 and 8002 free |

## Refresh Commands Before Sale

Run these on the exact machine or package copy being handed off:

```powershell
powershell -ExecutionPolicy Bypass -File .\check.ps1
powershell -ExecutionPolicy Bypass -File .\start.ps1 -SkipBrowser
.\.venv\Scripts\python.exe -u scripts\browser_smoke.py --skip-chat --timeout-ms 180000
powershell -ExecutionPolicy Bypass -File .\stop.ps1
```

For deeper technical diligence:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\contracts -q
.\.venv\Scripts\python.exe -m pytest tests\test_runtime_smoke.py -q
.\.venv\Scripts\python.exe -m ruff check src tests
.\.venv\Scripts\python.exe -m ruff format --check src tests
```

Do not mark those deeper suites as current evidence unless they were run during the packaging pass.

## Evidence Still Needed For A Buyer Listing

| Item | Status |
|------|--------|
| Clean-machine transfer rehearsal | Pending |
| Full chat browser smoke on the final package copy | Pending |
| Fresh contract/ruff evidence for the final ZIP | Pending |
| Demo video or live demo script proof | Pending |
| SHA256 checksum for final ZIP | Pending |
| Legal review of financial-disclaimer language | Pending |

## Evidence Rules

- Link every commercial claim to a command, log, screenshot, checkpoint, or audit file.
- Do not list screenshots that are not present in the package or reproducible from a command.
- Do not claim full pytest/ruff pass unless it was run in the current packaging pass.
- Keep generated logs and screenshots out of the source commit unless explicitly selected for the buyer bundle.
