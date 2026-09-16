# Mike → Ezio: controle e continuidade local

Implementação de 14/09/2026. Pesquisa com referência temporal até agosto de 2026.

## Decisão

Para estes dois processos locais, usar um cliente de controle com recibos duráveis,
snapshot operacional periódico e recuperação de memória por sessão. SQLite já faz
parte do ambiente; não foi introduzido serviço pago nem outro servidor de workflow.

```
Mike :8083 /v1/ezio/commands → bridge :8009 /commands → Ezio :8002 /control/commands
Mike :8083 /v1/ezio/task     ↗ (compatibilidade SSE; devolve recibo, não resposta final)

Ezio → coleta bridge (intervalo configurado: 5 s)
bridge /console/state → coletor Mike (intervalo configurado: 5 s)
                     → Mike runtime/state/ezio-continuity.sqlite3
                     → contexto do modelo a cada pedido
memória Mike → último checkpoint da mesma sessão → contexto do pedido
```

São intervalos configurados, não garantia de latência: timeout e duração de coleta
somam-se ao intervalo. A resposta `/v1/ezio/context` informa idade e fresh/stale.
A observação é stale se o poll upstream tiver mais de 20 s ou se a cópia no Mike
tiver mais de 15 s. Um erro de coleta também torna o estado stale.

## Recuperação

- O coletor sobe no lifespan antes do bootstrap pesado do cérebro, e é cancelado
  explicitamente no shutdown. Não chama LLM e não depende de conversa aberta.
- O SQLite conserva a última observação e os recibos. Após reiniciar, o snapshot
  é histórico até uma nova consulta bem-sucedida; indisponibilidade não apaga a prova anterior.
- Cada comando é reservado por ID e hash antes do HTTP. Payload diferente com o
  mesmo ID é conflito. Reenvio do mesmo ID consulta o recibo e não executa de novo.
- Timeout/crash deixa `unknown`. Não há replay automático de efeitos. É preciso
  reconciliar o ID com o executor; `applied` significa aceitação/aplicação do comando,
  não conclusão da tarefa financeira. O bridge e o ledger do Ezio ainda são voláteis.
- A memória consulta o checkpoint mais recente **da mesma sessão**; não restaura
  destrutivamente uma conversa antiga. Mensagens posteriores têm precedência.
  O default de auto-checkpoint do Mike passou para cada turno persistido; a variável
  `MIKE_AUTO_CHECKPOINT_INTERVAL` continua sendo override explícito.
- Estado global contém apenas metadados operacionais. Resumos de conversa entram
  somente no contexto da sessão correspondente, fora dos modos privado/raw.

## Fronteira

A allowlist continua no bridge. O cliente não cria sua própria lista paralela.
Leituras de saúde podem usar 8002; comandos desta API nunca fazem fallback para
`/task/submit`. O cérebro do Mike permanece local. As ferramentas preexistentes de
shell/edição de código são um canal de manutenção separado: esta mudança não
afirma que um prompt transforma esse canal em uma barreira de segurança.

## Pesquisa e alternativas

- [Anthropic, Effective context engineering, 29/09/2025](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents): contexto selecionado e notas duráveis fora da janela. Orienta a separação entre estado operacional compacto e memória da sessão.
- [Anthropic, Effective harnesses for long-running agents, 26/11/2025](https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents): recuperação por registros de progresso e verificação real ao retomar. Contexto longo sozinho não resolve continuidade.
- [Temporal, arquitetura](https://github.com/temporalio/temporal/blob/main/docs/architecture/README.md): histórico de eventos e reconstrução de estado. Alternativa para muitos workflows duráveis; não adotada aqui porque exigiria outra infraestrutura. O recibo local não oferece todas as garantias de Temporal.
- [LangGraph, persistência](https://docs.langchain.com/oss/python/langgraph/persistence): checkpoints por thread. Serve de referência conceitual; o Mike conserva sua memória existente em vez de ganhar um segundo grafo. Esta página é documentação corrente consultada em setembro, não um snapshot comprovado de agosto.

## Verificação reproduzível

No Mike: `.venv/Scripts/python.exe -m pytest tests/unit/test_ezio_continuity.py tests/unit/test_light_chat_context.py -q`.
No Ezio: `python -m pytest bridge/tests -q`.
Runtime: `GET :8083/v1/ezio/context`, aguardar um ciclo e verificar avanço de
`observed_at_epoch`; reiniciar Mike e verificar recuperação. Testes herméticos
cobrem recibo após restart, timeout sem duplicação, isolamento de sessão e rota
HTTP passando pela ponte. Provas de runtime devem distinguir comando negado,
comando aceito e tarefa concluída.
