# Checkpoint — SuperEzio scan / DataHub (pré-reinício)

**Data (local):** 2026-05-22  
**Sessão:** Market scan US/Canada + Finnhub primary + fallbacks + Twelve Data test  
**Status:** `in_progress` — código salvo no disco; **reiniciar PC e API** antes de considerar fechado  
**Projeto:** `C:\Users\marco\Desktop\SuperEzio`  
**Owner:** Marco  

---

## Objetivo da sessão

Corrigir o scan genérico **2 semanas US/Canada** (`US_CANADA_LIQUID`) que rejeitava **100%** dos candidatos com `missing_price` / `no_provider_result_for_price`.

**Aceite alvo:**

- `hub.get_price("AAPL")` retorna preço numérico.
- Scan com no máximo **24** tickers; rejeições **mistas** (tese/liquidez), não só preço.
- **Finnhub** primário; **Twelve Data** → **yfinance** → **Stooq** como fallbacks.

---

## O que está salvo no disco (resumo)

### Pipeline / scan

| Arquivo | Alteração |
|---------|-----------|
| `src/core/pipeline/graph.py` | `orchestrator_primary → data → agent` (collector antes do CEO) |
| `src/core/pipeline/nodes/agent.py` | Resposta determinística de `market_scan` antes do CEO; relatório Bob 8 seções |
| `src/core/pipeline/nodes/collector.py` | Quotas scan: 12/país, max 24 total, price enrich 24, profile/catalyst 12, concurrency 2; telemetria `price_provider` / `price_attempts_sample`; `load_local_env()`; fix `scan_max_total` fora do `try` do scanner |

### DataHub / providers

| Arquivo | Alteração |
|---------|-----------|
| `src/data/data_hub.py` | Prioridade: finnhub (1) → twelve_data (12) → yfinance (30) → stooq (45); `load_local_env()`; `_kwargs_for_method()` (sem `market=` em providers incompatíveis) |
| `src/data/finnhub_provider.py` | Rate limit, variantes de símbolo, candles/news |
| `src/data/finnhub_symbols.py` | Normalização BRK-B / `.TO` / Canada |
| `src/data/yfinance_provider.py` | **NOVO** — fallback sem chave |
| `src/data/stooq_provider.py` | Fallback keyless |
| `src/data/twelve_data.py` | Inalterado na lógica; usado como fallback com chave |

### Config / operador

| Arquivo | Alteração |
|---------|-----------|
| `.env` | `FINNHUB_API_KEY` e `TWELVE_DATA_API_KEY` (gitignored — **não commitar**) |
| `.env.example` | Cadeia de providers + `SUPEREZIO_SCAN_*` + `FINNHUB_MIN_INTERVAL_SEC` |
| `pyproject.toml` | `yfinance>=0.2` |
| `desktop/SuperEzio.bat` | Carrega `.env` / `.env.local` |
| `DELIVERY.md` | §2.3 graph, §2.4 DataHub/Finnhub |

### Scripts de verificação

| Script | Uso |
|--------|-----|
| `scripts/smoke_datahub_price.py` | AAPL + `list_active()` / `price_routes` |
| `scripts/smoke_twelve_data.py` | Twelve direto + hub; grava `runtime/smoke_twelve_data_result.json` |
| `runtime/do_restart.ps1` | Reinicia API CEO 8082 / API 8002 |

### Testes (pytest, sem rede)

- `tests/test_finnhub_symbols.py`
- `tests/test_finnhub_provider.py`
- `tests/test_stooq_provider.py`
- `tests/test_data_hub_routing.py`
- `tests/test_market_scan_candidate_gate.py`

---

## Variáveis de ambiente (scan — defaults atuais)

```env
SUPEREZIO_SCAN_LIMIT=12
SUPEREZIO_SCAN_MAX_TOTAL=24
SUPEREZIO_SCAN_ENRICH=12
SUPEREZIO_SCAN_PRICE_ENRICH=24
SUPEREZIO_SCAN_ENRICH_CONCURRENCY=2
FINNHUB_MIN_INTERVAL_SEC=1.05
```

---

## Testes feitos nesta sessão (evidência)

### Finnhub (conversa anterior + chave no `.env`)

- Quote AAPL via API: **OK** (~309).

### Twelve Data — teste ao vivo (2026-05-22)

Plano **Basic B** — limite **8 créditos/minuto** (dashboard mostrou pico 26/8).

| Símbolo | Resultado |
|---------|-----------|
| AAPL, MSFT, SPY, SHOP | OK (preço numérico) |
| RY (TSX) | 404 — exige plano Grow/Venture |
| BRK/B | 404 — símbolo inválido |
| BRK.B (após várias calls) | 429 — estourou 8/min |

**Conclusão Twelve:** serve para **US pontual**, **não** como fallback em massa no scan de 24 tickers. Canadá no Basic B: usar Finnhub/yfinance, não Twelve.

### Smoke local (terminal do agente)

- Comandos `python scripts/smoke_*.py` **não retornaram saída** no ambiente do agente (0 ms) — **Marco deve rodar após reinício**.

---

## Pendente após reiniciar o PC

1. Abrir PowerShell:

```powershell
cd C:\Users\marco\Desktop\SuperEzio
pip install yfinance
python scripts/smoke_datahub_price.py
python scripts/smoke_twelve_data.py
type runtime\smoke_twelve_data_result.json
.\runtime\do_restart.ps1
```

2. No CEO (`http://127.0.0.1:8082`), repetir:

   *"What stock would you recommend if I want to profit within the next 2 weeks?"*

3. No trace, confirmar:

   - `scanner_invoked: true`
   - `candidate_count` ≤ 24
   - `price_provider:` **não** `no_provider_result_for_price=60`
   - Rejeições mistas se houver candidatos sem tese/liquidez

4. Se ainda 100% `missing_price`:

   - API antiga ainda rodando → `do_restart.ps1` de novo
   - Colar `price_attempts_sample` e `price_routes_active` do trace

---

## Melhorias opcionais (não implementadas)

- Throttle Twelve Data (~8/min) + variantes `BRK.B` no `twelve_data.py`
- Pular Twelve para `market=Canada` / `.TO` no Basic B
- Endpoint `/api/data/health` com diagnóstico AAPL

---

## Segurança

- Chaves Finnhub e Twelve Data apareceram em chat/screenshot — **rotacionar** nos painéis dos provedores após estabilizar o scan.
- **Nunca** `git add .env` nem commitar chaves.

---

## Portas / atalhos

| Serviço | Porta |
|---------|-------|
| API | 8002 |
| CEO UI | 8082 |
| Launcher | `desktop\SuperEzio.bat` |

---

## Próximo passo (uma linha)

Reiniciar PC → `do_restart.ps1` → smoke AAPL → rerun prompt 2 semanas → validar trace ≠ 100% `missing_price`.

---

*Checkpoint gerado antes do reinício solicitado pelo operador.*
