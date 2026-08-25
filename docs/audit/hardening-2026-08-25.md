# Auditoria do caminho de trade — achados e correções (2026-08-24/25)

Consolidado da auditoria completa das sete dimensões do caminho de trade.
Evidência por item: `git log` de cada commit + teste que falha contra o código
original. Suíte final: **2240 passed, 0 failed, 3 skipped** com servidor vivo.

## Dimensões e veredito

| Dimensão | Veredito pré-correção | Sustentação |
|---|---|---|
| FSM de ordens | CONFORME | `workflow_store.py:22-34`, terminais `:31-33` |
| Idempotência (mecanismo) | CONFORME | UNIQUE `:120,:132,:166`; `BEGIN IMMEDIATE` `:221,:292` |
| Idempotência (chave) | DEFEITO → corrigido | janela truncada de relógio (borda 10:04:59/10:05:01) |
| Ledger append-only | AUSENTE no PaperJournal → corrigido | `_rewrite` com `open(...,"w")` + descarte de linha corrompida |
| Matemática (ffill) | REFUTADO | zero ocorrências em `src/` |
| Fallbacks silenciosos | 1 ALTO + 3 MÉDIOS, 9 legítimos → corrigidos | `main.py:811` era o grave |
| Fronteira LLM↔execução | PARCIAL → corrigido | `tool_executor.py:455` honrava limit_price do modelo; stop_loss contornava aprovação de $500 |

## Correções (ordem cronológica)

1. **Healthcheck fail-closed** (`522f0df`): sonda de consciência falhou → 503 com
   `detail`, nunca mais 200 mentiroso com o CEO caído.
2. **Journal atômico + quarentena** (`47fff47`): tmp+fsync+`os.replace`; linha
   corrompida preservada em `.quarantine` antes de qualquer reescrita.
3. **Borda de idempotência** (`8d6ae5a`, `2e0b0be`): chaves das janelas atual E
   anterior; `create_ticket` aceita `fingerprint_aliases`; claim atômico do par.
4. **Falhas silenciosas logadas** (`2dbcb3a`): yfinance intraday, pain log,
   cancel_open_order. Nove pontos confirmados legítimos ficaram intactos.
5. **Lock intra + cross-process do journal** (`886b956`, `588cffb`): RLock no span
   RMW + lock de arquivo msvcrt (região do byte 0) para agent_server × scan Mangala.
6. **MAN_AT_WORK endurecido e enforçado** (`b16c66c`, `eb9a9bc`): entrada só com 3
   falhas consecutivas (reusa contador do Organ), recovery a cada ciclo; GATE 1.5
   fail-closed no `evaluate_trade_gate`.
7. **Stop do modelo ignorado** (`be5cd08`): fecha o bypass da aprovação humana de
   $500 (risk = |limit − stop| × qty era manipulável pelo modelo).
8. **Colar de preço** (`3dc38350`): GATE 9.5 `LIMIT_PRICE_COLLAR`, banda 5%/10%
   condicionada à idade da referência (universo penny + scan de 5 min).
9. **Costura LLM** (`9e439a3`): `calculate` entrou no Literal (era despachado e
   morria no validate); drops de tool call logados, fail-soft sem `extra=forbid`.
10. **Frontend honesto** (`eb9a9bc`, `be6ab58`): `fetchJson` propaga `detail`;
    cockpit distingue 503-degradado de offline; `idempotent_replay` exibido como
    "já estava registrado — ticket X"; branch morto `brokerConfirmed` removido.
11. **Taxonomia de reason_code** (`ffb5837`): `core.trading.reason_codes` +
    teste de conformidade que extrai os literais do gate.

## Fatos que a auditoria refutou

- "O sistema usa ffill sobre preço" — falso, zero ocorrências em `src/`.
- "Os componentes têm nome certo e função fraca" — refutado no núcleo:
  `TradeWorkflowStore` é Tier-1 (FSM explícita, idempotência no banco,
  reserva atômica de buying power).
- "O modelo inventa preço em todos os caminhos" — falso: `_resolve_limit_price`
  e `_build_submit_paper_order_call` já resolvem do DataHub; só o caminho
  `node_tool_executor → _submit_paper_order` honrava args do modelo.

## Pendências anotadas (não bloqueantes)

- Colar por múltiplo de ATR (substituindo % fixo; ATR já é calculado em
  `neural_decision.py:223-232` e roda antes do gate).
- Schemas por-tool completos em `AgentToolCall.args` (sem `extra=forbid` —
  droparia tool calls inteiras do modelo local).
- Migração dos demais emissores de motivo (position_sizer, manual_trade_workflow,
  approval_gate) para a taxonomia central.
- `ruff format` nos 5 arquivos pré-existentes (endpoints.py, agent.py,
  collector.py, penny_scanner.py, finnhub_provider.py) — tarefa dedicada.
- Testes do colar de 2% do caminho TD (`td_direct_ticket.py:295-300` não tem
  teste unitário do desvio).

## Verificação

- Suíte final: **2240 passed, 0 failed, 3 skipped** (713s) — baseline da sessão
  2201/11; servidor :8002 vivo faz os testes de smoke executarem.
- Cada correção com teste que falha contra o código original (prova por
  `git stash` do alvo).
- `browser_smoke.py` VERDE: Bob respondeu (bobMsgCount 1, PT válido, stream
  completo, 0 erros de console). Screenshot: `output/playwright/`.
- Ruff check limpo; secrets scan limpo; DISK ONLY respeitado.
