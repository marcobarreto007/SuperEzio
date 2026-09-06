# SuperEzio — Entrega ao cliente

Sistema de trade e assistente de investimento, com dados externos, gráficos,
carteira, análise de risco e assistência à decisão. Bob é o assistente do produto.

## Estado da entrega

Entrega local Windows validada: 2346 testes passaram, 9 ignorados e 1 deselecionado.
Lint limpo; smoke real de trade e consultoria aprovado. Este arquivo substitui o handoff operacional antigo,
que descrevia modelos locais e comandos incompatíveis com a configuração atual.
O histórico de versões permanece nos commits locais.

## Instalação e operação

Siga `README_FIRST.md`. O ponto de entrada Windows é `setup_superezio.bat run`,
que chama `start.ps1`. O SuperEzio usa uma API local e modelos externos definidos
em `config/runtime.yml`. Não exige um servidor llama.cpp para a inteligência em nuvem.

`stop.ps1` encerra somente o processo registrado pelo launcher, verificando PID
e horário de criação. Uma instância iniciada por outro comando não é encerrada
apenas por ocupar a porta.

## Critérios de aceite

- Instalação e startup propagam falhas com código de saída não zero.
- Gráfico carrega dados ordenados e desenha candles visíveis.
- Chat finaliza com resposta visível; cartões de telemetria não contam como resposta.
- Carteira indisponível não mostra saldo ou histórico fictício.
- Consulta à corretora não é apresentada como permissão de envio de ordens.
- Testes, lint e smoke real são registrados com resultados atuais.
- Pacote inclui manifesto e checksum, excluindo credenciais, dados pessoais,
  arquivos arquivados, módulos deprecated e caches.

## Limites operacionais

Execução com dinheiro real permanece bloqueada. IBKR paper requer habilitação
explícita e gates aprovados. TD Direct Investing permanece um fluxo manual.
Provedores externos exigem configuração válida, internet e cobertura contratada.

O ZIP de distribuição não inclui as credenciais ou o histórico do operador.
Excluir esses arquivos do pacote não resolve por si só qualquer credencial
exposta anteriormente: a dívida histórica permanece registrada no checkpoint.

## Evidências

As evidências estão em `.f51/checkpoints/latest.json` e em
`docs/CLIENT_DELIVERY_2026-09-05.md`. Não trate um teste com serviços externos ignorados como
prova de integração completa. Os limites da validação e da instalação estão registrados no relatório.
