# Agent Lab — Melhora o exército de agentes

Goal: Testar, comparar e evoluir os agentes do SuperEzio.

## Ciclo de evolução
1. Identificar agente fraco (via agent-explorer)
2. Criar agente candidato em `.claude/agents/`
3. Rodar mesma tarefa com agente atual E candidato
4. Comparar evidências (não opiniões)
5. Se candidato vencer → promover para active
6. Mover perdedor para `.claude/agents/deprecated/`
7. Savekeeper registra a troca

## Tarefa de benchmark sugerida
"Auditar o estado atual do projeto e reportar 3 riscos com evidência"

## Métrica de vitória
Agente vence se tiver MAIS:
- Evidências citadas (arquivo:linha)
- Riscos reais encontrados
- Ações verificáveis sugeridas

E MENOS:
- Afirmações sem evidência
- Alucinações
- Repetição de outros agentes

## Estados de agente
- `candidate` — novo, experimental, roda em paralelo
- `active` — confiável, chamado em swarm normal
- `elite` — excepcional, usado em releases
- `deprecated` — movido para `deprecated/`, não deletado

## Template de substituição
```text
Problema: [agente] falhou em [critério]
Candidato: [novo agente]
Tarefa teste: [descrição]
Resultado atual: [score]
Resultado candidato: [score]
Decisão: [promote/retry/reject]
```
