# Avaliação de Qualidade — 4 Agentes em Paralelo (2026-08-21)

Escopo: sistema VIVO (llama-server :8080 UD-IQ2_XXS + API :8002) + scripts de serving.
Metodologia: 4 lentes independentes, somente leitura, sem chamadas pagas DeepSeek,
redact de segredos obrigatório. Confirmação do operador (Claude): teste de regressão
reproduzido em primeira mão.

## Vereditos por agente

| Agente | Veredito | Essência |
|---|---|---|
| model-gateway-verifier | 3 PASS + 1 parcial | Serving saudável, 19.9 tok/s decode, 4/4 respostas PT, args do processo == script, MAN_AT_WORK coerente com contrato |
| code-quality-reviewer | 1 CRÍTICO + 2 ALTO + achados | EAP clobber por dot-source; pin set incompleto (judge/auditor); dead code (Gemini/a2a); loop de retry triplicado; smoke com falsos positivos possíveis |
| runtime-verifier | Runtime saudável, divergências | CEO+API 200, 0 erros críticos, 2 processos canônicos sem zumbis; RUNBOOK stale; provider_agent.model stale; gpu.available falso-negativo |
| ai-eval-verifier | BLOCK (1 regressão real) | 51/52 testes passam; test_cockpit_summary falha: cockpit reporta Q4_K_M vs contrato UD-IQ2_XXS; TTFT ~2.6s; chart-data 8–9s; language drift explicado (system prompt EN) |

## Consenso central (achado convergente de 3+ agentes)

**DRIFT-1 — modelo reportado ≠ modelo servido.** O commit 03d7fd7 (switch canônico
para UD-IQ2_XXS) ficou incompleto: `.env:11` (SUPEREZIO_AGENT_MODEL=Q4_K_M),
`src/agent_server/endpoints.py:468` e `src/core/config/schema.py:168` (defaults stale)
fazem o cockpit e o `/health/details` anunciarem Q4_K_M enquanto o servidor real serve
UD-IQ2_XXS e os contratos de teste exigem UD-IQ2_XXS.

- Reproduzido: `PYTHONPATH=src python -m pytest tests/test_api_routes_sync.py -q --no-cov`
  → `1 failed (test_cockpit_summary), 51 passed` — AssertionError em
  `tests/test_api_routes_sync.py:516` (`+ Qwen3.8-27B-Q4_K_M`).
- Impacto: rótulo de proveniência falso em auditorias; regressão de contrato público.
- Correção mínima: alinhar defaults de código + `.env` ao canonical UD-IQ2_XXS.

## Métricas medidas (agentes, sistema vivo)

| Métrica | Valor | Fonte |
|---|---|---|
| Decode steady | 20.37 tok/s (19.9–20.4 entre agentes) | gw-verifier / eval-verifier |
| TTFT streaming | 0.102 s | gw-verifier |
| TTFT (urllib, uso real) | 2.58–2.60 s | eval-verifier (ressalva vs claim 0.354s) |
| GET /health :8002 p50 | 0.212 s (curl) | eval-verifier |
| localhost vs 127.0.0.1 | +2.04s por resolução ::1 no python | eval-verifier |
| /api/chart-data/TD.TO | 7.65–9.01 s sem cache | eval-verifier (gargalo de experiência) |
| VRAM | 9092/12288 MiB, GPU única, sem CPU offload | runtime-verifier |
| Erros críticos em 48min de log | 0 | runtime-verifier |
| Respostas PT no modelo cru | 4/4 | gw-verifier |
| Regressão | 1 falha real (test_cockpit_summary) | eval-verifier + confirmação direta |

## Language drift (explicado)

O modelo cru responde em PORTUGUÊS a prompts PT (4/4). A resposta em inglês do smoke
(2626 chars) vem do system prompt em INGLÊS do pipeline:
`src/core/pipeline/prompts/builder.py:473` e `src/core/pipeline/prompts/_prompts.py:4,56`
("You are Bob, SuperEzio's autonomous financial agent..."). Falha de produto para
usuário PT, não do modelo.

## Riscos priorizados (consolidados)

1. CRÍTICO — `serve_agent_llamacpp.ps1:14` define `$ErrorActionPreference="Stop"`, mas
   o dot-source de `config.ps1:3` redefine `"Continue"` → fail-fast silenciosamente
   desligado; config.ps1 também muta `$env:PYTHONPATH` do caller.
2. ALTO — Pin set do gateway (`gateway.py:138-141`) fixa só {agent, deepseek};
   `daytrade_judge`/`daytrade_auditor` não pinados → com allow_fallback default True,
   fallback transiente trocaria evidência DeepSeek por Qwen local (contradiz
   "No cross-provider fallback"). Hoje mitigado só pelo caller expert_dialogue.py:227.
3. ALTO — DRIFT-1 (ver consenso central).
4. MÉDIO — `_providers_for_request(None)` (gateway.py:152-157) monta fila genérica que
   inclui DeepSeek/judge/auditor → chamadas genéricas (ex.: postmortem) gastam tokens
   externos sem arbitragem.
5. MÉDIO — Triplicação do loop retry/circuito/cooldown (generate/stream_generate/
   stream_generate_async) com divergências já existentes (raise vs yield "[ERROR]").
6. MÉDIO — Smoke valida só "resposta não-vazia": não detecta idioma, modelo errado
   (DRIFT-1), canvas em branco (`_assert_canvas_nonblank` não lê pixels), candle velho,
   console_errors coletados mas nunca assertados; cache (.env:29) pode mascarar
   regressão de inferência.
7. MÉDIO — `latest_alert.txt` não registra o clear do MAN_AT_WORK (só estado em memória)
   → quem lê o arquivo vê gate ativo indevidamente.
8. BAIXO — Dead code: `set_deepseek_provider`, Gemini (constantes + `_apply_gemini_options`
   no-op), `generate_a2a_remote` inalcançável, `warmup()`/`unload_all()` no-op.
9. BAIXO — Docs/comentários stale citando Q4_K_M (RUNBOOK.md, serve script:2,104-105,
   manifest:25); manifest version "4.2.0" vs health "4.0.0".
10. BAIXO — `gpu.available=false` no /health/details é falso-negativo (faltam pynvml/
    torch-CUDA no probe); `providers.py:332` int(getenv) sem guarda pode crashar o build.

## Próximos passos sugeridos (para gate/orquestrador, não executados aqui)

- Correção mínima da regressão de contrato (DRIFT-1): defaults em endpoints.py:468,
  schema.py:168 + .env — depois re-executar test_api_routes_sync.py.
- Tarefa refactor (f51-refactor): EAP/dot-source, pin set completo, deduplicar loop de
  retry, remover dead code.
- Tarefa de teste (f51-tests): smoke com asserções de idioma, proveniência do modelo,
  frescor de candles e console_errors.
- Runtime/doc-sync: RUNBOOK.md, comentários do serve script, registro de clear do
  MAN_AT_WORK no arquivo.
- Investigar chart-data 8–9s (cache?) e penalidade localhost/::1 no cliente python.

## Evidência

- Confirmação direta do operador: `test_cockpit_summary` FAILED (15.13s, 1 failed,
  6 passed) — erro exato `- Qwen3.8-27B-UD-IQ2_XXS / + Qwen3.8-27B-Q4_K_M`.
- Relatórios completos dos 4 agentes no checkpoint latest.json
  (`quality_eval_4_agents_20260821`).
