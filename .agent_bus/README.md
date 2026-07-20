# Agent Bus — Barramento de Comunicação Inter-Agente

## Estrutura

```
.agent_bus/
  runtime/           # Memória volátil (git-ignored)
    tickets/         # Tickets disparados em cada wave
    reports/         # Relatórios de agentes
    state.json       # Estado atual do exército (qual wave, status)
```

## Protocolo

1. **Captain** lê `state.json` e avalia estado atual
2. **Captain** escreve tickets em `tickets/` com Goal, Context, Expected output
3. **Captain** dispara agentes via Agent tool (Claude Code nativo)
4. **Agentes** devolvem relatórios → Captain salva em `reports/`
5. **Captain** integra, atualiza `state.json` e `.f51/checkpoints/latest.json`

## Regras

- Nenhum agente escreve no mesmo arquivo que outro
- Tickets são imutáveis após escritos
- State.json é append-only (log de transições)
- Captain é o único que escreve em `state.json`
