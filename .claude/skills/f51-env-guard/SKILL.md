---
name: f51-env-guard
description: "Valida todas as variáveis de ambiente com Pydantic Settings schema. Detecta typos, missing vars, e valores inseguros antes do boot. Triggers: env, environment, settings, pydantic-settings, config, dotenv, variáveis de ambiente, freeze."
compatibility: "SuperEzio bootstrap layer"
allowed-tools: "Read, Edit, Write, Bash, Grep, Diff"
depends-on: [f51-contracts, f51-runtime]
related-skills: [f51-safety-science, f51-circuit-breaker]
---

# f51-env-guard

## Quando usar

- Variáveis de ambiente são lidas com `os.getenv` sem validação de schema
- Um typo em env var de segurança (ex: `F51_TRADING_EXECUTION_FREEZE`) pode desligar proteção
- Bootstrap do sistema falha silenciosamente por env var ausente
- Precisa documentar quais env vars existem, seus defaults, e seus riscos

## Nunca fazer

- Hardcodar secrets no schema (usar `SecretStr`)
- Validar env var e não avisar quando valor é inseguro
- Deixar env var sem default documentado
- Criar schema que não corresponde ao comportamento real do código

## Workflow

1. **Auditar env vars atuais**: `grep -rn "os.getenv\|os.environ" src/` — listar todas.
2. **Classificar por criticalidade**: `CRITICAL` (security/finance), `HIGH` (connectivity), `MEDIUM` (behavior), `LOW` (cosmetic).
3. **Criar `src/core/config/settings.py`**: classe `Settings(BaseSettings)` com todas as env vars tipadas, defaults seguros, e validações.
4. **Substituir `os.getenv` por `settings.X`** nos módulos críticos: `f51_trade_gate.py`, `auto_execute_paper.py`, `main.py`.
5. **Adicionar validação de boot**: `Settings()` no startup do sistema — se falhar, NÃO sobe.
6. **Atualizar `.env.example`** com todas as vars documentadas.
7. **Rodar teste**: desligar FREEZE por typo → sistema deve rejeitar.

## Portões de decisão

- Se env var CRITICAL não tem validação explícita: bloqueado.
- Se default é inseguro (ex: FREEZE=false por padrão): bloqueado — deve ser `true`.
- Se schema não corresponde a pelo menos 95% dos `os.getenv` encontrados: revisar.

## Schema mínimo

```python
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field, SecretStr


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="forbid",  # rejeita env vars não declaradas
    )

    # ── Security (CRITICAL) ──
    f51_trading_execution_freeze: bool = Field(
        default=True,
        description="Global kill switch. TRUE = ALL orders blocked. NEVER set to false in production.",
    )
    superezio_enable_paper_order_submit: bool = Field(
        default=False, description="Enable paper order submission to IBKR TWS."
    )

    # ── Connectivity (HIGH) ──
    ibkr_host: str = Field(default="127.0.0.1")
    ibkr_port: int = Field(default=7497, ge=1024, le=65535)

    # ── Behavior (MEDIUM) ──
    universal_skip_gateway: bool = Field(default=False)
    superezio_bob_sovereign: bool = Field(default=False)
```

## Entregáveis mínimos

```
== F51 ENV GUARD REPORT ==

## Env vars auditadas
- Total encontradas: N
- CRITICAL: N | HIGH: N | MEDIUM: N | LOW: N

## Schema criado
- Arquivo: src/core/config/settings.py
- Cobertura: X% das env vars encontradas

## Substituições
- [arquivo]: [N os.getenv → settings.X]

## Validação de boot
- [Settings() no startup]: [PASS / FAIL]

## .env.example
- [atualizado / pendente]

## Checkpoint
- Atualizado em `.f51/checkpoints/latest.json`
```

## Regras

- FREEZE padrão é SEMPRE `true`.
- Env var nova sem documentação = bloqueada.
- `extra="forbid"` é obrigatório — typo em env var deve crashar, não ignorar.
- Secrets usam `SecretStr` — nunca aparecem em logs.
