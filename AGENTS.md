# AGENTS — SuperEzio Agent Army (Playbook 2026)

Porta curta para agentes. Regras completas em `CLAUDE.md`.
Orquestração detalhada em `docs/AGENT_ORCHESTRATION.md`.

## REGRA CRÍTICA: GITHUB BLOQUEADO

Fonte: `.f51/GITHUB_POLICY.json`. Modo **DISK ONLY**.
- NUNCA `git push`, `git pull`, `git fetch`, `gh`
- Commits locais OBRIGATÓRIOS após cada mudança mínima

## Exército Ativo (10 agentes)

| Agente | Classe | Missão |
|--------|--------|--------|
| `recon-researcher` | Researcher | Mapeia arquitetura, órfãos, código morto |
| `security-reviewer` | Verifier | Audita segredos, env vars, superfície de ataque |
| `code-quality-reviewer` | Verifier | Lint, imports quebrados, código comentado |
| `runtime-verifier` | Verifier | Portas, GPU, modelo, health checks |
| `training-verifier` | Verifier | Scripts, datasets, checkpoints, modelos |
| `api-contract-verifier` | Verifier | Endpoints, schemas, breaking changes |
| `frontend-ux-reviewer` | Verifier | Smoke test, UI funcional |
| `model-gateway-verifier` | Verifier | Provider cascade, latência, fallback |
| `agent-explorer` | Explorer | Avalia qualidade dos agentes, propõe substituições |
| `savekeeper` | Savekeeper | Salva docs, checkpoint, changelog |

## Comandos

| Comando | Descrição |
|---------|-----------|
| `/swarm <objetivo>` | Dispara exército completo |
| `/save` | Salva estado + commit local |
| `/agent-lab` | Testa e evolui agentes |

## F51 Skills (22 skills)

Mantidas em `.claude/skills/`. Skills nucleares: inventory, contracts, runtime, refactor, tests, audit, release, money-gate.

## Regras de Ouro

- Um agente = uma missão
- Toda afirmação precisa de evidência (arquivo:linha ou comando)
- Verifier não é o mesmo que escreveu
- Savekeeper não salva segredo
- Explorer mata agente ruim
- Checkpoint obrigatório em `.f51/checkpoints/latest.json`

## Gates

```powershell
git status --short
python -m ruff check src/ tests/
python -m pytest tests/ -q
python scripts/browser_smoke.py
```

## Política de MCPs

MCPs permitidos: filesystem, playwright, firebase, context7, ide.
Playwright OBRIGATÓRIO com pytest. GitHub BLOQUEADO.
