# Plano de Deploy Público — supereziorealtime.com (Cloudflare)

Consolidado de 3 especialistas em paralelo (security-reviewer, reliability-sre-operator,
product-delivery-orchestrator) em 2026-08-22. DISK ONLY — nada de GitHub.

## Veredito

**NO-GO hoje.** A API roda em dev mode (JWT fail-open), /auth/register é público,
não há rate limit no app, e /health/details + /metrics* expõem infra interna.
**GO condicional** após os gates abaixo — todos verificáveis com curl.

## Fase 1 — Auth local (Gate A — hard gate, destrava o resto)

1. `SUPEREZIO_JWT_SECRET` forte (>=32 chars, `secrets.token_hex(32)`) em `.env.local` (gitignored) — OPERADOR gera.
2. Boot fail-closed em modo público: sem secret >=32 chars → processo não sobe (exit != 0).
3. `/auth/register` → 403 em modo público (contas só via `scripts/create_operator_user.py` — OPERADOR define a senha).
4. Conjunto público reduzido por env (`SUPEREZIO_PUBLIC_MODE`): remover `/metrics*`, `/health/dashboard*` do público.
5. Login como tela inicial (modal já existe no frontend; Bearer já implementado em api.js).
6. Aceite: G1 `/cockpit/summary` sem token → 401; G2 login → 200 + cockpit com Bearer → 200;
   G3 boot sem secret falha; G4 register → 403; G5 `/auth/me` anônimo → 401; G6 browser: modal → login → cockpit.
7. Testes: `tests/test_auth_public_gate.py` novo + pytest + ruff + browser smoke.

## Fase 2 — Túnel Cloudflare (Gate B — gate humano: credencial do operador)

- `winget install Cloudflare.cloudflared` (GitHub bloqueado → winget).
- OPERADOR: `cloudflared tunnel login` (browser no dashboard dele).
- `cloudflared tunnel create superezio` → config.yml com ingress ÚNICO: `supereziorealtime.com → http://127.0.0.1:8002` + catch-all 404. **NUNCA :8080.**
- Prova negativa: `https://supereziorealtime.com:8080` não responde.

## Fase 3 — DNS + verificação (Gate C)

- OPERADOR no dashboard: CNAME `@` → `<UUID>.cfargotunnel.com`, Proxy ON (orange cloud).
- Smoke público: todas as rotas sensíveis → 401 sem token; `/health` 200; login+UI via HTTPS;
  scan de secrets nas respostas (zero); `trading_frozen=true`; 24h de janela com chat BLOQUEADO.

## Fase 4 — Chat DeepSeek público: **DEFER** (gasta tokens pagos — GO só com teto aprovado pelo operador + rate limit edge).

## Rollback (< 5 min)

DNS → remover CNAME / restaurar snapshot; `cloudflared service uninstall` + `tunnel delete`;
JWT permanece ativo (nunca reverter para dev mode após exposição).

## Stop conditions (rollback imediato)

Rota protegida 200 anônima · secret vazado · :8080 acessível pelo hostname · custo DeepSeek não aprovado.

## Checklist de segurança (D1) — resumo

JWT fail-closed · register fechado · rate limit WAF por IP (o do app é bypassável por session_id) ·
HTTPS strict + HSTS · CSP com nonce (dashboard usa inline JS) · Cache-Control no-store para /api/* ·
nunca expor /health/details, /neural/logs, /evidence/*, /bob/ibkr/recover, /trade/*, /paper/* · CORS explícito.

## Fontes

- Audit D1 (security-reviewer): checklist 12 pontos, NO-GO com evidência arquivo:linha
- Runbook D2 (SRE): 4 fases com comandos exatos + critérios de aceite + rollback
- Slice D3 (orchestrator): G1-G13 mensuráveis, owners de arquivo, GO/DEFER/NO-GO por fase
