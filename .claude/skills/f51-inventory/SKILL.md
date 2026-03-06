---
name: f51-inventory
description: "Mapeia estrutura, entrypoints, comandos reais e estado atual antes de qualquer implementação."
compatibility: "SuperEzio v3+"
allowed-tools: "Read, LS, Search, Terminal (read-only), JSON"
related-skills: [f51-contracts, f51-runtime, f51-tests]
---

# f51-inventory

## Quando usar
- Início de tarefa nova
- Repositório alterado sem checkpoint recente
- Antes de qualquer mudança estrutural

## Entregáveis mínimos
- Inventário atualizado em `.f51/INVENTORY_TEMPLATE.json` (ou derivado operacional)
- Lista de entrypoints e comandos válidos
- Riscos iniciais documentados em `.f51/RISK_REGISTER.md`
- Checkpoint atualizado em `.f51/checkpoints/latest.json`

## Regras
- Não implementar feature.
- Não alterar código de produto.
- Priorizar fatos observáveis e comandos executáveis.
