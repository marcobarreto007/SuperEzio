---
name: reference-emissores-etf-alcance
description: Quais sites de emissor de ETF respondem ao WebFetch nesta maquina, quais bloqueiam, e o caminho que funciona para cotacao/ficha de ETF canadense (stockanalysis.com/quote/tsx/)
metadata:
  type: reference
---

Mapa de alcance medido em 2026-09-14, coletando a base `data/reference/knowledge/universe.jsonl` (82 ETFs elegiveis do TD).

**Respondem (dado do proprio emissor):**
- `ssga.com` (State Street) — SPY, GLD, DIA, SPHY. Traz "expense ratio" com data de referencia e lista dos maiores holdings.
- `invesco.com` — QQQ.
- `ishares.com` — IWM. ATENCAO: a URL tem ID numerico de produto e **nao e adivinhavel**: `/us/products/239726/` devolve IVV e `/us/products/239725/` devolve IVW. Sempre conferir o nome do fundo que voltou antes de usar o dado.

**Bloqueiam ou nao servem (WebFetch direto):**
- `vanguard.ca` — 404 nos caminhos de produto testados e 503 nas listas. O site parece indisponivel para esta rede, nao so bloqueio de bot.
- `globalx.ca` — 403 no dominio inteiro.
- `schwabassetmanagement.com` — 403. `vaneck.com` — loop de redirect. `ci.com` — 404.
- `td.com/ca/en/asset-management/...` — todo caminho de ETF testado deu 404 (o antigo `tdassetmanagement.com` redireciona para td.com e nao expoe lista).
- `investor.vanguard.com` e `advisors.vanguard.com` — devolvem so o titulo (pagina em JavaScript).
- `money.tmx.com` — idem, JavaScript.

**Caminho que funciona para ETF canadense:** `https://stockanalysis.com/quote/tsx/<TICKER>/` (aceita ticker com ponto: `TDOC.U`, `BTCX.B`). Para ETF americano: `https://stockanalysis.com/etf/<ticker>/`. E um AGREGADOR, nao o emissor: entrega "Expense Ratio", indice rastreado, numero de holdings, maiores posicoes, moeda e emissor — sem data de vigencia da taxa. Marcar o dado como `mer_de_agregador`.

**Contorno conhecido:** `https://r.jina.ai/<URL>` derruba o 403 (funcionou com globalx.ca), mas nao resolve pagina em JavaScript nem 503 do alvo. Ver [[reference-fontes-regulatorias-canada]]. Para MER oficial o caminho que resta e baixar o ETF Facts em PDF — e esta maquina nao tem extrator de PDF instalado (o Read falha com "pdftoppm is not installed").
