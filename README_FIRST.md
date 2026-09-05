# SuperEzio — Trade e assistente de investimento

O SuperEzio reúne gráficos, análise de ativos, acompanhamento de carteira e um assistente de investimento. Use o chat para estudar oportunidades, comparar investimentos e construir planos de entrada, saída e gestão de risco. Bob é o assistente dentro do SuperEzio.

## Instalar

Você precisa de Windows, Python 3.11 ou superior e internet para as APIs externas de inteligência e dados de mercado. Um servidor de modelo local, GPU e CUDA não são requisitos para o assistente em nuvem.

```powershell
$env:SUPEREZIO_ADMIN_PASSWORD = "substitua-por-uma-senha-longa-e-unica"
.\setup_superezio.bat
```

Configure suas chaves no arquivo local `.env.local`. Os modelos e endpoints estão em `config/runtime.yml`; o padrão atual usa a API oficial DeepSeek e a variável `SUPEREZIO_DEEPSEEK_API_KEY`. Os provedores de mercado dependem das chaves e permissões contratadas. Nunca compartilhe esse arquivo na entrega a outro cliente.

## Abrir

```powershell
.\setup_superezio.bat run
```

Acesse [SuperEzio](http://127.0.0.1:8002) e entre com sua conta. Para encerrar, execute `powershell -ExecutionPolicy Bypass -File stop.ps1`.

## Começar a usar

1. Busque um ativo, como `MSFT` ou `TD.TO`, e escolha o período do gráfico.
2. Peça: “Analise TD.TO para swing trade. Mostre fontes, atualidade dos dados, riscos, entrada, invalidação e saída.”
3. Compare alternativas: “Compare MSFT e um ETF amplo para meu horizonte de investimento.”
4. Consulte sua carteira e peça uma revisão de concentração e exposição. Informe apenas posições e valores necessários à análise.
5. Confira se os dados estão disponíveis e atualizados antes de usar uma conclusão. Uma API indisponível ou sem cobertura deve aparecer como limitação, nunca como cotação inventada.

## Operação de trade

A entrega mantém execução com dinheiro real bloqueada. A integração IBKR em paper depende de conexão, habilitação explícita e aprovação dos controles de risco. TD Direct Investing usa preparação e revisão manual, sem transmissão automática. Uma sugestão no chat não equivale a uma ordem executada.

O SuperEzio apoia decisões de investimento, sem promessa de retorno. A disponibilidade dos serviços externos depende de conexão, saldo, cobertura e limites das APIs.

## Verificar a instalação

```powershell
powershell -ExecutionPolicy Bypass -File check.ps1
python -m ruff check src/ tests/
python -m pytest tests/ -q
python scripts/browser_smoke.py
```

O teste de navegador exige a API em execução e acesso válido aos provedores. Consulte `docs/runbooks/RUNBOOK.md` para diagnóstico e recuperação.
