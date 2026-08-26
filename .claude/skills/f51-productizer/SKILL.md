---
name: f51-productizer
description: "Transforma projeto técnico em produto vendável. Triggers: monetizar, productizar, empacotar, pricing, MVP, o que cobrar, como vender, entrega mínima vendável."
compatibility: "SuperEzio bootstrap layer"
allowed-tools: "Read, Grep, Glob, Bash (read-only)"
depends-on: [f51-inventory, f51-money-gate]
related-skills: [f51-doc-sync]
---

# f51-productizer

## Quando usar

- Quando o projeto técnico está funcional e precisa virar produto
- Antes de definir pricing, packaging ou go-to-market
- Quando há dúvida sobre o que cortar vs. o que vender
- Antes de investir tempo em feature que pode não dar dinheiro

## Nunca fazer

- Prometer feature que não existe como se fosse produto
- Definir pricing sem saber o custo de entrega
- Ignorar quem é o comprador real
- Empacotar tudo em vez de focar na entrega mínima vendável
- Adicionar feature de produto durante a análise de monetização

## Workflow

1. Mapear o que o projeto faz de fato (código real, não plano).
2. Identificar quem compra, qual dor resolve e quanto cobrar.
3. Definir entrega mínima vendável: o menor conjunto que alguém paga.
4. Listar o que cortar porque não dá dinheiro agora.
5. Definir como empacotar (SaaS, API, CLI, licença, serviço).
6. Atualizar checkpoint com decisão de monetização.

## Portões de decisão

- Se não consegue responder "quem compra", o produto não está pronto para monetização.
- Se a entrega mínima vendável precisa de 3+ sprints, o escopo está grande demais.

## Entregáveis mínimos

```
== F51 PRODUCTIZER REPORT ==

## O que o projeto faz (código real)
- [lista de capacidades comprovadas]

## Quem compra
- [persona ou segmento]

## Qual dor resolve
- [problema específico]

## Pricing sugerido
- [modelo + faixa de preço + justificativa]

## Entrega mínima vendável
- [lista de features que vão na V1]

## O que cortar (não dá dinheiro agora)
- [lista com motivo]

## Como empacotar
- [formato de entrega]

## Ação seguinte
- [próximo passo mínimo seguro]

## Checkpoint
- [atualizado com decisão]
```

- Resposta às 6 perguntas obrigatórias
- Entrega mínima vendável definida
- O que cortar justificado
- Checkpoint atualizado em `.f51/checkpoints/latest.json`

## Regras

- Produto é o que alguém paga, não o que é técnico.
- Cortar é mais importante que adicionar.
- Se não sabe quem compra, não sabe o que vender.
