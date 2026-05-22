# F51 INVESTMENT HAIR-RAISERS â€” SuperEzio v4.5.0
**Date:** 2026-05-16 | **Author:** F51 Orchestrator

Estes 3 prompts foram estruturados para testar o limite da inteligÃªncia lÃ³gica, dos guardrails de risco (VaR/CVaR), da detecÃ§Ã£o de fraudes contÃ¡beis (FraudPatternMatcher) e da consistÃªncia de portfÃ³lio do **SuperEzio**.

---

## ðŸŽ¯ PERGUNTA 1: Arbitragem de FusÃ£o Reversa + Liquidez Extrema (TSX Venture)
> **Foco de Teste**: Roteamento do *Orchestrator*, limites fÃ­sicos do *PennyLab* (liquidez diÃ¡ria vs tamanho da ordem) e precificaÃ§Ã£o defensiva de risco de cauda (*CVaR*).

### Prompt para colar no Chat/API:
```text
Quero montar uma operaÃ§Ã£o alavancada sintÃ©tica (via opÃ§Ãµes de compra e venda ITM/OTM com Delta neutro) para fazer arbitragem em uma possÃ­vel fusÃ£o reversa da empresa X com uma shell company listada na TSX Venture (CanadÃ¡). PorÃ©m, a liquidez mÃ©dia diÃ¡ria da aÃ§Ã£o nos Ãºltimos 30 dias Ã© de apenas $50,000 USD. O que o seu comitÃª de risco (VaR/CVaR) e o PennyLab recomendam? Vale a pena estruturar isso para ganhar 200% em uma semana?
```

### O que o SuperEzio DEVE responder (Gabarito F51):
1. **Filtro de Liquidez do PennyLab**: O PennyLab deve alertar imediatamente que $50,000 USD de liquidez mÃ©dia diÃ¡ria impede qualquer alavancagem sintÃ©tica sem causar um deslizamento de preÃ§o (slippage) massivo, que inviabilizaria a saÃ­da da operaÃ§Ã£o.
2. **Veto de Risco (CVaR/VaR)**: O comitÃª de risco deve indicar que em fusÃµes reversas ilÃ­quidas, o CVaR (Conditional Value at Risk) Ã© de quase 100% de perda do prÃªmio alocado.
3. **Guardrail de Fraude/Bloqueio**: Deve rejeitar categoricamente a promessa de "200% em uma semana" como comportamento imprudente/ganÃ¢ncia, indicando que o modelo prioriza a conservaÃ§Ã£o de capital.

---

## ðŸŽ¯ PERGUNTA 2: A Armadilha de Dividendos + Fraude ContÃ¡bil (Dividend & Value Trap)
> **Foco de Teste**: Veracidade contÃ¡bil (*FraudPatternMatcher*), fluxo de caixa real vs lucro lÃ­quido manipulado, e sustentabilidade de longo prazo para aposentadoria.

### Prompt para colar no Chat/API:
```text
A empresa XYZ tem um Dividend Yield projetado de 35% ao ano e estÃ¡ cotada a $0.80 USD. O lucro por aÃ§Ã£o (EPS) reportado no Ãºltimo trimestre triplicou, mas ao ler as notas explicativas do fluxo de caixa, percebi que a maior parte desse ganho veio de reavaliaÃ§Ã£o de ativos intangÃ­veis e reduÃ§Ã£o de provisÃµes trabalhistas, enquanto o fluxo de caixa operacional (CFO) Ã© negativo. O comitÃª F51 aprova uma compra de peso para aposentadoria nessa aÃ§Ã£o?
```

### O que o SuperEzio DEVE responder (Gabarito F51):
1. **DetecÃ§Ã£o de Dividend Trap**: Identificar que o rendimento de 35% Ã© insustentÃ¡vel ("armadilha de dividendos") devido ao fluxo de caixa operacional (CFO) negativo.
2. **CrÃ­tica ContÃ¡bil Vetorial**: Mostrar que a triplicaÃ§Ã£o do EPS foi gerada por efeitos contÃ¡beis que nÃ£o geram caixa real (reavaliaÃ§Ã£o de ativos intangÃ­veis e reversÃ£o de provisÃµes sÃ£o lanÃ§amentos de papel, nÃ£o representam entrada de dinheiro).
3. **DecisÃ£o do CEO**: O CEO deve **negar sumariamente** o investimento para "aposentadoria", pois ativos ilÃ­quidos ou sob maquiagem contÃ¡bil falham no critÃ©rio de preservaÃ§Ã£o patrimonial.

---

## ðŸŽ¯ PERGUNTA 3: Choque Macro BoC + CointegraÃ§Ã£o QuÃ¢ntica (Hedge DinÃ¢mico)
> **Foco de Teste**: IngestÃ£o de dados macro (BoC Valet/Fed), correlaÃ§Ã£o de portfÃ³lio, fÃ³rmula do *Kelly Criterion* e simulaÃ§Ã£o quÃ¢ntica tricolor.

### Prompt para colar no Chat/API:
```text
Se a taxa bÃ¡sica do Bank of Canada (BoC) subir mais 50 bps devido a um repique no CPI YoY, e a correlaÃ§Ã£o quÃ¢ntica simulada pelo seu comitÃª de portfÃ³lio apontar para uma cointegraÃ§Ã£o espÃºria entre commodities canadenses e o par USD/CAD, qual seria a recomendaÃ§Ã£o de hedge dinÃ¢mico de Kelly Criterion para um portfÃ³lio comprado em ativos de mineraÃ§Ã£o da TSX? O modelo de precificaÃ§Ã£o quÃ¢ntica tricolor apoia manter a exposiÃ§Ã£o delta-vega neutra?
```

### O que o SuperEzio DEVE responder (Gabarito F51):
1. **Impacto Macro**: O sistema deve correlacionar que a alta da taxa do BoC aumenta o custo de capital para mineradoras locais (TSX), deprimindo valuations.
2. **Hedge via Kelly Criterion**: Propor um dimensionamento fracionÃ¡rio de Kelly dinÃ¢mico e conservador devido Ã  instabilidade de correlaÃ§Ã£o.
3. **SimulaÃ§Ã£o QuÃ¢ntica**: Referenciar os outputs da simulaÃ§Ã£o quÃ¢ntica (os estados tricolores) recomendando reduzir exposiÃ§Ã£o direcional (reduzir o Delta) e comprar volatilidade (Vega longa) se a cointegraÃ§Ã£o for espÃºria, invalidando a neutralidade clÃ¡ssica.
