# Save — Persist Verified Truth

Goal: Save current project state to durable documentation.

## What Gets Saved
- `CLAUDE.md` / `AGENTS.md` — if rules changed
- `.f51/checkpoints/latest.json` — always
- `.f51/TASK_BOARD.md` — if tasks progressed
- `.f51/RISK_REGISTER.md` — if risks changed
- `docs/` — consolidated findings from agent reports

## Pre-Save Gates
1. [ ] Changes validated by at least one verifier agent
2. [ ] No secrets in content (scan: api_key, token, password, cert)
3. [ ] Tests passing or blockers documented
4. [ ] Risk register current
5. [ ] Checkpoint template filled

## Save Procedure
1. Run `git status --short` to see all changes
2. Review each change against gates
3. Update `.f51/checkpoints/latest.json`
4. Update affected docs
5. Report what was saved and why

## Never Save
- Secrets, keys, tokens, .env values
- Raw photos, private images
- Model files, GGUF, safetensors
- Raw datasets (.jsonl, .parquet)
- Runtime logs with tokens
- Temporary agent memory
