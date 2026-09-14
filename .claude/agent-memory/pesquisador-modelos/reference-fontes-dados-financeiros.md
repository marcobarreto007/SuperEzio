---
name: reference-fontes-dados-financeiros
description: Fontes de dado financeiro/macro verificadas como acessíveis SEM token em 2026-09-14 (FRED, BIS, Shiller, JST, OFR FSI, API do HF)
metadata:
  type: reference
---

Verificado em 2026-09-14, sem token, por requisição direta. Reutilizável para qualquer trabalho
de dado de mercado/macro neste projeto.

## Truques de acesso (o que funciona sem autenticação)

- **API de datasets do HF**: `https://huggingface.co/api/datasets?search=TERMO&limit=N` lista
  com downloads/likes/lastModified/license. Com `?blobs=true` no id específico devolve a
  **lista de arquivos com tamanho em bytes** — é assim que se pega tamanho real em vez de
  confiar no card.
- **datasets-server do HF** (o mais útil, e pouco conhecido):
  - `https://datasets-server.huggingface.co/info?dataset=ORG%2FNOME` → `num_examples`,
    splits, nomes e tipos das colunas. **Não baixa o dataset.**
  - `https://datasets-server.huggingface.co/rows?dataset=ORG%2FNOME&config=default&split=train&offset=N&length=3`
    → linhas cruas. Serve para achar a **primeira e a última data** de uma série
    (offset 0 e offset num_examples-1) sem baixar o arquivo.
  - Nem todo dataset tem config automática; parquet solto na raiz costuma funcionar.
- **FRED sem API key**: `https://fred.stlouisfed.org/graph/fredgraph.csv?id=SERIE&cosd=AAAA-MM-DD`
  devolve CSV cru. Confirmado com `BAMLH0A0HYM2`. Não precisa de cadastro — só a API JSON
  (`api.stlouisfed.org`) exige key. Série por série, não é bulk.
- **`WebSearch` tem teto por sessão** (bateu 200/200 numa tarefa de varredura de datasets).
  Planeje: gaste `WebSearch` só onde não se sabe a URL, use `WebFetch` direto no resto.

## Fontes confirmadas (link + licença)

| fonte | URL | licença | o que tem |
|---|---|---|---|
| FRED | fred.stlouisfed.org/graph/fredgraph.csv?id=... | termos FRED + da série de origem | qualquer série do FRED: spread high yield, curva, dívida/PIB, STLFSI4, NFCI, WALCL |
| BIS bulk | data.bis.org/bulkdownload → `/static/bulk/WS_CREDIT_GAP_csv_flat.zip`, `WS_TC_csv_flat.zip` | termos BIS | **credit-to-GDP gap** e crédito total ao setor não-financeiro, trimestral, 40+ economias (~45 anos no privado) |
| Shiller | shillerdata.com → `ie_data.xls` | sem licença explícita, só disclaimer | mensal desde jan/1871: preço, dividendos, lucros, CPI, juros, **CAPE** |
| JST Macrohistory R.6 | macrohistory.net/database/ → `JSTdatasetR6.xlsx` / `.dta` | **CC BY-NC-SA 4.0** (não comercial) | 18 economias, anual, **1870→**: crédito ao setor privado, hipotecas, empréstimos, preço de imóveis, dívida pública, taxas, e **dummy de crise financeira sistêmica** |
| OFR FSI | financialresearch.gov/financial-stress-index/data/fsi.csv | sem licença explícita, só disclaimer | diário desde **2000-01-03**: índice + 5 subíndices (crédito, valuation, funding, safe assets, volatilidade) + 3 regiões |

## Pegadinhas aprendidas

- `paperswithbacktest/Stocks-Daily-Price` (25,9M linhas, 7.764 símbolos, 1962→2026) **exige
  assinatura paga** para baixar, apesar de `gated: false` na API. O `HexQuant/Stocks-Daily-Price`
  é cópia com o mesmo gate. **`gated: false` na API não significa baixável** — sempre ler o card.
- Dataset com nome de "volatilidade" pode ser índice sintético de corretora (Deriv), não o VIX.
  `Mikecode123/volatility_100_index` não foi verificado quanto a isso.
- Datasets com README de poucos bytes e zips sem schema (ex.: `Go3x3/pump_and_dump_dataset`)
  existem mas não são auditáveis — não recomendar sem abrir.
- imf.org devolve **403** para fetch automatizado; material do IMF (base Laeven-Valencia de
  crises bancárias) não é verificável por esse caminho.

Ver também [[project-experts-trading]].
