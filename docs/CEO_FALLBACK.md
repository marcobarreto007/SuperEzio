# CEO Fallback — Automatic Backup (desenho antigo — SUPERSEDED)

> **HISTORICO / SUPERSEDED — nao implemente nem opere.** Este documento descreve um desenho antigo de fallback do CEO (Qwen local em `:8082` -> GLM Code Plan -> DeepSeek -> Gemini) que **nao** corresponde ao runtime atual. Nao ha mais modelo local no caminho de resposta. Estado atual: todos os papeis — Bob/CEO, orquestrador, experts, judge e auditor — rodam `deepseek-v4-flash` na API oficial `https://api.deepseek.com`; o caminho Z.ai GLM-5.3 e opcional e so e construido quando `SUPEREZIO_GLM_CODING_PLAN_API_KEY` existe. Fonte canonica: `docs/runbooks/RUNBOOK.md`.

## Problem
GPU/local provider crashes → System dies, no response. (Historico: nao ha GPU nem provider local no caminho de resposta.)

## Solution
Automatic fallback to GLM Code Plan (cloud) when local provider fails. (Desenho antigo; nao vigente.)

## Implementation

### How It Works (desenho antigo, preservado como registro)

1. **Primary (historico)**: Local agent (Qwen on :8082)
2. **Fallback (historico)**: GLM Code Plan (glm-5.2) via api.z.ai
3. **Fallback 2 (historico)**: DeepSeek V4 (cloud)
4. **Fallback 3 (historico)**: Gemini 2.5 Flash (cloud)

Nenhum provider `ceo_fallback_glm` ou `gemini`, nem os modelos `glm-5.2` / `gemini-2.5`, existem no codigo atual (`src/core/model_serving/providers.py`).

### Configuration (historico)

```bash
# Desenho antigo — nao usar.
SUPEREZIO_AGENT_MODEL_URL=http://127.0.0.1:8082/v1

# O nome vigente da chave e SUPEREZIO_GLM_CODING_PLAN_API_KEY ("CODING",
# nao "CODE_PLAN"). Re-arme atual do GLM-5.3: defina a chave e aponte o papel
# com SUPEREZIO_PRIMARY_MODEL=glm-5.3 (orquestrador) e/ou
# SUPEREZIO_AGENT_MODEL=glm-5.3 (Bob/CEO).
SUPEREZIO_GLM_CODING_PLAN_API_KEY=your_key_here
```

### Gateway Logic (historico — nao existe em `src/`)

```python
# Registro do desenho antigo; nao use como contrato.
providers = [
    agent(local),  # Try first
    ceo_fallback_glm,  # Fallback if local fails
    deepseek_v4,  # Next fallback
    gemini_2_5_flash,  # Last resort
]
```

### Cooldown Mechanism (historico)

- After 3 consecutive failures, provider goes into cooldown (60s)
- Gateway skips providers in cooldown
- Failed providers are retried after cooldown expires

## Testing

### Manual Test (nao executar — desenho antigo)

1. Stop local GPU server (`:8082`) — nao existe no runtime atual
2. Run a trade request
3. System should automatically use GLM fallback
4. No manual intervention required

### Automated Test

```bash
python tests/test_ceo_fallback.py
```

Historico: nao use este documento como contrato do comportamento atual; valide o escopo do arquivo de teste antes de cita-lo.

## Status (superado — nao usar como estado atual)

- Nao existe fallback automatico CEO local -> GLM: nao ha modelo local no caminho de resposta.
- O provider `glm` e opcional: so e construido quando `SUPEREZIO_GLM_CODING_PLAN_API_KEY` esta presente.
- O fallback por credito GLM -> DeepSeek para Bob (`SUPEREZIO_GLM_FALLBACK_TO_DEEPSEEK`, default ligado) so age quando o caminho GLM esta armado.
- Sem o caminho GLM armado, uma indisponibilidade do DeepSeek nao tem tier alternativo: a falha e tratada como analise indisponivel, nunca como aprovacao de ordem.

## Verification

Para listar os providers vigentes:

```python
from core.model_serving.gateway import ModelGateway
from core.model_serving.providers import build_providers

providers, config = build_providers()
gateway = ModelGateway(providers, config)

# Check providers
print([p.name for p in providers])
# Esperado hoje (sem a chave GLM): local_orchestrator, deepseek, daytrade_judge, daytrade_auditor, agent
# O provider `glm` so aparece quando SUPEREZIO_GLM_CODING_PLAN_API_KEY esta presente.
```

## When GPU Crashes (historico)

Nao se aplica ao runtime atual: nao ha GPU no caminho de resposta.

## No Downtime

Nenhum desenho de fallback garante 100% de disponibilidade. No runtime atual, sem o caminho GLM armado, a indisponibilidade do DeepSeek nao tem fallback; a falha e tratada como analise indisponivel, nunca como aprovacao de ordem.
