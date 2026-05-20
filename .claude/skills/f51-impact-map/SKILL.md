---
name: f51-impact-map
description: Mapeia arquitetura e superfície de risco antes de qualquer edição. Essencial antes de mudanças em sistemas críticos.
---

Antes de editar qualquer arquivo:
1. descreva o problema
2. identifique a arquitetura tocada
3. liste arquivos que devem mudar
4. liste arquivos indiretamente afetados
5. liste o que pode quebrar
6. proponha o menor patch seguro
7. proponha comandos de verificação

## Nunca fazer

- Editar código durante o mapeamento de impacto
- Pular o mapeamento porque "é mudança simples"
- Inventar arquivos ou dependências sem verificar com Grep/Glob
- Ignorar efeitos colaterais em testes ou configs

## Checkpoint
- Atualizar `.f51/checkpoints/latest.json` com mapa de impacto e riscos identificados.

Responda com:

## F51 IMPACT MAP

### Problema
[uma linha]

### Arquitetura Tocada
- [módulo / camada / serviço]

### Arquivos a Alterar
- [arquivo] — [motivo]

### Afetados Indiretamente
- [arquivo] — [risco]

### O Que Pode Quebrar
- [cenário]

### Menor Patch Seguro
[descrição]

### Verificação
- [comando]