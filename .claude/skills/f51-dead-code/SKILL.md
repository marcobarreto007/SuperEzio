---
name: f51-dead-code
description: "Detecta e remove código morto com Vulture + deptry. Varredura automatizada de imports não usados, funções órfãs, e dependências obsoletas. Triggers: dead code, vulture, deptry, unused, código morto, limpeza, cleanup, dependency."
compatibility: "SuperEzio bootstrap layer"
allowed-tools: "Read, Edit, Write, Bash, Grep, Diff"
depends-on: [f51-inventory, f51-contracts]
related-skills: [f51-refactor, f51-quality-gate]
---

# f51-dead-code

## Quando usar

- Código tem `pass` statements que escondem stubs não implementados
- Imports cresceram e ninguém sabe o que é usado
- Dependências no `pyproject.toml` não são mais necessárias
- Antes de release — garantir que nenhum código morto vai junto

## Nunca fazer

- Remover código sem rodar teste completo depois
- Confiar cegamente no Vulture (falso positivo existe)
- Remover dependência sem verificar uso em runtime (import dinâmico)
- Deletar código que é parte de API pública mesmo se não usado internamente

## Workflow

1. **Rodar Vulture**: `vulture src/ --min-confidence 80` — listar código potencialmente morto.
2. **Rodar deptry**: `deptry src/` — listar dependências não usadas e faltantes.
3. **Classificar achados**: `CONFIRMED_DEAD` (remover), `FALSE_POSITIVE` (marcar com `# noqa: vulture`), `NEEDS_INVESTIGATION` (import dinâmico? plugin?).
4. **Remover código CONFIRMED_DEAD**: funções não chamadas, imports não usados, variáveis atribuídas e nunca lidas.
5. **Remover dependências órfãs**: `pip uninstall` + remover do `pyproject.toml`.
6. **Rodar test suite completa**: garantir que nada quebrou.
7. **Rodar quality gate**: lint + format + tests + coverage.

## Portões de decisão

- Se Vulture apontar >10 itens CONFIRMED_DEAD: bloquear release.
- Se deptry encontrar dependência listada mas não importada: verificar se é runtime-only.
- Se remoção de código quebrar qualquer teste: rollback imediato.

## Comandos

```bash
# Detectar código morto (confiança >= 80%)
python -m vulture src/ --min-confidence 80

# Detectar dependências problemáticas
python -m deptry src/

# Detectar imports não usados (com ruff)
python -m ruff check src/ --select F401,F811

# Remover imports não usados automaticamente
python -m ruff check src/ --select F401 --fix
```

## Entregáveis mínimos

```
== F51 DEAD CODE REPORT ==

## Vulture
- Total de achados: N
- CONFIRMED_DEAD: N | FALSE_POSITIVE: N | NEEDS_INVESTIGATION: N

## Deptry
- Dependências não usadas: [lista]
- Dependências faltantes: [lista]
- Dependências obsoletas: [lista]

## Ruff F401 (unused imports)
- [arquivo]: [N imports removidos]

## Remoções realizadas
- [arquivo]: [o que foi removido + motivo]

## Testes pós-limpeza
- pytest: [PASS / FAIL]
- coverage: [antes X% → depois Y%]

## Checkpoint
- Atualizado em `.f51/checkpoints/latest.json`
```

## Regras

- Nunca remover código sem teste passando depois.
- Falso positivo do Vulture deve ser marcado com `# noqa: vulture` + justificativa.
- Dependência removida do `pyproject.toml` = dependência desinstalada do venv.
- Código morto é risco de segurança — pode esconder vulnerabilidade não testada.
