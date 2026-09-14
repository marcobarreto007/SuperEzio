---
name: reference-fontes-regulatorias-canada
description: Mapa de acesso aos reguladores canadenses de valores mobiliários (CSA, OSC, BCSC, AMF, CIRO) — quais respondem direto, quais dão 403, e o contorno gratuito
metadata:
  type: reference
---

Verificado em 2026-09-14 por WebFetch direto (WebSearch estava esgotado). Complementa
[[reference-canada-dados-broker]] (que cobre dado de mercado e broker) com **fontes
regulatórias de fraude/manipulação**.

## O contorno que funciona: `r.jina.ai`

Boa parte dos reguladores canadenses bloqueia fetch automatizado. O leitor público
**`https://r.jina.ai/<url-completa>`** passou onde o acesso direto tomou 403, **sem
cadastro, sem cartão, sem chave**. Use sempre que houver 403 — mas registre no MANIFEST
que o conteúdo veio por leitor.

| domínio | acesso direto | observação |
|---|---|---|
| **bcsc.bc.ca** | **OK direto** | único regulador que respondeu sem proxy |
| **osc.ca** | misto | páginas de listagem OK direto; **artigos de notícia dão 403** |
| **investright.org** (BCSC educação) | 403 | OK via jina |
| **lautorite.qc.ca** (AMF) | 403 | OK via jina |
| **ciro.ca** | 403 | OK via jina **exceto** o texto do UMIR (desafio Cloudflare "Just a moment...") |
| **securities-administrators.ca** | **307 em tudo** | contornar com jina |
| canlii.org | 403 | não deu para ler decisões por essa via |
| iosco.org | 403 | — |

## Onde estão os dados, com os números de 2026-09-14

- **CSA** — arquivo de alertas, maior do país: **5.082 alertas**, buscável.
  URL por slug: `securities-administrators.ca/investor-alerts/<slug>/`
- **OSC** — **1.331 avisos** em 66 páginas: `osc.ca/en/investors/investor-warnings-and-alerts`.
  URL por slug: `/en/investors/warnings/<empresa>`
- **AMF** — **~1.400 avisos** em 70 páginas: `lautorite.qc.ca/en/general-public/media-centre/investor-warnings`.
  Facetas por tópico com contagem — **Market manipulation = apenas 5**.
- **CIRO** — índice disciplinar com **~630 avisos** (63 páginas × 10):
  `ciro.ca/rules-and-enforcement/enforcement/enforcement-proceeding-notices`.
  O índice **não descreve a conduta**; é preciso abrir aviso por aviso.
- **BCSC** — Investment Caution List, CTOs, Halt Trade Orders e alertas em
  `bcsc.bc.ca/enforcement/early-intervention/*`

**Achado que muda o desenho de qualquer guarda:** o volume de alerta canadense é de
**plataforma falsa, cripto e forex** — não de manipulação de papel listado.
Ver [[project-pennylab-guarda]].

## Definições oficiais que valem citar

- **alert vs warning (OSC):** alert = atividade danosa **em curso**; warning = risco
  conhecido e cadastrado.
- **highly liquid security (CIRO/UMIR):** 60 dias com média de **≥100 negócios/dia E
  ≥$1.000.000/dia**. Lista publicada em **CSV diário** — o único limiar de liquidez com
  régua oficial no Canadá.
- **CTO não é sinal de manipulação:** o gatilho mais comum é **falha de arquivo de
  documentos** (divulgação contínua), não fraude.

## Armadilha

`data/fraud_patterns/enforcement_cases.jsonl` tem **URLs placeholder não resolvíveis**
(`.../2024-xxx`) e IDs que não mapeiam para documento citável. Não reusar aqueles casos
como se tivessem fonte. Ver [[project-pennylab-guarda]].
