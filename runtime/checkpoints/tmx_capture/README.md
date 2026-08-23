# TMX Money scraping feasibility — live captures (2026-08-23)

Operador autorizou scraping. Fonte oficial: money.tmx.com (TMX Group).

## Veredito: VIÁVEL — endpoint GraphQL interno estável, sem auth

O site é um SPA Next.js: as páginas `/en/quote/{symbol}` (HTML) não embutem
cotações — o browser busca tudo via GraphQL. Endpoint descoberto capturando o
tráfego de rede do site oficial:

```
POST https://app-money.tmx.com/graphql
Content-Type: application/json
```

- Nenhuma API key, cookie ou header Origin necessário (validado com curl puro
  e python `requests` — 200 em todos os casos).
- Operação: `getQuoteBySymbol(symbol, locale)`.
- ~0.5s por chamada; 5 chamadas seguidas OK (sem rate limit visível).
- Símbolos: `TD` / `TD:CA` resolvem; `TD.TO` retorna erro GraphQL 404 explícito
  (`"Sorry, we couldn't find any results for \"TD.TO\""`). O provider criado
  remove o sufixo `.TO`/`.V` antes de consultar.
- Campo `exchangeCode` = TSX/TSXV permite validar a listagem resolvida
  (ex.: `AAPL` bare resolve para o CDR listado na TSX, não a Nasdaq).

## Campos retornados (capturas reais nos gql_*.json)

preço, change, %change, volume, abertura, day high/low, VWAP, market cap
(com e sem classes), P/E, prev close, frequência/valor/currency de dividendo,
dividend yield, beta, EPS, datas ex-dividendo e pagamento, descrição, website,
email, telefone, endereço, funcionários, ações em circulação, D/E, 52w high/low,
médias de volume (10/20/30/50d), P/B, P/CF, ROE, ROA, médias móveis 21/50/200d,
crescimento de dividendo 3/5 anos, setor, indústria, moeda.

## Capturas (arquivos)

| Arquivo | Conteúdo |
|---|---|
| gql_TD.json | Resposta completa real para TD (TSX, Toronto-Dominion Bank) |
| gql_RY.json | Resposta completa real para RY (TSX, Royal Bank of Canada) |
| gql_SHOP.json | Resposta completa real para SHOP (TSX, Shopify, sem dividendo — nulls honestos) |
| gql_CSU.json | Resposta completa real para CSU (TSX, Constellation Software) |
| gql_ZZZZ.json | Erro explícito para símbolo inexistente (código 404 no corpo) |
| td_quote.html | HTML da página /en/quote/TD.TO (SPA — sem dados embutidos) |

## Peculiaridades observadas (tratadas no provider)

- TSXV reporta `peRatio` como string vazia `""` e `eps` como null (HITI) —
  o provider omite esses campos em vez de fabricar valores.
- Empresas sem dividendo retornam `dividendYield`/`dividendAmount` null —
  ausência honesta, nunca zero inventado.
- `dividendYield` vem em percentual (2.778 = 2.778%), mesma unidade do contrato
  Finnhub/yfinance do DataHub.
