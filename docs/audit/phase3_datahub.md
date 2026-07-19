# Fase 3 — Auditoria do DataHub (infraestrutura de roteamento)

Gerado: 2026-07-19
Escopo: `src/data/data_hub.py`
Método: leitura direta de código. Sem chamadas de rede.

## 1. CONFIRMED — dict vazio `{}` é tratado como resultado utilizável

`DataHub._is_usable_result` (linha 482-490):

```python
@staticmethod
def _is_usable_result(result: Any) -> bool:
    if result is None:
        return False
    if isinstance(result, dict):
        return "error" not in result
    if isinstance(result, list):
        return len(result) > 0
    return True
```

- Para `dict`: a única checagem é ausência da chave `"error"`. Um dicionário vazio `{}` não contém `"error"`, então `_is_usable_result({})` → `True`.
- Consequência direta em `route()` (linha 427-466): se um provider retorna `{}`, o hub aceita esse resultado como sucesso, faz `result.setdefault("provider", route.name)` (deixando o dict com só `{"provider": "..."}`), **retorna imediatamente** e não tenta o próximo provider na cadeia de prioridade.
- Isso é diferente do tratamento de `list`, que corretamente exige `len(result) > 0`.
- Verdict: **CONFIRMED por leitura direta do código**, linha exata. Não encontrei nenhum provider em `src/data/*.py` que hoje retorne literalmente `{}` via `grep` de `return {}` — mas isso não neutraliza o risco: qualquer provider que construa um dict a partir de uma resposta de API vazia (ex: JSON `{}` de um endpoint que não encontrou o ticker) cai nesse buraco sem qualquer proteção estrutural. É uma falha de robustez do hub, não dos providers individuais.
- Classe: INFRAESTRUTURA. Severidade: MÉDIA-ALTA (silencioso, difícil de detectar em produção — o sintoma seria "dados ausentes mas sem erro reportado").
- Correção sugerida (não aplicada nesta fase, é feature/fix — fora do escopo de auditoria): `isinstance(result, dict) and "error" not in result and bool(result)`.

## 2. Cadeia de prioridade de market data — como documentado

Confirmado por leitura direta (linhas 160-336), ordem real de tentativa por `priority` (menor primeiro):

| Priority | Provider | Capabilities | Precisa de key |
|---|---|---|---|
| 1 | finnhub | price, market_price, quote, profile, fundamentals, short_term_catalyst, candles, news | `FINNHUB_API_KEY` |
| 12 | twelve_data | price, market_price, candles | `TWELVE_DATA_API_KEY` |
| 15 | newsapi | news, sentiment, market_sentiment | `NEWSAPI_KEY` |
| 20 | reddit_pulse | reddit, social_sentiment | nenhuma |
| 20 | boc_macro | macro, macro_ca | nenhuma |
| 22 | news_scout | news, sentiment | nenhuma |
| 25 | alpha_vantage | treasury | `ALPHA_VANTAGE_API_KEY` |
| 30 | yfinance | price, market_price, candles, profile | nenhuma |
| 30 | fed_macro | macro, macro_us | nenhuma |
| 30 | wolfram | quantitative, math_verify | `WOLFRAM_API_KEY` |
| 45 | stooq | price, market_price | nenhuma |
| 50 | quantum | quantum | nenhuma |

Isso bate com a descrição da conversa anterior (Finnhub → Twelve Data → yfinance → Stooq para preço). **Confirmado, não é invenção da transcrição.**

## 3. `resolve()` já filtra por `_is_configured` — correto

- `resolve()` (linha 419-425) só retorna rotas onde `_is_configured(route)` é `True` — ou seja, se a chave obrigatória não estiver setada, a rota nem entra na lista de tentativa. Isso é comportamento correto e evita erro de credencial ausente sendo contado como "tentativa falha" nos `attempts`.
- **Mas**: se NENHUMA rota para a capability estiver configurada (ex: nenhuma key de mercado setada), `route()` retorna `{"error": "no_provider_result_for_{capability}", "attempts": []}` — lista de tentativas vazia, o que é o comportamento correto mas pode confundir debug (parece "não tentei nada" quando na real "não havia nada configurado para tentar").

## 4. `_kwargs_for_method` — filtragem de kwargs por assinatura, correto

- Usa `inspect.signature` para descartar kwargs que o método do provider não aceita, exceto se o método tiver `**kwargs`. Comportamento defensivo correto, sem achado de risco.

## 5. `search_web` / `extract_web` — dependência de processo externo Node.js

- `search_web` chama `subprocess.run(["node", tavily_search_path, query], ...)` com timeout de 20s. Se o Tavily não estiver configurado (chave ou path ausente), cai direto para `search_ddg` (DuckDuckGo via `ddgs` lib). Comportamento correto, com fallback real.
- Risco não relacionado a fabricação de dado, mas a superfície de ataque: `cmd = ["node", self.tavily_search_path, query]` — `query` vem de fora (potencialmente do usuário final via pipeline) e é passado como argument list para `subprocess.run` (não shell=True), então não há injeção de shell clássica. Não é um achado desta fase (fora do escopo "roteamento de dados"), mas registrado para a fase de segurança (f51-secure-scan).

## 6. Resumo executivo desta fase

| Achado | Classe | Severidade | Status |
|---|---|---|---|
| `{}` tratado como resultado utilizável, quebra a cadeia de fallback silenciosamente | INFRAESTRUTURA | MÉDIA-ALTA | CONFIRMED |
| Cadeia de prioridade Finnhub→TwelveData→yfinance→Stooq | INFRAESTRUTURA | Informativo | CONFIRMED (bate com descrição prévia) |
| `resolve()` filtra corretamente por chave configurada | INFRAESTRUTURA | — | Correto, sem achado |
| `search_web` passa query para subprocess sem shell=True | SEGURANÇA (fora de escopo desta fase) | A avaliar em fase de segurança | Anotado, não avaliado |

## Próximo passo

Fase 4: `src/core/data_collector/` — verificar se seções simuladas (QuantEngine base fixa 50%, `market_runtime_removed`, `risk_runtime_removed`) são incluídas no pacote agregado sem marcação clara de "simulado" vs "real".
