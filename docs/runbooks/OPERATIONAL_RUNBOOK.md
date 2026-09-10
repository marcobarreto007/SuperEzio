# SuperEzio — Runbook Operacional

Atualizado: 2026-08-21

> Este guia curto acompanha o runbook canonico `docs/runbooks/RUNBOOK.md`. Em caso de divergencia, o runbook canonico e `config/runtime.yml` prevalecem.

## Contrato do runtime

| Componente | Bind | Contrato |
|---|---|---|
| DeepSeek oficial | `https://api.deepseek.com` | `deepseek-v4-flash`; atende TODOS os papeis — Bob CEO, orquestrador, experts financeiros, judge e auditor |
| Z.ai Coding Plan (opcional) | `https://api.z.ai` | `glm-5.3`; caminho opcional, so existe com `SUPEREZIO_GLM_CODING_PLAN_API_KEY` e falha fechado sem ela |
| API + UI | `127.0.0.1:8002` | FastAPI, pipeline, health e cockpit |

Se `SUPEREZIO_DEEPSEEK_API_KEY` nao estiver configurada em `.env.local`, a API mantém liveness em `:8002`, mas `/health/details` reporta o tier de modelos como indisponível e o sistema entra em fail-closed `MAN_AT_WORK`. A chave GLM nao e pre-requisito de boot.

## Iniciar na ordem correta

No diretório raiz do projeto:

```powershell
$env:PYTHONPATH = "src;$env:PYTHONPATH"
python -m agent_server.main
```

Antes do boot da API, configure APENAS `SUPEREZIO_DEEPSEEK_API_KEY` em `.env.local`. `SUPEREZIO_GLM_CODING_PLAN_API_KEY` nao e pre-requisito de boot: ela apenas habilita o caminho opcional Z.ai/GLM.

## Verificar saude

```powershell
curl.exe -fsS http://127.0.0.1:8002/health
curl.exe -fsS http://127.0.0.1:8002/health/details
```

A UI fica em `http://127.0.0.1:8002`. O cockpit exibe os cards de telemetria, gráficos e chat.

## Recuperacao

### Provedor em nuvem offline ou chave ausente

1. Confirme conectividade de rede com `https://api.deepseek.com` (e, somente se o caminho opcional estiver habilitado, `https://api.z.ai`).
2. Verifique se `SUPEREZIO_DEEPSEEK_API_KEY` está presente em `.env.local` — e a unica chave exigida; a chave GLM so habilita o caminho opcional.
3. Consulte `/health/details` na seção `checks.providers_summary`.
4. Enquanto as chaves forem inválidas ou a conexão externa falhar, `MAN_AT_WORK` é o comportamento seguro esperado.

### Experts DeepSeek indisponiveis

1. Consulte `/health/details` e o campo `provider_deepseek.status`.
2. Confirme chave local, base `https://api.deepseek.com` e modelo `deepseek-v4-flash` sem imprimir o segredo.
3. Confirme conectividade HTTPS; 401 sem autenticacao prova alcance, nao credencial valida.
4. Nao aponte experts para Qwen. Corrija a credencial/rede e repita o health detalhado.

### API ou UI offline

1. Confirme o dono da porta com `Get-NetTCPConnection -LocalPort 8002 -ErrorAction SilentlyContinue`.
2. Consulte `runtime/logs/`.
3. Reinicie a API (`python -m agent_server.main`) somente apos confirmar que a chave/SDK do provider em nuvem esta saudavel.
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

O smoke de browser exige a API em `:8002`; o chat real exige tambem o tier DeepSeek configurado (`deepseek-v4-flash`) — nao ha modelo local no caminho de resposta. Em 2026-08-21 a suite encontrou 1.975 testes e terminou com 1.965 passed/10 skipped, mas essa e apenas evidencia datada. Registre sempre a contagem e o resultado produzidos pela execucao corrente.

## Politicas obrigatorias

- Topologia DeepSeek-only (todos os papeis em `deepseek-v4-flash`, API HTTPS oficial) com fail-closed: chave ausente ou provider inalcancavel → `MAN_AT_WORK`. O caminho Z.ai/GLM e opcional e tambem falha fechado.
- Trading real desabilitado; operacao paper exige readiness do broker.
- Segredos somente em arquivos locais ignorados pelo Git.
- Repositorio em modo DISK ONLY: nunca `git push`, `git pull`, `git fetch` ou `gh`.
- Para parar processos, prefira `stop.ps1`; nao mate processos por nome sem confirmar PID e porta.
