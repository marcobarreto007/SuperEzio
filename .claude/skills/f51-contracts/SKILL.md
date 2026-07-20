---
name: f51-contracts
description: "Use quando validar APIs, schemas, assinaturas, formatos de resposta, paths públicos e interfaces antes de qualquer mudança funcional. Triggers: contratos, contracts, schema, assinatura pública, compatibilidade, interface."
compatibility: "SuperEzio bootstrap layer"
allowed-tools: "Read, Grep, Tests, JSON, Diff"
depends-on: [f51-inventory]
related-skills: [f51-refactor, f51-tests, f51-audit]
---

# f51-contracts

## Quando usar

- Antes de editar APIs, schemas, assinaturas públicas ou formatos de saída
- Antes de refatoração com potencial de quebra
- Quando houver dúvida sobre compatibilidade retroativa

## Nunca fazer

- Aceitar mudança silenciosa de contrato
- Misturar validação de contrato com feature não autorizada

## Workflow

1. Ler o baseline de inventário e identificar a superfície pública relevante.
2. Mapear contratos afetados: APIs, schemas, CLI args, env vars, caminhos e formatos de arquivo.
3. Classificar risco de compatibilidade e explicitar o que pode quebrar.
4. Definir validações necessárias: testes, checks estáticos, diffs de contrato, rollback.
5. Atualizar evidência e checkpoint antes de liberar qualquer edição dependente.

## Portões de decisão

- Se houver mudança pública sem aprovação explícita, bloquear.
- Se não existir plano de rollback ou validação, não prosseguir.

## Entregáveis mínimos

- Mapa de contratos afetados
- Risco de quebra e plano de rollback
- Evidência de validação de contrato (testes/checagens)
- Checkpoint atualizado em `.f51/checkpoints/latest.json`

## Regras

- Mudança de contrato sem gate explícito: bloqueada.
- Sem mudanças silenciosas em comportamento público.
- Compatibilidade deve ser tratada como requisito, não como detalhe.
