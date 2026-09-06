# SuperEzio — Validação da entrega Windows

Data: 2026-09-05. Produto: sistema de trade e assistente de investimento.

## Alterações entregues

- Inicialização com APIs externas, sem processo de modelo local obrigatório.
- Parada restrita ao PID e horário de criação registrados pelo launcher.
- Carteira sem capital de missão apresentado como saldo real; saldo indisponível é `null`.
- Remoção de saldo e estatísticas fictícios da interface.
- Estados de conexão, consulta e permissão de ordens paper separados.
- Controles de risco sem aprovação presumida na ausência de evidência.
- Identidade e orientação inicial SuperEzio em português.
- Smoke exige resposta final visível, excluindo cartões de telemetria.
- Runbook atual e distribuição sem archive/deprecated/legacy, caches ou dados do operador.

## Evidência executada

- `python -m ruff check src/ tests/`: All checks passed!
- `python -m ruff format --check src/ tests/`: 430 files already formatted.
- Carteira e indicador de corretora: 9 testes Chromium passaram após a revisão final.
- Saldo do backend e cache IBKR degradado: 16 testes passaram.
- Contratos de runtime e rotas: 68 testes passaram.
- Launcher: 3 testes PowerShell passaram (isolamento, timeout e proteção contra PID reutilizado).
- Pacote: teste de ZIP/manifesto passou; 753 checksums verificados na primeira construção.
- Suite completa: **2346 passed, 9 skipped, 1 deselected in 443.54s**. Log local: `output/pytest-client-final.log`. Os nove skips e o teste live_model deselecionado não são apresentados como testes aprovados.

## Fluxos reais

Consultoria de investimento: resposta DOM final com 4.221 caracteres, resposta da API em português e console sem erros.

Trade TD.TO (2 a 4 semanas): instância nova em modo isolado; 129 candles ordenados, gráfico desenhado, resposta DOM final com 3.197 caracteres, resposta da API com 2.665 caracteres em português. Não foi solicitada execução de ordem.

A instância normal foi reiniciada em `http://127.0.0.1:8002`. Health público e detalhado retornaram HTTP 200. Smoke de gráfico após reinício passou. Carteira desconectada retornou `equity: null`, `equity_source: unavailable`, `can_submit_orders: false`.

## Revisão independente

Revisão dos commits de carteira, permissões e distribuição não encontrou bloqueadores. A ressalva sobre rótulo paper foi corrigida e os nove testes de navegador repetidos. A distribuição validada é Windows.

## Limites da evidência

Execução com dinheiro real continua bloqueada. Integração paper depende de corretora e permissões válidas. Os testes reais realizados cobrem pesquisa, análise e consultoria; não comprovam execução de ordens na corretora. APIs exigem conexão, saldo e cobertura. A instalação em máquina Windows limpa não foi executada nesta sessão; o bootstrap foi testado por contratos e processos simulados, e o launcher foi executado nesta máquina.

O pacote não contém credenciais e dados pessoais locais. O histórico do repositório e a dívida histórica de credenciais não são distribuídos nem declarados saneados. A instância local atual informa acesso sem autenticação; permanece ligada somente a loopback. O bootstrap de cliente oferece configuração de conta e segredo próprios.
