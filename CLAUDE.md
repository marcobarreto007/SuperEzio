# SuperEzio

## O que é

Runtime local e camada operacional do ecossistema F51: um agente de trading (Bob) com chat, dados de mercado e execução de ordens, para um operador que roda tudo em disco local, sem nuvem.

## Comandos
- instalar: pip install -e ".[dev]"
- rodar: python -m agent_server.main (a partir de src/)
- testes: python -m pytest tests/ -q
- lint: python -m ruff check src tests && python -m ruff format --check src tests

## Arquitetura em cinco linhas
- entrada: dados de mercado (IBKR, DataHub) via market-data-puller + mensagens do operador no chat
- núcleo: Bob (agent_server) + gateway de modelos local :8080 + teses em runtime/theses + execução com journal e idempotency
- persistência: runtime/ (teses, reports, checkpoints) + data/ (logs) + .f51/ (estado operacional)
- saída: frontend web (chat) + relatórios de tese + logs estruturados
- fora do escopo deste repositório: GitHub, nuvem, dinheiro real (corretora), MCPs não aprovados

## Regras invioláveis
1. Nunca editar arquivo fora deste diretório.
2. Nunca ler nem commitar .env, chave ou credencial.
3. Mudança de comportamento sempre vem com teste.
4. Migração de banco é sempre reversível.
5. Dependência nova só depois de me perguntar.
6. Nunca usar GitHub neste projeto (DISK ONLY — fonte mandataria: .f51/GITHUB_POLICY.json).

## Definição de pronto
Uma tarefa está pronta quando, e só quando:
- pytest -q passa inteiro
- ruff check . está limpo
- o comando de aceite da spec retorna 0
- o diff cabe numa revisão de dez minutos

## Como falar comigo
- Português, direto. Discordou? Diga antes de executar, não depois.
- Antes de código novo, mostre o plano e espere o OK.
- Travou duas vezes no mesmo erro: pare e pergunte.
- Não diga que terminou sem colar a saída do comando que prova.
