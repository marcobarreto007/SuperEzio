# Livro-razão de sinais — SuperEzio

Versão da política: **v1** (`official_signal_policy.v1.json`)

Objetivo: transformar cada run do pipeline (`POST /task/submit`, NDJSON) em registro **auditável** para uso próprio e, depois, venda de sinais com track record forward.

Não altera `src/` até você congelar a regra de negócio.

---

## Arquivos no disco

| Caminho | Conteúdo |
|---------|----------|
| `data/signals/emitted.jsonl` | Um JSON por linha: sinal emitido ou candidato rejeitado |
| `data/signals/resolutions.jsonl` | Resultado T+N por `signal_id` |
| `data/signals/raw_ndjson/{run_id}.ndjson` | Cópia opcional do stream bruto (auditoria) |
| `docs/signals/signal_ledger.schema.json` | JSON Schema (`signal_emit`, `signal_resolution`) |
| `docs/signals/official_signal_policy.v1.json` | Regras versionadas de elegibilidade |

---

## Tipos de registro

### `signal_emit`

Gravado ao final de cada análise processada pelo script `append_from_ndjson.py`.

- `status: "official"` — passou na política v1; conta no track record público.
- `status: "watchlist"` — passou parcialmente (ex.: SDCA `REVIEW`); não vender como sinal “oficial” até política v2.
- `status: "rejected"` — candidato com motivos (`reject_reasons[]`); mantém prova de que o sistema **não** vendeu hype.

### `signal_resolution`

Gravado por `resolve_signals.py` quando o horizonte vence (ex.: 5 dias úteis após `reference_ts`).

Campos: `return_pct`, `direction_hit`, `max_adverse_pct` (drawdown do período contra a posição).

---

## Mapeamento NDJSON → ledger

Eventos que o coletor entende (stream `/task/submit`):

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

## Comandos

```powershell
# 1) Gravar emit a partir de NDJSON capturado (curl /task/submit, log do painel, etc.)
python scripts/signal_ledger/append_from_ndjson.py data/signals/inbox/run.ndjson

# Dry-run (não grava)
python scripts/signal_ledger/append_from_ndjson.py data/signals/inbox/run.ndjson --dry-run

# 2) Resolver sinais official abertos (CSV ticker,date,close ou --manual-price AAPL=310)
python scripts/signal_ledger/resolve_signals.py --prices-csv data/signals/prices.csv
python scripts/signal_ledger/resolve_signals.py --manual-price AAPL=310.5 --horizon 5d

# 3) Relatório
python scripts/signal_ledger/report_signals.py
python scripts/signal_ledger/report_signals.py --json
```

Variáveis úteis: `PYTHONPATH=src` se algum import de paths do projeto for necessário; os scripts usam stdlib + pydantic já no projeto.

---

## Próximo passo (produto, não obrigatório agora)

- Hook opcional em `agent_server` para append automático pós-stream (1 chamada ao módulo `scripts/signal_ledger`).
- UI Bob: aba “Track record” lendo `emitted.jsonl` + `resolutions.jsonl`.
- Política v2: universo penny-only, spread mínimo, volume mínimo.

---

## Venda de sinais (checklist antes de cobrar)

- [ ] ≥ 100 sinais `official` com resolução 5d/20d
- [ ] Relatório exportável (CSV + equity curve)
- [ ] Política v1 congelada + `policy_version` em cada linha
- [ ] Disclaimer + consulta jurídica (BR / CVM se aplicável)
- [ ] Canal (Telegram) posta o mesmo `signal_id` que está no JSONL (prova anti-edição)
