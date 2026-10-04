# SuperEzio — caminho curto para uma demonstração honesta

Estado medido em 4 de outubro de 2026. O produto é um cockpit local de pesquisa de investimentos para Marco: dados de mercado → matemática → seis especialistas → resposta do Bob → revisão humana. TD é manual; execução com dinheiro real permanece bloqueada. O arranque previsto é `start.ps1` (API `127.0.0.1:8002`, bridge `:8009`). O servidor não estava ligado durante a auditoria. Uma resposta autenticada com dados atuais e fontes é a prova mínima de funcionamento; um teste verde sozinho não a substitui.

## 1. Fechar a base verificável

| Trabalho | Estado | Prova para fechar |
| --- | --- | --- |
| Classificar `GET /api/heart/status` na bridge | Feito | `tests/test_control_endpoints.py` passa; rota declarada em `bridge/events.toml` |
| Rever a lista oficial TD de 108 ETFs | Feito em 04-10; validade 7 dias | Comparação exata de símbolo e mercado com a tabela da TD; `tests/test_td_direct_ticket.py` passa |
| Recalcular o universo efetivo com preços novos | Feito em 04-10; validade 7 dias | `scripts/verify_effective_universe.py` passa e `tests/test_effective_universe.py` passa; os 17 avisos de séries defasadas permanecem visíveis |
| Correr a suíte completa após as mudanças | Em verificação | Resultado completo com `--maxfail=0`, distinguindo falha, skip e teste dependente de serviço externo |

Os dois manifestos expiram independentemente. Não alterar só `verified_at` ou `generated_at` para obter verde: comparar primeiro a lista oficial e reconstruir o universo com preços novos. Confirmar sempre comissão e elegibilidade no preview do TD antes de uma ordem manual.

## 2. Segurança antes de ligar a API

| Trabalho | Estado | Prova para fechar |
| --- | --- | --- |
| Desligar acesso anónimo na configuração local | Feito nesta máquina; `.env.local` é ignorado pelo Git | `SUPEREZIO_OPEN_ACCESS=0`, segredo JWT forte e login autenticado num arranque controlado |
| Manter freeze real e paper opt-in | Sem alteração deliberada | Leitura do gate em runtime; nenhuma ordem transmitida durante a verificação |
| Revogar credenciais historicamente expostas | Pendente de prova dos provedores | Recibo ou estado de revogação de DeepSeek, TwelveData, Alpha Vantage e NewsAPI; substituir chaves locais sem as escrever em tickets ou commits |
| Conferir o acesso ao serviço | Pendente | Bind apenas em loopback, anónimo recebe 401 nas rotas protegidas, login válido funciona |

## 3. Tornar os veredictos operacionais

Tratar cada ponto como mudança pequena com teste de falha e caminho de rollback. Manter a execução real congelada durante toda esta fase.

1. O F51 exige claims e ground truth independentes, mas o fluxo normal não os produz. Definir a proveniência dos dois antes de tentar permitir `passed=True`. Nunca aliviar o gate apenas para conseguir uma ordem.
2. O SDCA/C4 está em *observe*: um BLOCK ou erro não pára a resposta. Testar casos reais e falsos positivos antes de promover C4 a gate ativo.
3. O Guardrail Hub corre antes do texto final; verificações de saída ficam sem texto. Ligar uma revisão após a resposta e testar que bloqueio/erro não desaparece em silêncio.
4. `expert_committee_status="OK"` é escrito mesmo que todos os especialistas falhem. Fazer o estado refletir resultados válidos e mostrar cobertura parcial.
5. Reavaliar o modelo neural com dados atuais. O código admite `ready` sob qualificação; a auditoria não provou uma previsão qualificada recente nem desempenho preditivo.

## 4. Demonstração e comunicação

1. Arrancar localmente com login, freeze e serviços externos verificados; guardar só evidência sem segredos.
2. Fazer uma pergunta sobre um ativo e seguir dados → cálculo → seis pareceres → bloqueios → resposta. Confirmar a frescura e as fontes na interface.
3. Testar TD até à prévia manual, sem transmitir ordem; testar IBKR apenas em paper, com opt-in explícito.
4. Publicar números de testes com data e limitações. O site F51 deve reconhecer que o código existe, que a orquestração do captain requer operador e que a IBKR tem um caminho paper condicionado.

**Critério de entrega:** suíte sem falhas não explicadas, credenciais revogadas com prova, acesso autenticado demonstrado e fluxo principal visto numa execução real. Até lá: pesquisa local em verificação, sem promessa de autonomia de trading ou retorno financeiro.
