---
name: reference-canada-dados-broker
description: Acesso a dado de mercado canadense (TSX/TSXV) e a situação do broker TD Direct Investing — o que é grátis e o que não existe
metadata:
  type: reference
---

Verificado em 2026-09-14 por fetch direto. Complementa [[reference-fontes-dados-financeiros]]
(que cobre macro) com **equity canadense** e **broker**.

## Dado de equity TSX/TSXV que serve

| fonte | como | licença | grátis? | cobertura canadense |
|---|---|---|---|---|
| **OpenBB provider `tmx`** | `pip install openbb-tmx` | **AGPL-3.0-only** | provavelmente sim — ver ressalva | TSX **e TSXV**; **não exige sufixo de exchange**; aceita `.TO` e `.TSX` |
| Alpha Vantage | API com key | termos AV | free tier **25 req/dia** | sim, com sufixo **`.TRT`** (Toronto) e **`.TRV`** (Venture) |
| yfinance | `yfinance` | Apache-2.0 (lib) | sim | sim, sufixo `.TO` — **não verificado nesta pesquisa** |

**O provider `tmx` do OpenBB é o achado principal.** Endpoints: `equity.price.historical`/`quote`,
`equity.fundamental.dividends`/`filings`, `equity.ownership.insider_trading`,
`equity.calendar.earnings`, `equity.estimates.consensus`, `equity.profile`, `equity.search`,
ETF (só top 10 holdings), `index.constituents`, `fixedincome.*`, `news.company`,
`derivatives.options.chains` (EOD desde 2009). Intraday começa **2022-04-14**. Ajuste:
diário tem split / split+dividendo / não-ajustado; outros intervalos só split. Tem cache
(`aiohttp-client-cache` + SQLite) e `use_cache=False`. Versão `openbb-tmx 1.5.2`.

**RESSALVA IMPORTANTE (não confirmado):** o README do provider não menciona API key, e o
`pyproject.toml` não tem nenhuma dependência de credencial — mas depende de
`random-user-agent`, o que indica **scraping dos dados públicos do site da TMX**, não uma
API licenciada. Não li os termos de uso da TMX. Tratar como "provável que seja grátis" e
verificar antes de depender.

**Licença AGPL é armadilha neste projeto:** a OpenBB Platform é AGPLv3 e o `openbb-tmx` é
AGPL-3.0-only. O SuperEzio serve HTTP (`:8002`, bridge `:8009`), e a cláusula de rede da
AGPL pode ser acionada. **Não importar `openbb` para dentro do SuperEzio** — usar como
processo separado, ou só ler o código do provider como referência de endpoints.

## Broker: TD Direct Investing — não existe API pública

- `developer.td.com` e `developer.tdameritrade.com` — **ambos com DNS que não resolve**
  em 2026-09-14 (`getaddrinfo ENOTFOUND`). A API do TD Ameritrade foi encerrada; nada
  substituiu para o lado canadense.
- Ou seja: **execução no TD Direct Investing é manual** (ou por automação de UI, que é
  frágil). Não há caminho de API.
- Para **execução automatizada**, o que os frameworks suportam é **Interactive Brokers**
  (Lumibot suporta IBKR inclusive via REST). O SuperEzio **já puxa dado do IBKR** pelo
  market-data-puller — mas o protocolo de sobrevivência manda executar nos ETFs
  commission-free do TD. Isso é uma tensão real de arquitetura, não resolvida.
- **Nenhum framework open source tem conector canadense** (i.e. TD, RBC, Questrade,
  Banque Nationale). Lumibot: Alpaca, IBKR, Tradier, Schwab, Tradovate, TopstepX,
  Bitunix, Polymarket — zero Canadá.

Ver também [[project-experts-trading]] e [[project-superezio-clone-comite]].
