# Livro-razão de sinais — SuperEzio

Versão da política: **v1** (`official_signal_policy.v1.json`)

Objetivo: transformar cada run do pipeline (`POST /task/submit`, NDJSON) em registro **auditável** para uso próprio e, depois, venda de sinais com track record forward.

Não altera `src/` até você congelar a regra de negócio.

---

## Arquivos

O diretório `data/signals/` ainda não existe. Os três primeiros caminhos abaixo são **planejados** (destinos futuros, não dados existentes); somente os dois últimos já existem no repositório.

| Caminho | Conteúdo | Estado |
|---------|----------|--------|
| `data/signals/emitted.jsonl` | Um JSON por linha: sinal emitido ou candidato rejeitado | Planejado — não existe |
| `data/signals/resolutions.jsonl` | Resultado T+N por `signal_id` | Planejado — não existe |
| `data/signals/raw_ndjson/{run_id}.ndjson` | Cópia opcional do stream bruto (auditoria) | Planejado — não existe |
| `docs/signals/signal_ledger.schema.json` | JSON Schema (`signal_emit`, `signal_resolution`) | Existe |
| `docs/signals/official_signal_policy.v1.json` | Regras versionadas de elegibilidade | Existe |

---

## Tipos de registro

### `signal_emit`

Planejado: será gravado ao final de cada análise quando um writer append-only for implementado (o script `append_from_ndjson.py` jamais existiu no repositório).

- `status: "official"` — passou na política v1; conta no track record público.
- `status: "watchlist"` — passou parcialmente (ex.: SDCA `REVIEW`); não vender como sinal “oficial” até política v2.
- `status: "rejected"` — candidato com motivos (`reject_reasons[]`); mantém prova de que o sistema **não** vendeu hype.

### `signal_resolution`

Planejado: será gravado por um resolvedor quando o horizonte vencer (ex.: 5 dias úteis após `reference_ts`); o `resolve_signals.py` citado em versões antigas jamais existiu no repositório.

Campos: `return_pct`, `direction_hit`, `max_adverse_pct` (drawdown do período contra a posição).

---

## Mapeamento NDJSON → ledger

Eventos que o coletor deverá entender quando implementado (stream `/task/submit`):

| `type` | Uso no ledger |
|--------|----------------|
| `STREAM_START` | `msg_id`, início do run |
| `CHART_DATA` | confirma `ticker` |
| `INTENT_CLASSIFIED` | `route`, `intent`, `ticker` |
| `DATA_COLLECTED` | `data_quality`, link `analysis_id` → `data/traces/{analysis_id}.json` |
| `F51_VERDICT` | `f51_passed`, `f51_confidence`, fatores |
| `NEURAL_DECISION` | direção, `veto`, `regime`, `recommendation` |
| `SDCA_FIREWALL` | `decision` ALLOW / REVIEW / BLOCK |
| `CRISIS_MATH` | opcional, `systemic_risk` |
| `PIPELINE_STEP` | apenas progresso (ignorado no emit) |
| `CHUNK` | texto CEO (hash + primeiros 500 chars; **não** parsear BUY/SELL do texto na v1) |
| `ERROR` | `status=rejected`, motivo erro |

**Regra v1:** ação do sinal vem só de campos estruturados (`NEURAL_DECISION` + `F51_VERDICT`), não do prose do CEO.

---

## Política “sinal oficial” (v1)

Resumo; fonte: `official_signal_policy.v1.json`.

1. `route == ticker_analysis` e `ticker` válido (1–10 chars, alfanumérico).
2. `sdca_firewall.decision == ALLOW` → `official`. `REVIEW` → `watchlist`. `BLOCK` → `rejected`.
3. `f51_verdict.passed == true` e `confidence >= 0.55`.
4. `neural_decision.veto == false`.
5. `data_quality` ∉ `error`, `timeout`, `unavailable` (quando presente).
6. Direção: `direction_prob >= 0.55` → `LONG`; `<= 0.45` → `SHORT`; senão `HOLD` (oficial só se política `allow_hold: false` → v1 **não** emite oficial em HOLD; vai `watchlist`).

Horizonte padrão de resolução: **5d** (`resolution_horizon: "5d"`).

Preço de referência: **close do dia UTC** em `reference_ts` (ajustável na política).

---

## Estado executável

Este documento define somente schema e política. Os antigos comandos
`scripts/signal_ledger/*` foram removidos porque os scripts nunca existiram no repositório e
não havia caller de produto. Até uma implementação testada ser adicionada, o Signal Ledger
não deve ser apresentado como trilha de performance ativa nem usado para decisões financeiras.

---

## Próximo passo (produto, não obrigatório agora)

- Implementar primeiro um writer append-only testado e só então ligar um hook pós-stream.
- UI Bob: aba “Track record” lendo `emitted.jsonl` + `resolutions.jsonl`.
- Política v2: universo penny-only, spread mínimo, volume mínimo.

---

## Venda de sinais (checklist antes de cobrar)

- [ ] ≥ 100 sinais `official` com resolução 5d/20d
- [ ] Relatório exportável (CSV + equity curve)
- [ ] Política v1 congelada + `policy_version` em cada linha
- [ ] Disclaimer + consulta jurídica (BR / CVM se aplicável)
- [ ] Canal (Telegram) posta o mesmo `signal_id` que está no JSONL (prova anti-edição)
