---
name: f51-executor
description: "Executa patches pequenos com teste e evidência. Triggers: patch, fix rápido, executor, aplicar mudança, comando único, tarefa cirúrgica."
compatibility: "SuperEzio bootstrap layer"
allowed-tools: "Read, Edit, Write, Bash, Grep, Glob"
depends-on: [f51-impact-map]
related-skills: [f51-quality-gate, f51-regression-hunter]
---

# f51-executor

## Quando usar

- Patch cirúrgico de 1-3 arquivos
- Fix de bug com escopo claro
- Ajuste de configuração ou import
- Qualquer mudança que cabe em uma sentada

## Nunca fazer

- Refatorar além do escopo do patch
- Adicionar feature junto com fix
- Declarar sucesso sem rodar teste
- Editar sem mapear impacto antes (usar f51-impact-map)
- Abrir mais de 3 arquivos sem justificativa explícita

## Workflow

1. Confirmar escopo: o que muda, o que NÃO muda.
2. Mapear impacto mínimo (pode ser mental para patch trivial).
3. Aplicar patch cirúrgico — menor mudança que resolve.
4. Rodar teste ou verificação disponível.
5. Entregar: arquivos alterados, comandos rodados, resultado real.

## Portões de decisão

- Se o patch cresce além de 3 arquivos: parar e reportar.
- Se não existe teste para validar: reportar explicitamente.

## Entregáveis mínimos

```
== F51 EXECUTOR REPORT ==

## Escopo
- Problema: [uma linha]
- Arquivos alterados: [lista]

## Mudanças
- [arquivo]: [o que mudou e por quê]

## Verificação
- Comando: [o que rodou]
- Resultado: [pass/fail/skip + output relevante]

## Riscos remanescentes
- [se houver]

## Checkpoint
- [atualizado / não aplicável]
```

- Arquivos alterados com motivo
- Comandos executados com resultado real
- Checkpoint atualizado em `.f51/checkpoints/latest.json` (quando aplicável)

## Regras

- Patch mínimo. Sem refatoração extra.
- Sem teste, sem "passou".
- Entregar evidência, não promessa.
