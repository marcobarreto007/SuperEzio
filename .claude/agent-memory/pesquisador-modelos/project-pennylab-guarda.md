---
name: project-pennylab-guarda
description: O expert pennylab mudou de caçador de manipulação para GUARDA, e a base de conhecimento em data/reference/knowledge/pennylab.jsonl foi construída em 2026-09-14
metadata:
  type: project
---

**A mudança de função.** O expert `pennylab` deixou de ser caçador de manipulação
(procurar pump-and-dump para operar) e virou **guarda**: o sistema opera apenas **ETFs
líquidos e commission-free da TSX** com $1.000 CAD, e o dono **executa manualmente e não
entende de finanças**. Detecção de manipulação ali não é fonte de alfa — é **filtro de
segurança**: "esse papel está manipulado, NÃO entra".

**Why:** num universo de ETFs líquidos a manipulação é estruturalmente inviável (float não
é controlável por um grupo, emissor é gestora regulada). A caça a pump-and-dump produziria
falso positivo em escala, e o valor do expert passou a ser **recusar**, não descobrir.

**How to apply:** ao mexer em `pennylab`, lembrar que (a) o alvo é recusar uma compra, não
achar um trade; (b) o critério é objetivo, não gráfico; (c) um guarda que grita sempre é
tão inútil quanto um que nunca grita. As três perguntas de decisão estão no item
`penny_047` e a regra de bloqueio duro (ordem prescrita com quantidade, preço e data) no
`penny_048`.

## O entregável (2026-09-14)

- `data/reference/knowledge/pennylab.jsonl` — **57 itens**, ids `penny_001`..`penny_057`,
  schema idêntico ao de `crisis.jsonl`/`universe.jsonl` (mesmo diretório, agentes irmãos).
- `data/reference/knowledge/pennylab.MANIFEST.json` — 19 erros de fetch literais, o que
  foi procurado e não achado, e os achados de integridade.
- Temas: 14 fontes regulatórias, 17 sinais, 10 casos, 7 sobre distinguir de movimento
  legítimo, 9 limitações.
- Fontes: BCSC 16, InvestRight 7, AMF 7, CIRO 6, CSA/OSC 6, OSC 5, CSA 3, resto síntese.

## Achados de integridade (importantes para o próximo que mexer)

1. **`red_flag_rules.json` tem 21 regras, não 242.** O briefing dizia 242 — 242 é o número
   de **linhas** do arquivo. Dado o briefing, pode voltar a acontecer; conferir sempre.
2. **15 das 21 regras são `computable: false`.** Só 6 são computáveis, e **4 delas são
   exatamente os detectores de volume/preço** — a família de maior falso positivo em ETF
   líquido. Ou seja: o que o sistema consegue computar é justamente o que menos deve pesar.
3. **`enforcement_cases.jsonl` tem URLs inventadas/placeholder** (`.../2024-xxx`) e IDs
   que não resolvem para documento nenhum. Não reusar.

## O que NÃO existe

Nenhum regulador canadense publica lista de **papéis** manipulados — só lista de **quem
oferece investimento**. Não há atalho de consultar cadastro: o guarda avalia critério.
E o texto do **UMIR nunca foi obtido** (403 + Cloudflare): nenhum item cita número de regra
UMIR, de propósito.

Ver [[reference-fontes-regulatorias-canada]] e [[project-experts-trading]].
