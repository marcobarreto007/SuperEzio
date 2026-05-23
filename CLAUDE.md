# SuperEzio — F51 Bootstrap Operational Layer

## REGRA CRITICA: GITHUB BLOQUEADO

Fonte mandataria: `.f51/GITHUB_POLICY.json`

Este projeto esta em modo **DISK ONLY**.

Regra clara:
- NUNCA usar GitHub neste projeto.
- NUNCA executar `git push`, `git pull`, `git fetch` ou `gh`.
- NUNCA usar GitHub Actions, pull requests, GitHub API, conector GitHub ou MCP GitHub.
- Commits locais sao permitidos quando Marco pedir para salvar, mas sem push.
- Se uma tarefa exigir GitHub, parar e reportar bloqueio.

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
python scripts/browser_smoke.py
```

**Regra Playwright:** Todo `pytest` deve ser acompanhado de `python scripts/browser_smoke.py`.
O servidor precisa estar live. Se o servidor não estiver reachable, o smoke é skipped com
warning visível no output do pytest (via fixture condicional em `tests/conftest.py`).

**Modo visível (headed):** Para assistir o browser executando em tempo real:
```bash
# Standalone (sempre visível com --headed):
python scripts/browser_smoke.py --headed

# Via pytest (abre browser visível com slow_mo 300ms por ação):
$env:SUPEREZIO_SMOKE_HEADED = "1"
python -m pytest tests/ -q

# Velocidade customizada (ms por ação):
$env:SUPEREZIO_SMOKE_SLOW_MO = "500"
```

**Modo chat real:** Para validar o pipeline completo com resposta do Bob:
```bash
$env:SUPEREZIO_SMOKE_CHAT = "1"
python scripts/browser_smoke.py --headed
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

## Política F51 de MCPs

MCP permitido somente se cumprir pelo menos uma função:
1. Reduzir erro operacional
2. Testar produto real
3. Auditar entrega
4. Acessar documentação necessária
5. Preparar venda/demo

Proibido:
- Instalar MCP por curiosidade
- Dar acesso amplo ao filesystem
- Usar token com escopo exagerado
- Deixar MCP sem descrição no AGENTS.md/CLAUDE.md

### MCPs Registrados e Autorizados
- `chrome-devtools-plugin` / `chrome_devtools`: Avaliação e execução de scripts em sessões locais do Chrome para testes de UI e depuração do frontend do SuperEzio.

