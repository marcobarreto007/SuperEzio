# SuperEzio — roadmap sequencial para TD Direct Investing Canada

Status inicial: **NO-GO para dinheiro real**. O freeze de execução permanece ativo até a
Fase 10 e nenhuma fase autoriza login, scraping ou transmissão automática no TD.

## Regras globais

1. Executar uma fase por vez; a próxima começa somente com o gate anterior verde.
2. Cada mudança mínima recebe teste, browser smoke, evidência e commit local.
3. Testes nunca podem alterar journals, memória, RAG, tickets ou bancos de produção.
4. Um verifier diferente do autor revisa toda mudança financeira crítica.
5. Comissão zero é filtro de custo, nunca sinal de compra ou bypass de risco.
6. Nenhuma credencial, conta, cookie ou token TD entra no SuperEzio.
7. Capital autorizado é zero até uma decisão explícita do operador na Fase 10.

## Sequência de gates

### Fase 1 — verdade visual da interface — CONCLUÍDA

Objetivo: impedir que sucesso HTTP seja exibido como confirmação da corretora.

Entregas:

- sucesso visual exige `data.ok === true` e `submitted_to_broker === true`;
- ticket pendente mostra `Not submitted to broker`;
- teste impede o retorno de `Paper order submitted` no caminho pendente.

Verificação registrada:

- 39 testes de rotas passaram;
- Ruff e `node --check` passaram;
- browser smoke passou: health OK, 130 candles, 7 canvases;
- commit: `7270652`.

Gate de saída: **verde**.

### Fase 2 — isolamento e descontaminação de dados — CONCLUÍDA

Objetivo: provar que testes e simulações não conseguem tocar dados usados para decisão.

Entregas:

- caminhos explícitos e separados para `test`, `development` e `operator`;
- `PaperJournal`, Mangala, memória, RAG, outcome learning e traces recebem storage injetado;
- testes falham se tentarem abrir `data/paper_journal.jsonl` ou `runtime/investor.db`;
- inventário dos registros sintéticos existentes, seguido de quarentena recuperável;
- RAG aceita somente registros com provenance e ambiente válidos.

Testes obrigatórios:

- unitários de resolução de path e provenance;
- teste que calcula hashes dos artefatos de operador antes/depois da suíte;
- testes Mangala e feedback usando apenas `tmp_path`;
- regressão RAG: registros `environment=test` nunca são ingeridos;
- browser smoke.

Gate de saída: suíte relevante passa e os hashes de todos os dados do operador permanecem
idênticos. Se qualquer byte de produção mudar, a fase falha.

### Fase 3 — estado financeiro persistente e único — CONCLUÍDA

Objetivo: eliminar kill switch, approval, ticket e status divergentes ou voláteis.

Entregas:

- um único `KillSwitch` compartilhado pelo GuardrailHub e por todos os caminhos financeiros;
- event store append-only para tickets e transições;
- estados imutáveis: `DRAFT -> GATED -> AWAITING_HUMAN -> APPROVED -> MANUALLY_ENTERED ->
  BROKER_CONFIRMED`, com rejeição/cancelamento explícitos;
- ApprovalGate persistente aponta para o mesmo `ticket_id` e fingerprint;
- `/trade/status` reconstrói estado após restart;
- idempotency key persistente e confirmação manual com operador, timestamp e referência TD.

Testes obrigatórios:

- restart/replay do event store;
- concorrência e idempotência cross-process;
- aprovação de ticket diferente ou alterado deve falhar;
- kill switch ativo bloqueia toda promoção;
- property tests das transições de estado;
- browser smoke.

Gate de saída: nenhum estado financeiro depende de dicionário em memória e toda transição é
rastreável e reproduzível.

### Fase 4 — workflow broker-neutral e TD manual — CONCLUÍDA

Objetivo: retirar IBKR/paper do caminho escolhido para TD sem apagar o legado antes da prova.

Entregas:

- contrato `ManualTradeTicket` sem campos TWS/IBKR;
- separação entre análise, elegibilidade, aprovação e transporte;
- TD configurado apenas como `execution_venue=TD_DIRECT_INVESTING_CANADA`;
- graph termina em handoff manual, nunca em `auto_execute_paper`, quando o venue é TD;
- cockpit e textos deixam de afirmar IBKR/paper no modo TD;
- testes garantem que nenhum adapter ou socket de broker é chamado.

Testes obrigatórios:

- testes de roteamento LangGraph para TD e legado;
- contract tests de ausência de transmissão;
- busca estática por dependências IBKR no caminho TD;
- browser smoke dos estados draft/approved/confirmed.

Gate de saída: uma análise TD completa produz somente um ticket manual persistente; zero chamadas
de broker e zero credenciais TD.

### Fase 5 — cotação confiável server-side — CONCLUÍDA

Objetivo: impedir que preço, horário ou fonte declarados pelo navegador autorizem um ticket.

Entregas:

- quote obtida pelo DataHub no servidor, com provider, exchange, currency, `as_of` e evidence ID;
- validação independente por segundo provider quando disponível;
- TTL curto e fail-closed para divergência, atraso, mercado fechado ou moeda incompatível;
- normalização explícita de símbolos TSX/TSXV/US;
- snapshot da evidência incluído no fingerprint do ticket.

Testes obrigatórios:

- quotes stale, futuras, divergentes, sem timezone e com venue incorreto;
- indisponibilidade/circuit breaker de providers;
- idempotência da mesma evidência;
- contract test proibindo promoção de `UNVERIFIED_CLIENT_ASSERTION`;
- browser smoke.

Gate de saída: somente evidência criada e assinada pelo servidor pode mover o ticket para `GATED`.

### Fase 6 — Money Gate Canadá — CONCLUÍDA

Objetivo: calcular risco real da carteira e impedir exposição incompatível com a conta.

Entregas:

- equity e buying power confirmados pelo operador com timestamp e expiração;
- limites de notional, risco por operação, exposição por ativo/setor/moeda e risco agregado;
- regras de TFSA, RRSP, FHSA, CASH e MARGIN modeladas como restrições explícitas;
- risco CAD/USD, concentração, gap, slippage e perda além do stop;
- SELL não pode criar short acidental;
- todos os limites têm defaults seguros e configuração tipada.

Testes obrigatórios:

- boundary/property tests de quantidades e moedas;
- exposição simultânea e ordens concorrentes;
- buying power stale ou insuficiente;
- conta incompatível e venda acima da posição;
- restart e browser smoke.

Gate de saída: nenhuma aprovação é possível sem snapshot de carteira válido e todos os limites
passando simultaneamente.

### Fase 7 — custos e confirmação no TD — CONCLUÍDA

Objetivo: registrar o custo visto pelo operador na prévia oficial do TD.

Entregas:

- comissão, spread, FX, ECN/regulatory fees e custo total estimado;
- elegibilidade dos 108 ETFs com TTL e fonte oficial;
- strategy orders e TD Easy Trade nunca são marcados automaticamente como comissão zero;
- confirmação manual exige o valor exibido no preview TD;
- divergência entre estimativa e preview força nova aprovação.

Testes obrigatórios:

- lista desatualizada, símbolo ausente e condições incompatíveis;
- CAD/USD com e sem conversão;
- preview com comissão inesperada;
- alteração de custo invalida fingerprint/aprovação;
- browser smoke.

Gate de saída: o ticket contém custo total confirmado, não apenas a comissão base.

### Fase 8 — ambiente reproduzível e release gate

Objetivo: executar exatamente o ambiente declarado sem contaminar dados reais.

Entregas:

- interpreter e dependências reproduzidos pelo lock;
- schema Pydantic cobre todas as variáveis críticas e rejeita configuração insegura;
- referências quebradas de Docker, Ruff e Signal Ledger corrigidas ou removidas por contrato;
- CI local cria storage descartável e não acessa dados do operador;
- backup/restauração testados antes de migração.

Testes obrigatórios:

- Ruff, suíte completa, coverage, contracts, security scan e dependency audit;
- browser smoke com servidor e modelo locais;
- teste de restore e restart;
- hashes dos dados do operador antes/depois da suíte.

Gate de saída: todos os gates verdes em máquina limpa e nenhuma diferença nos dados do operador.

Status em 2026-08-19: **EM PROGRESSO / NO-GO**. A suíte completa passou com
1.822 testes e 9 skips, cobertura global de 68%, e o isolamento preservou os hashes
do banco, pain log e traces. O health check que escrevia heartbeats no PaperJournal
foi removido; 6.156 registros sintéticos foram separados com backup recuperável,
restando 534 registros. O browser smoke continua vermelho porque
`/api/chart-data/AAPL` excede 20 segundos no ambiente isolado. Fases 9 e 10 não
começam até esse endpoint falhar rapidamente ou entregar candles verificáveis.

### Fase 9 — benchmark temporal dos agentes

Objetivo: medir se os agentes adicionam valor líquido, em vez de apenas complexidade.

Entregas:

- dataset temporal congelado e splits walk-forward sem leakage;
- baseline simples por horizonte: buy-and-hold, cash e regras técnicas declaradas;
- custos realistas: spread, FX, fees e slippage;
- métricas: retorno líquido, drawdown, Sharpe/Sortino, hit rate, turnover, calibração e abstention;
- ablation por agente e promoção somente quando melhora resultado fora da amostra;
- benchmark específico no universo TD sem comissão, sem dar bônus indevido à comissão zero.

Testes obrigatórios:

- leakage probes, reprodutibilidade por seed e dados faltantes;
- comparação estatística com baseline e intervalos de incerteza;
- stress regimes e delisting/survivorship bias;
- agent-lab com score e evidência persistente.

Gate de saída: vantagem líquida fora da amostra, estável e auditável. Se não superar o baseline,
o agente não entra no caminho financeiro.

### Fase 10 — piloto real estritamente limitado

Objetivo: validar o workflow manual com exposição mínima e autorização separada do operador.

Pré-condições:

- Fases 1–9 verdes;
- kill switch testado no mesmo dia;
- backup e procedimento de incidente verificados;
- limite de capital e risco definidos explicitamente pelo operador;
- nenhuma autorização implícita derivada deste roadmap.

Execução:

- somente LIMIT e execução manual em plataforma oficial TD;
- uma posição por vez no início;
- preview TD registrado antes e confirmação registrada depois;
- reconciliação de posição, custo e estado no mesmo ticket;
- stop operacional e condição de encerramento previamente declarados.

Gate de saída: reconciliação completa sem divergência. Qualquer inconsistência congela novas
operações e retorna à fase responsável.

## Ordem de implementação e commits

Cada fase deve ser dividida em commits pequenos: contrato/teste vermelho, implementação mínima,
verifier/regressão, documentação/checkpoint. Nunca misturar duas fases em um mesmo commit.

O primeiro próximo trabalho autorizado por este roadmap é a **Fase 2 — isolamento e
descontaminação de dados**. Nada neste documento autoriza excluir registros; a quarentena deve ser
recuperável e precedida por inventário com hashes.
