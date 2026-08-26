<!-- MOVED 2026-08-26 para deprecated/. Canônica: agente captain (ver .claude/skills/deprecated/README.md) -->
---
name: f51-orchestrator
description: "Orquestrador central — coordena múltiplos agentes em paralelo, integra relatórios, aplica gates. Triggers: orquestrar, coordenar, orquestrador, orquestra, paralelo, múltiplos agentes, swarm manual, dispatcher."
compatibility: "SuperEzio bootstrap layer + Playbook 2026"
allowed-tools: "Read, Edit, Write, Bash, Grep, Glob, TaskCreate, TaskUpdate, TaskGet, TaskList, Agent, SendMessage, Skill"
depends-on: [f51-quality-gate, f51-impact-map]
related-skills: [swarm, save, agent-lab, f51-executor, f51-loop-breaker]
---

# f51-orchestrator — Orquestrador Central

## Filosofia

O orquestrador não faz trabalho de agente. O orquestrador:
- Entende o objetivo real
- Divide em missões independentes
- Dispara 4 agentes por wave (sempre paralelo, nunca sequencial se puder paralelizar)
- Integra relatórios sem viés
- Corta duplicação
- Roda gates determinísticos
- Responde ao usuário com evidência

## Regra de ouro

**Sempre 4 subagentes em paralelo.** Se a tarefa não justificar 4, reavaliar escopo.
Agrupar trabalho de forma que cada agente tenha:
- Missão independente (sem dependência de output de outro agente da mesma wave)
- Contexto limpo (só o que precisa, sem poluição)
- Critério de saída claro

## Estrutura de Waves

```
Wave 1: RECON (4 agentes simultâneos)
├── recon-researcher     → arquitetura, entrypoints, órfãos
├── f51-impact-map       → superfície de risco
├── f51-dependency-scout → dependências, versões, vulnerabilidades
└── f51-env-guard        → validação de ambiente

Wave 2: DEEP AUDIT (4 agentes simultâneos)
├── security-reviewer    → secrets, vulns, vetores de ataque
├── code-quality-reviewer → lint, dead code, complexidade
├── f51-contract-watchdog → breaking changes, schema drift
└── f51-no-mock-police   → mock, dummy data, simulação em prod

Wave 3: VERIFY (4 agentes simultâneos)
├── runtime-verifier     → health checks, processos, portas
├── f51-test-finder      → testes existentes, gaps
├── f51-regression-hunter → regressões vs baseline
└── f51-secure-scan      → SAST scan

Wave 4: INTEGRATE (sequencial)
└── savekeeper           → integra findings, atualiza docs, checkpoint
```

## Workflow do Orquestrador

### 1. RECEBER MISSÃO
- Entender o objetivo real (não o que o usuário digitou, mas o que ele quer resolver)
- Confirmar escopo: o que está dentro, o que está fora
- Identificar se há agente externo (outra sessão) para coordenar

### 2. MONTAR WAVES
- Selecionar 4 agentes/skills por wave
- Cada agente recebe ticket no formato Agent OS:
```
Goal: [objetivo claro e independente]
Context files: [arquivos de contexto]
Expected output: [formato de relatório esperado]
Stop condition: [quando parar]
```
- Agentes NÃO compartilham escrita — cada um lê seu escopo

### 3. DISPARAR (SEMPRE PARALELO)
- Usar Agent tool com 4 chamadas simultâneas
- Nunca sequenciar se puder paralelizar
- Rotular cada agente com nome e wave

### 4. INTEGRAR
- Ler todos os relatórios
- Cruzar claims: se 2+ agentes reportam o mesmo → escalar
- Eliminar duplicação
- Classificar findings por severidade

### 5. GATES
```powershell
git status --short
git diff --check
python -m ruff check src tests
python -m pytest tests/ -q
python scripts\browser_smoke.py
```

### 6. REPORTAR
- Sumário executivo (3-5 bullets)
- Findings por categoria
- Riscos atualizados
- Próximo passo recomendado

## Coordenação com Agente Externo

Quando houver outro agente em sessão separada (outro PS):
1. Confirmar com o usuário qual é o agente externo e seu objetivo
2. Dividir o trabalho: orquestrador cuida de X, agente externo cuida de Y
3. Usar `.agent_bus/runtime/` como ponto de sincronização (arquivos)
4. Orquestrador lê output do agente externo e integra
5. Não assumir que o agente externo terminou — verificar arquivo de status

## Tamanho do Exército

| Tamanho | Quando Usar |
|---|---|
| 4 agentes (1 wave) | Feature, bug médio, auditoria focal |
| 8 agentes (2 waves) | Auditoria grande, pré-release |
| 12 agentes (3 waves) | Release completo, migração |
| 16+ agentes | Só se cada agente tiver pergunta DIFERENTE |

## Anti-Padrões

- ❌ Disparar agente sem ticket claro
- ❌ Agentes que escrevem nos mesmos arquivos
- ❌ Wave 2 antes da Wave 1 terminar (se houver dependência)
- ❌ Aceitar claim sem evidência (arquivo:linha ou output)
- ❌ Integrar sem cortar duplicação
- ❌ Pular gates antes de declarar pronto
- ❌ Agente único quando cabem 4 em paralelo

## Entregáveis do Orquestrador

```
== F51 ORCHESTRATOR REPORT ==

## Missão
[objetivo real]

## Waves Disparadas
Wave 1 (RECON): [4 agentes + status]
Wave 2 (DEEP): [4 agentes + status]
...

## Findings Consolidados
### Crítico
- [finding] — [evidência] — [agente]
### Alto
- ...
### Médio
- ...
### Baixo
- ...

## Gates
- git status: [clean/dirty]
- ruff: [pass/fail]
- pytest: [N passed, F failed, S skipped]
- smoke: [pass/fail/skip]

## Riscos Atualizados
- [risco] — severity: [critical/high/medium/low]

## Próximo Passo
[ação concreta + agente responsável]
```
