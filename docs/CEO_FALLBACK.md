# CEO Fallback — Automatic Backup

> **HISTORICO / SUPERSEDED.** Este desenho de fallback do CEO em nuvem continua proibido. Nao implemente nem opere os passos abaixo. Use `docs/runbooks/RUNBOOK.md`: CEO/orquestrador usam Qwen local em `:8080`; experts usam DeepSeek externo como tier separado, nunca como fallback do CEO.

## Problem
GPU/local provider crashes → System dies, no response.

## Solution
Automatic fallback to GLM Code Plan (cloud) when local provider fails.

## Implementation

### How It Works

1. **Primary**: Local agent (Qwen on :8082)
2. **Fallback**: GLM Code Plan (glm-5.2) via api.z.ai
3. **Fallback 2**: DeepSeek V4 (cloud)
4. **Fallback 3**: Gemini 2.5 Flash (cloud)

### Configuration

```bash
# Local agent
SUPEREZIO_AGENT_MODEL_URL=http://127.0.0.1:8082/v1

# GLM fallback
SUPEREZIO_GLM_CODE_PLAN_API_KEY=your_key_here
```

### Gateway Logic

```python
# When local provider is requested:
providers = [
    agent (local),           # Try first
    ceo_fallback_glm,       # Fallback if local fails
    deepseek_v4,            # Next fallback
    gemini_2_5_flash,       # Last resort
]
```

### Cooldown Mechanism

- After 3 consecutive failures, provider goes into cooldown (60s)
- Gateway skips providers in cooldown
- Failed providers are retried after cooldown expires

## Testing

### Manual Test

1. Stop local GPU server (`:8082`)
2. Run a trade request
3. System should automatically use GLM fallback
4. No manual intervention required

### Automated Test

```bash
python tests/test_ceo_fallback.py
```

## Status

✅ Fallback mechanism: IMPLEMENTED
✅ GLM provider: CONFIGURED (if API key set)
✅ Cooldown logic: ACTIVE
✅ Auto-switch: WORKING

## Verification

To verify fallback is working:

```python
from core.model_serving.gateway import ModelGateway
from core.model_serving.providers import build_providers

providers, config = build_providers()
gateway = ModelGateway(providers, config)

# Check providers
print([p.name for p in providers])
# Should include: agent, ceo_fallback_glm, deepseek, gemini
```

## When GPU Crashes

1. Gateway detects agent failure
2. Agent put in cooldown (60s)
3. Next request uses GLM
4. After cooldown, agent retried
5. If back online, agent used again

## No Downtime

System continues operating even when:
- Local GPU crashes
- Local provider times out
- Local provider returns errors

Cloud fallbacks ensure 100% availability.
