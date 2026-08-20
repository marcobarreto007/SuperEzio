# SuperEzio - Transfer Checklist

Complete this checklist before delivering the kit to a buyer or evaluator.

## Pre-Packaging Gate

- [ ] Run `git status --short` and document any dirty files.
- [ ] Run `powershell -ExecutionPolicy Bypass -File .\check.ps1` on a stopped system.
- [ ] Run `powershell -ExecutionPolicy Bypass -File .\start.ps1 -SkipBrowser`.
- [ ] Run `.\.venv\Scripts\python.exe -u scripts\browser_smoke.py --skip-chat --timeout-ms 180000`.
- [ ] Run `powershell -ExecutionPolicy Bypass -File .\stop.ps1`.
- [ ] Refresh `.f51/checkpoints/latest.json` with the commands and results.
- [ ] Verify no real secrets are tracked:

```powershell
rg -n "sk-|AIza|hf_|CG-|API[_-]?KEY=.*[A-Za-z0-9]{12}" .
```

## Cleaning Rules

- [ ] Run preview first:

```powershell
powershell -ExecutionPolicy Bypass -File .\clean.ps1 -DryRun
```

- [ ] Run cleanup only on a copied package folder, not on the working source tree:

```powershell
powershell -ExecutionPolicy Bypass -File .\clean.ps1 -Apply
```

- [ ] Use `-RemoveGit` only if the buyer should not receive Git history.
- [ ] Use `-RemoveF51Checkpoints` only if the buyer should not receive internal checkpoints.
- [ ] Keep `.env` out of the package. Include `.env.example`.
- [ ] Keep `.venv\` out of the package. The buyer creates their own environment.
- [ ] Keep `models\*.gguf` out of source-only packages unless the sale explicitly includes the model file.

## Required Package Contents

- [ ] `README_FIRST.md`
- [ ] `config.ps1`
- [ ] `check.ps1`
- [ ] `start.ps1`
- [ ] `stop.ps1`
- [ ] `clean.ps1`
- [ ] `OPEN_UI.url`
- [ ] `.env.example`
- [ ] `pyproject.toml`
- [ ] `requirements.txt`
- [ ] `src\`
- [ ] `frontend\`
- [ ] `tests\`
- [ ] `scripts\`
- [ ] `docs\BUYER_SETUP_GUIDE.md`
- [ ] `docs\ARCHITECTURE_ONEPAGER.md`
- [ ] `docs\RISK_DISCLOSURE.md`
- [ ] `docs\EVIDENCE_INDEX.md`
- [ ] `docs\runbooks\FINAL_PACKAGING_PLAN.md`
- [ ] `docs\internal\audits\frontpage_correspondence_audit_2026-06-03.md`
- [ ] `models\README_MODEL.md`

## Optional Package Contents

- [ ] `output\playwright\superezio-browser-smoke-20260603-101308.png` or a freshly generated replacement screenshot.
- [ ] Latest startup, API, and browser-smoke logs, if they do not contain secrets.
- [ ] Final demo script or video.

## Final Verification On A Clean Machine Or VM

- [ ] ZIP extracts to one folder, for example `C:\SuperEzio`.
- [ ] Buyer follows `README_FIRST.md` and `docs\BUYER_SETUP_GUIDE.md`.
- [ ] `check.ps1` passes on the stopped system.
- [ ] `start.ps1` brings CEO and API healthy.
- [ ] UI opens at `http://127.0.0.1:8002`.
- [ ] One bounded research prompt completes.
- [ ] `stop.ps1` frees ports 8080 and 8002.

## Sign-Off

```text
Date:
Package:
SHA256:
Verified by:
Notes:
```
