# SuperEzio — Runbook Operacional

Atualizado: 2026-08-20

> Este guia curto acompanha o runbook canonico `docs/runbooks/RUNBOOK.md`. Em caso de divergencia, o runbook canonico e `config/runtime.yml` prevalecem.

## Contrato do runtime

| Componente | Bind | Contrato |
|---|---|---|
| llama-server compartilhado | `127.0.0.1:8080` | Qwen3.8-27B-Q4_K_M; atende CEO, orquestrador, experts, judge e auditor |
| API + UI | `127.0.0.1:8002` | FastAPI, pipeline, health e cockpit |

Todos os papeis LLM usam o endpoint local em `:8080`. Nao existe fallback para LLM em nuvem. Se o llama-server cair, o sistema deve entrar em `MAN_AT_WORK` e bloquear ordens.

## Iniciar na ordem correta

No diretorio raiz do projeto:

```powershell
# Terminal 1 — modelo local compartilhado
powershell -ExecutionPolicy Bypass -File scripts/serve_agent_llamacpp.ps1 -Port 8080

# Terminal 2 — API e UI, depois que :8080 responder
python -m agent_server.main
```

## Verificar saude

```powershell
curl.exe -fsS http://127.0.0.1:8080/health
curl.exe -fsS http://127.0.0.1:8080/v1/models
curl.exe -fsS http://127.0.0.1:8002/health
curl.exe -fsS http://127.0.0.1:8002/health/details
```

`/v1/models` deve refletir `Qwen3.8-27B-Q4_K_M`, conforme `config/model_manifest.json`. A UI fica em `http://127.0.0.1:8002`.

## Recuperacao

### Modelo local offline

1. Confirme o dono da porta com `Get-NetTCPConnection -LocalPort 8080 -ErrorAction SilentlyContinue`.
2. Consulte `runtime/logs/` e corrija a causa de boot, GPU ou modelo.
3. Reinicie o launcher local em `:8080`.
4. Confirme `/health` e `/v1/models` antes de testar a API.
5. Nao configure provider de LLM em nuvem como contorno.

Enquanto `:8080` estiver offline, `MAN_AT_WORK` e o comportamento seguro esperado.

### API ou UI offline

1. Confirme o dono da porta com `Get-NetTCPConnection -LocalPort 8002 -ErrorAction SilentlyContinue`.
2. Consulte `runtime/logs/`.
3. Reinicie `python -m agent_server.main` somente depois de o modelo local estar saudavel.
4. Valide `/health`, `/health/details` e a UI.

### IBKR offline

O broker permanece paper-only. Abra TWS/IB Gateway paper em `127.0.0.1:7497`, valide a configuracao de API e execute a probe documentada no runbook canonico. Nunca troque para a porta live `7496` durante recuperacao.

## Gates antes de declarar pronto

```powershell
python -m ruff check src/ tests/
python -m ruff format --check src/ tests/
python scripts/check_agents.py
python -m pytest tests/ -q
python scripts/browser_smoke.py
```

O smoke de browser exige a API em `:8002`; o chat real exige tambem o modelo em `:8080`. Em 2026-08-20 a coleta encontrou 1.885 testes, mas essa e apenas evidencia datada. Registre sempre a contagem e o resultado produzidos pela execucao corrente.

## Politicas obrigatorias

- Runtime LLM zero-cloud e fail-closed.
- Trading real desabilitado; operacao paper exige readiness do broker.
- Segredos somente em arquivos locais ignorados pelo Git.
- Repositorio em modo DISK ONLY: nunca `git push`, `git pull`, `git fetch` ou `gh`.
- Para parar processos, prefira `stop.ps1`; nao mate processos por nome sem confirmar PID e porta.
