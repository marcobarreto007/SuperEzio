# Intel — "DeepSeek Agent Hermes" (colhido 2026-08-18)

**Pergunta do operador:** "DeepSeek lançou o DeepSeek Agent Hermes esta semana — pesquisa."
**Resposta curta:** não existe um produto "DeepSeek Agent Hermes". O nome funde duas coisas distintas — uma delas lançada esta semana, a outra não é da DeepSeek.

## O que é real (verificado por busca, 2 queries)

### 1. DeepSeek V4-Pro (0813) — GA em 12-13/08/2026 (isto sim é desta semana)
- Flagship da DeepSeek saiu do preview (~4 meses) e virou GA como `deepseek-v4-pro` (app, web, API).
- Foco: **melhorias em tool usage e tarefas de agente**, "flexible reasoning effort", compatibilidade Codex/Responses API.
- Integrações agênticas citadas: Claude Code, OpenClaw, OpenCode.
- Preço novo em vigor desde 16/08 16:00 UTC: ~$0.435/1M input, ~$0.87/1M output (cache-hit $0.003625).
- Aliases legados de modelo aposentados em 24/07 (eram redirecionados em silêncio p/ V4 Flash).

### 2. Hermes Agent — NÃO é da DeepSeek
- Agente open-source da **Nous Research**; a DeepSeek só documenta como integrar o Hermes com a API deles (`api-docs.deepseek.com/quick_start/agent_integrations/hermes`).
- Comunidade usa Hermes + DeepSeek V4 Flash como alternativa barata/grátis a Claude/OpenAI.

### 3. "DeepSeek Harness" (não verificado)
- Um comparativo em vídeo cita um "harness" da DeepSeek com 113k estrelas GitHub em 2 dias — fonte única, não confirmado antes da colheita ser encerrada. Tratar como rumor até confirmação.

## Nota de segurança (relevante para nós)
- Ator de ameaça na China usou DeepSeek via Hermes Agent para **campanha de hacking autônomo** (460+ alvos a partir de uma única instrução por Telegram) — Cybersecurity Dive / The Hacker News, jul/2026.
- Lição de arquitetura: agente + LLM com poder de ferramenta = vetor. Reforça o padrão que adotamos (menor privilégio por folha, auditor read-only, stop-and-surface — `docs/architecture/AGENT_PATTERNS_ANTHROPIC_FS.md`).

## Relevância para o SuperEzio

| Item | Posição |
|---|---|
| V4-Pro na API DeepSeek | **Zero-cloud (2026-08-17) proíbe.** Nada a adotar no gateway. O nome "deepseek" no nosso providers.py é rota local (:8080), não o serviço deles. |
| Chave antiga de DeepSeek | Ainda não revogada? **Revogar** — com o reajuste de preço em 16/08, chave ativa = faturável. (Registrado no RISK_REGISTER.) |
| Hermes Agent (open-source) | Framework de agente, não modelo. Nada identificado que sobre nossa arquitetura atual (padrão Anthropic FS + trio market-*). Reavaliar só se surgir caso de uso. |
| Rumor "DeepSeek Harness" | Sem ação. |

**Conclusão:** nenhum impacto no SuperEzio. Diretiva zero-cloud intacta; única ação pendente do operador continua sendo revogar a chave DeepSeek antiga.

## Fontes
- DeepSeek API Docs — integração Hermes: https://api-docs.deepseek.com/quick_start/agent_integrations/hermes
- DeepSeek API Docs — changelog (preços 16/08): https://api-docs.deepseek.com/updates/
- Anúncio V4-Pro: https://api-docs.deepseek.com/news/news260813
- Quartz: https://qz.com/deepseek-v4-pro-official-launch-081326
- Yahoo Tech: https://tech.yahoo.com/ai/articles/deepseek-officially-launches-v4-pro-181255468.html
- Cybersecurity Dive (hacking autônomo): https://www.cybersecuritydive.com/news/china-based-hacker-deepseek-autonomous/826784/
- The Hacker News: https://thehackernews.com/2026/07/chinese-hacker-commands-deepseek-via.html
