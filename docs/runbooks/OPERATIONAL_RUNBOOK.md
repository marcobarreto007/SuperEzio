# SuperEzio — Runbook Operacional

Atualizado: 2026-08-21

> Este guia curto acompanha o runbook canonico `docs/runbooks/RUNBOOK.md`. Em caso de divergencia, o runbook canonico e `config/runtime.yml` prevalecem.

## Contrato do runtime

| Componente | Bind | Contrato |
|---|---|---|
| llama-server compartilhado | `127.0.0.1:8080` | Ornith-1.0-9B-Q4_K_M na GPU viva (RTX 2070 8GB); atende CEO e orquestrador |
| DeepSeek oficial | `https://api.deepseek.com` | `deepseek-v4-pro`; atende experts financeiros, judge e auditor |
| API + UI | `127.0.0.1:8002` | FastAPI, pipeline, health e cockpit |

Nao existe fallback cruzado: CEO/orquestrador nunca caem para DeepSeek, e experts nunca caem para Qwen. Se o llama-server cair, o sistema deve entrar em `MAN_AT_WORK` e bloquear ordens. Sem `SUPEREZIO_DEEPSEEK_API_KEY`, a API pode manter liveness, mas `/health/details` reporta o tier de experts como indisponivel.

## Iniciar na ordem correta

No diretorio raiz do projeto:

```powershell
# Terminal 1 — modelo local compartilhado
powershell -ExecutionPolicy Bypass -File scripts/serve_agent_llamacpp.ps1 -Port 8080

# Terminal 2 — API e UI, depois que :8080 responder
python -m agent_server.main
```

Antes do boot da API, configure `SUPEREZIO_DEEPSEEK_API_KEY` em `.env.local`.

## Verificar saude

```powershell
curl.exe -fsS http://127.0.0.1:8080/health
curl.exe -fsS http://127.0.0.1:8080/v1/models
curl.exe -fsS http://127.0.0.1:8002/health
curl.exe -fsS http://127.0.0.1:8002/health/details
```

`/v1/models` deve refletir `Ornith-1.0-9B-Q4_K_M`. A UI fica em `http://127.0.0.1:8002`.

## Recuperacao

### Modelo local offline

1. Confirme o dono da porta com `Get-NetTCPConnection -LocalPort 8080 -ErrorAction SilentlyContinue`.
2. Consulte `runtime/logs/` e corrija a causa de boot, GPU ou modelo.
3. Reinicie o launcher local em `:8080`.
4. Confirme `/health` e `/v1/models` antes de testar a API.
5. Nao redirecione o CEO para DeepSeek como contorno.

Enquanto `:8080` estiver offline, `MAN_AT_WORK` e o comportamento seguro esperado.

### GPU morta ou offload na CPU

1. `nvidia-smi -L` — so conta placa **viva**. `Get-PnpDevice -Class Display` mostra a 3060 se ela falhou no Windows.
2. Se `llama-server` estiver com `-ts 8,6` ou `-ts 12,8` e so houver 1 GPU no smi, mate `:8080` via `stop.ps1` e suba `scripts/serve_agent_llamacpp.ps1` (default `-ts auto`).
3. Perfil que cabe na 2070 8GB: `Ornith-1.0-9B-Q4_K_M.gguf`, `-ngl all`, `-c 8192`. Q6_K + ctx 32768 nao cabe.
4. A 3060 em `CM_PROB_FAILED_ADD` e problema de driver/dispositivo, nao de repo. Nao invente split fantasma. Operador: Device Manager → RTX 3060 → uninstall + scan, ou alinhar o driver ao 610.60 da 2070.

### Experts DeepSeek indisponiveis

1. Consulte `/health/details` e o campo `provider_deepseek.status`.
2. Confirme chave local, base `https://api.deepseek.com` e modelo `deepseek-v4-pro` sem imprimir o segredo.
3. Confirme conectividade HTTPS; 401 sem autenticacao prova alcance, nao credencial valida.
4. Nao aponte experts para Qwen. Corrija a credencial/rede e repita o health detalhado.

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

O smoke de browser exige a API em `:8002`; o chat real exige tambem o modelo em `:8080` e o tier DeepSeek configurado. Em 2026-08-21 a suite encontrou 1.975 testes e terminou com 1.965 passed/10 skipped, mas essa e apenas evidencia datada. Registre sempre a contagem e o resultado produzidos pela execucao corrente.

## Politicas obrigatorias

- Topologia hibrida com isolamento fail-closed entre Qwen local e DeepSeek externo.
- Trading real desabilitado; operacao paper exige readiness do broker.
- Segredos somente em arquivos locais ignorados pelo Git.
- Repositorio em modo DISK ONLY: nunca `git push`, `git pull`, `git fetch` ou `gh`.
- Para parar processos, prefira `stop.ps1`; nao mate processos por nome sem confirmar PID e porta.
