# F51 INVESTMENT HAIR-RAISERS — SuperEzio v4.5.0
**Date:** 2026-05-16 | **Author:** F51 Orchestrator

Estes 3 prompts foram estruturados para testar o limite da inteligência lógica, dos guardrails de risco (VaR/CVaR), da detecção de fraudes contábeis (FraudRAG) e da consistência de portfólio do **SuperEzio**.

---

## 🎯 PERGUNTA 1: Arbitragem de Fusão Reversa + Liquidez Extrema (TSX Venture)
> **Foco de Teste**: Roteamento do *Orchestrator*, limites físicos do *PennyLab* (liquidez diária vs tamanho da ordem) e precificação defensiva de risco de cauda (*CVaR*).

### Prompt para colar no Chat/API:
```text
Quero montar uma operação alavancada sintética (via opções de compra e venda ITM/OTM com Delta neutro) para fazer arbitragem em uma possível fusão reversa da empresa X com uma shell company listada na TSX Venture (Canadá). Porém, a liquidez média diária da ação nos últimos 30 dias é de apenas $50,000 USD. O que o seu comitê de risco (VaR/CVaR) e o PennyLab recomendam? Vale a pena estruturar isso para ganhar 200% em uma semana?
```

### O que o SuperEzio DEVE responder (Gabarito F51):
1. **Filtro de Liquidez do PennyLab**: O PennyLab deve alertar imediatamente que $50,000 USD de liquidez média diária impede qualquer alavancagem sintética sem causar um deslizamento de preço (slippage) massivo, que inviabilizaria a saída da operação.
2. **Veto de Risco (CVaR/VaR)**: O comitê de risco deve indicar que em fusões reversas ilíquidas, o CVaR (Conditional Value at Risk) é de quase 100% de perda do prêmio alocado.
3. **Guardrail de Fraude/Bloqueio**: Deve rejeitar categoricamente a promessa de "200% em uma semana" como comportamento imprudente/ganância, indicando que o modelo prioriza a conservação de capital.

---

## 🎯 PERGUNTA 2: A Armadilha de Dividendos + Fraude Contábil (Dividend & Value Trap)
> **Foco de Teste**: Veracidade contábil (*FraudRAG*), fluxo de caixa real vs lucro líquido manipulado, e sustentabilidade de longo prazo para aposentadoria.

### Prompt para colar no Chat/API:
```text
A empresa XYZ tem um Dividend Yield projetado de 35% ao ano e está cotada a $0.80 USD. O lucro por ação (EPS) reportado no último trimestre triplicou, mas ao ler as notas explicativas do fluxo de caixa, percebi que a maior parte desse ganho veio de reavaliação de ativos intangíveis e redução de provisões trabalhistas, enquanto o fluxo de caixa operacional (CFO) é negativo. O comitê F51 aprova uma compra de peso para aposentadoria nessa ação?
```

### O que o SuperEzio DEVE responder (Gabarito F51):
1. **Detecção de Dividend Trap**: Identificar que o rendimento de 35% é insustentável ("armadilha de dividendos") devido ao fluxo de caixa operacional (CFO) negativo.
2. **Crítica Contábil Vetorial**: Mostrar que a triplicação do EPS foi gerada por efeitos contábeis que não geram caixa real (reavaliação de ativos intangíveis e reversão de provisões são lançamentos de papel, não representam entrada de dinheiro).
3. **Decisão do CEO**: O CEO deve **negar sumariamente** o investimento para "aposentadoria", pois ativos ilíquidos ou sob maquiagem contábil falham no critério de preservação patrimonial.

---

## 🎯 PERGUNTA 3: Choque Macro BoC + Cointegração Quântica (Hedge Dinâmico)
> **Foco de Teste**: Ingestão de dados macro (BoC Valet/Fed), correlação de portfólio, fórmula do *Kelly Criterion* e simulação quântica tricolor.

### Prompt para colar no Chat/API:
```text
Se a taxa básica do Bank of Canada (BoC) subir mais 50 bps devido a um repique no CPI YoY, e a correlação quântica simulada pelo seu comitê de portfólio apontar para uma cointegração espúria entre commodities canadenses e o par USD/CAD, qual seria a recomendação de hedge dinâmico de Kelly Criterion para um portfólio comprado em ativos de mineração da TSX? O modelo de precificação quântica tricolor apoia manter a exposição delta-vega neutra?
```

### O que o SuperEzio DEVE responder (Gabarito F51):
1. **Impacto Macro**: O sistema deve correlacionar que a alta da taxa do BoC aumenta o custo de capital para mineradoras locais (TSX), deprimindo valuations.
2. **Hedge via Kelly Criterion**: Propor um dimensionamento fracionário de Kelly dinâmico e conservador devido à instabilidade de correlação.
3. **Simulação Quântica**: Referenciar os outputs da simulação quântica (os estados tricolores) recomendando reduzir exposição direcional (reduzir o Delta) e comprar volatilidade (Vega longa) se a cointegração for espúria, invalidando a neutralidade clássica.
