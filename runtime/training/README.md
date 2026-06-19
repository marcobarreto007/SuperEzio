# Bob Chart Training Orders

## O que foi feito

Criei 10 ordens de treinamento para o Bob baseadas no endpoint `/api/chart-data/{ticker}` do UI.

## Por que concordo

### Arquitetura Correta

1. **Endpoint de Charts Consolidado**: `/api/chart-data/{ticker}` retorna OHLCV + todos os indicadores técnicos (RSI, SMA, EMA, MACD, Bollinger) em uma única chamada.

2. **Integração com Pipeline**: As ordens usam o padrão `TICKER XXXX: sincronize grafico + Sentimento Vivo` que já está testado nos traces.

3. **Guardrails Intactos**: O endpoint `/trade/execute` respeita a fase de validação - não bypassa o pipeline, o Bob precisa rodar ferramentas primeiro.

### 10 Cenários Cobertos

| ID | Ticker | Tipo | Conceito |
|----|--------|------|----------|
| TRAIN-001 | AAPL | RSI_OVERSOLD_BOUNCE | Recuo RSI < 30 |
| TRAIN-002 | TSLA | RESISTANCE_BREAKOUT | Rompimento de resistência |
| TRAIN-003 | MSFT | SMA20_PULLBACK | Pullback em média móvel |
| TRAIN-004 | NVDA | MACD_BULLISH_CROSS | Cruzamento MACD bullish |
| TRAIN-005 | AMD | VOLUME_SPIKE_CONFIRMATION | Confirmação por volume |
| TRAIN-006 | META | BULLISH_ENGULFING | Padrão de candle |
| TRAIN-007 | GOOGL | GAP_UP_RESISTANCE_TEST | Análise de gap |
| TRAIN-008 | AMZN | LONG_TERM_UPTREND_ENTRY | Tendência de longo prazo |
| TRAIN-009 | NFLX | BOLLINGER_LOWER_BAND_TOUCH | Volatilidade Bollinger |
| TRAIN-010 | INTC | BULLISH_DIVERGENCE_EXIT | Divergência preço/indicador |

## Como usar

```bash
# Via endpoint /task/submit com chart_context
POST /task/submit
{
  "message": "TICKER AAPL: sincronize grafico + Sentimento Vivo. Bob, analise...",
  "chart_context": "<dados do endpoint /api/chart-data/AAPL>",
  "session_id": "training-001"
}
```

## Contrato Mantido

- ✅ Chart context via `/api/chart-data/{ticker}`
- ✅ Sentimento Vivo integrado
- ✅ Ferramentas obrigatórias antes de PAPER_TICKET
- ✅ SDCA firewall ativo
- ✅ F51 verdict + neural decision
- ✅ Risco e invalidação numerados

## Próximo Passo

Executar estas ordens em modo paper para coletar evidências de decisão e ajustar pesos dos guardrails.