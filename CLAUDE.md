# SuperEzio — F51 Bootstrap Operational Layer

## Missão do projeto

Transformar o ecossistema F51 em entrega previsível: decisões auditáveis, runtime estável, testes determinísticos, e execução orientada a receita sem dispersão técnica.

## Regra mestra (gating)

**Sem feature antes de:** inventário, contratos, runtime e testes.

Ordem mínima obrigatória:
1. Inventário (`.f51/INVENTORY_TEMPLATE.json` + estado atual)
2. Contratos (`docs/architecture/ARCHITECTURE_TEMPLATE.md` + contratos públicos)
3. Runtime (`docs/runbooks/RUNBOOK_TEMPLATE.md` + health checks)
4. Testes (plano + execução com evidência)

## Comandos permitidos (bootstrap / operação)

```bash
python -m agent_server.main
python -m pytest tests/ -q
python -m ruff check src tests
python -m ruff format --check src tests
```

Se um comando não existir no ambiente, reportar explicitamente no checkpoint.

## Definição de pronto

Uma tarefa só é “pronta” quando:
- objetivo e escopo estão claros em `.f51/TASK_BOARD.md`;
- risco atualizado em `.f51/RISK_REGISTER.md`;
- checkpoint atualizado em `.f51/checkpoints/latest.json`;
- testes relevantes executados com evidência de resultado;
- sem mudança silenciosa de contrato público.

## Política de testes

- Testes devem ser determinísticos.
- Proibido depender de rede externa para testes unitários.
- Sempre executar o menor conjunto de testes que valide a mudança e, quando necessário, suíte ampliada.
- Relatar: o que rodou, o que passou, o que não foi executado e por quê.

## Política de arquivos

- Não apagar, mover ou renomear arquivos sem tarefa explícita.
- Não alterar diretórios de produto durante bootstrap operacional:
      - `apps/`, `src/`, `packages/`, `core/`, `pipelines/`
- Artefatos operacionais e documentação devem ficar em:
      - `.f51/`, `.claude/skills/`, `docs/`, `runtime/checkpoints/`

## Política de mocks

- Não usar mock para mascarar bug real de integração crítica.
- Mock só quando necessário para isolamento de unidade.
- Todo mock deve ser explícito, rastreável e removível.

## Política de refatoração segura

- Refatorar somente com escopo pequeno e reversível.
- Sem mistura de refatoração + feature na mesma tarefa.
- Preservar APIs/contratos públicos, exceto se houver gate de contrato aprovado.
- Exigir evidência de não regressão (testes + checkpoint).

## Responsabilidade operacional dos agentes

- Todo agente deve atualizar `.f51/checkpoints/latest.json` ao concluir etapa.
- Toda execução deve produzir relatório objetivo (o que fez, evidências, riscos, próximo passo).
- Proibido improvisar escopo fora do gate de decisão.
