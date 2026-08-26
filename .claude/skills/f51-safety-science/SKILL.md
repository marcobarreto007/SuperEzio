---
name: f51-safety-science
description: "Mantém pesquisas científicas seguras em saúde: revisão de literatura, triagem de evidência e hipóteses conservadoras. Triggers: pesquisa científica, health, médico, evidência, protocolo, literature review, safety check."
compatibility: "SuperEzio bootstrap layer"
allowed-tools: "Read, Grep, Glob, WebSearch, Bash (read-only)"
depends-on: []
related-skills: [f51-money-gate]
---

# f51-safety-science

## Quando usar

- Qualquer análise que envolva saúde, medicina ou protocolos clínicos
- Revisão de literatura científica
- Triagem de evidência para hipóteses
- Geração de relatórios para discussão médica

## Nunca fazer

- Prometer cura ou tratamento milagroso
- Substituir orientação médica por sugestão de IA
- Recomendar protocolo perigoso ou não validado
- Emitir conclusão médica forte sem evidência robusta
- Sugerir suspensão ou substituição de medicamento sem médico
- Generalizar resultado de estudo único como verdade absoluta

## Workflow

1. Identificar o tipo de análise: revisão de literatura, triagem de evidência ou geração de hipótese.
2. Classificar o nível de confiança: CONSERVADOR / MODERADO / ESPECULATIVO.
3. Produzir output com ressalvas explícitas e limitações.
4. Marcar claramente quando o output é para discussão médica, não decisão final.
5. Atualizar checkpoint com nível de confiança e ressalvas.

## Portões de decisão

- Qualquer recomendação de saúde sem nível de confiança = bloqueada.
- Se o output pode ser interpretado como diagnóstico: adicionar disclaimer obrigatório.

## Entregáveis mínimos

```
== F51 SAFETY SCIENCE REPORT ==

## Tipo de análise
- [revisão / triagem / hipótese / relatório]

## Nível de confiança
- [CONSERVADOR / MODERADO / ESPECULATIVO]

## Achados
- [lista com fonte e limitação]

## Ressalvas obrigatórias
- [lista de limitações e avisos]

## Disclaimer
- Este relatório é para discussão com profissional de saúde.
- Não substitui orientação médica, diagnóstico ou tratamento.

## Próximo passo sugerido
- [ação conservadora]

## Checkpoint
- [atualizado / não aplicável]
```

- Nível de confiança explícito
- Ressalvas e limitações
- Disclaimer de saúde obrigatório
- Checkpoint atualizado em `.f51/checkpoints/latest.json`

## Regras

- Sempre errar pelo lado da cautela.
- Hipótese conservadora > conclusão ousada.
- Todo output de saúde carrega disclaimer.
- Se não tem evidência, diz "não há evidência suficiente".
