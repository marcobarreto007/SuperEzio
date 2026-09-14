---
name: project-experts-trading
description: O sistema de trading do usuário tem 4 experts (crisis, pennylab, technical_neural, neural_decision) e quais dados cada um exige
metadata:
  type: project
---

Pesquisa feita em 2026-09-14 a pedido do usuário: levantar **datasets** (HF e fora) para
alimentar experts de um sistema de trading.

**Os quatro experts e suas exigências de dado:**

- **`crisis`** — risco sistêmico/macro. Implementa LPPLS (bolha do Sornette), Hawkes,
  Growth-at-Risk (regressão quantílica do IMF), SRISK, Shiller CAPE, Minsky-Keen, hiato de
  crédito do BIS, Markov regime. Precisa de **série macro longa** (crédito/PIB, CAPE, taxas,
  spreads de crédito) + **episódios de crise rotulados**. Tem `MIN_DAYS`/`MIN_PAIRS` que
  impedem rodar sem histórico longo — as fórmulas de primeira linha estão **paradas por falta
  de série**, não por falta de código.
- **`pennylab`** — **MUDOU DE FUNÇÃO em 2026-09-14: virou GUARDA** (era caçador de
  manipulação). Não precisa mais de dataset rotulado com ticker + janela: o objetivo agora
  é **recusar** papel manipulado no universo de ETFs líquidos da TSX. As fontes são
  **regulatórias**, não dataset. Ver [[project-pennylab-guarda]].
- **`technical_neural`** — MLP sobre candles OHLCV, classifica down/sideways/up. Exige
  **≥161 barras por símbolo** e vinha morrendo com 26 barras — ou seja, falta de histórico
  por símbolo é o gargalo real, não falta de dado total.
- **`neural_decision`** — é regra, **não** precisa de dataset.

**Why:** a regra global do usuário é "antes de escrever código, pesquise se alguém já fez
melhor — clone/adapte". Aplicada aqui: procurar dado pronto em vez de construir.

**How to apply:** quando o assunto voltar, partir das fontes já verificadas em
[[reference-fontes-dados-financeiros]] em vez de re-varre o HF. Para `technical_neural`, o
gargalo é **profundidade por símbolo** — ao avaliar qualquer dataset novo, checar logo
barras-por-símbolo e não só linhas totais. Para `crisis`, o HF não tem nada utilizável; o
caminho é JST + FRED + BIS + Shiller. Para `pennylab`, não existe dataset de penny stock
rotulado no HF — só material de cripto; a base foi construída de **fontes regulatórias
canadenses** em 2026-09-14 ([[reference-fontes-regulatorias-canada]]).
