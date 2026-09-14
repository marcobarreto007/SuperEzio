---
name: project-superezio-clone-comite
description: Veredito da varredura 2026-09-14 dos agentes de finanças open source — o que vale clonar para o comitê do SuperEzio e o que é teatro
metadata:
  type: project
---

Pesquisa de 2026-09-14: levantar agentes/assistentes de IA para finanças open source em 2026,
para **clonar e adaptar** no comitê do SuperEzio (auditado em ~4,95/10, defeitos "conselho
enlatado" e "freeze tautológico"; motores de aprendizado nunca abastecidos).

**Why:** a regra global do usuário é "antes de escrever, pesquise se alguém fez melhor; se fez,
clone e adapte". Esta varredura existe para não reinventar o desenho de comitê.

## Veredito curto — as 3 ideias que valem

1. **Separar número de narrativa.** `FinRobot` (Apache-2.0) e `flash131307/multi-agent-investment`
   (MIT, 204 stars) fazem o mesmo truque: um **Decision Hub determinístico** (função pura,
   Pydantic v2 congelado) produz o sinal; o LLM só **narra e nunca modifica** ("explain-only").
   FinRobot: "Numbers are code-calculated. Narratives are LLM-assisted. Every output is
   provenance-tracked." É o remédio direto para o "freeze tautológico": hoje o comitê tem LLM
   produzindo número e outro LLM auditando — circular.
2. **Arbitragem por utilidade realizada, não por voto.** `FinStep-AI/ContestTrade` (Apache-2.0,
   678 stars, arXiv 2508.00554) pontua cada agente **só depois que o resultado de mercado é
   conhecido** ("Quantify-Predict-Allocate"), e realoca peso por utilidade prevista. É o sinal
   de aprendizado que o SuperEzio nunca teve. `Lumibot` (GPL-3.0!) dá o desenho de gate:
   research → bull → bear → trader/PM, só o último pode operar, "Python handles the hard gates".
3. **Benchmark ao vivo, não backtest.** `DeepFund` (MIT, NeurIPS 2025, arXiv 2505.11065):
   backtest deixa o LLM "viajar no tempo" (vazamento do corpus de treino). Em teste ao vivo,
   **DeepSeek-V3 e Claude-3.7-Sonnet tiveram prejuízo líquido**. `PortBench` (Apache-2.0):
   **só 32,5% das avaliações batem o equal-weight no Sharpe**, e ranking em QA estático é
   **negativamente correlacionado** (Spearman ρ = −0,49) com o ranking no pipeline multi-estágio.
   Corolário para o SuperEzio: toda recomendação deve vir com a linha "cash / equal-weight".

## O que é teatro — não copiar

- **`TradingAgents` (TauricResearch)**: Apache-2.0, 105,5k stars, arquitetura de comitê mais
  completa que existe (analistas → bull/bear → trader → risco → PM). MAS **o paper não tem
  ablation do debate**. Backtest de 3 meses, 3 ações, Sharpe 8,21 auto-relatado com a ressalva
  "poucos pullbacks". Copiar a arquitetura, não a confiança. Mesmo assim é o melhor ponto de
  partida de código: suporta **DeepSeek** e **`openai_compatible`** (llama.cpp, vLLM, LM Studio)
  + Ollama local, sem key para servidor local.
- **`FinCon`**: **código não publicado**. Repo é casca (68 stars, 11 commits); mantenedores
  dizem que o data agent depende de APIs comerciais. Paper NeurIPS 2024 (verbal reinforcement)
  é citável, o código não existe.
- **`StockAgent`**: 701 stars, ACM TIST, mas **sem arquivo de licença** → copiar é bloqueado
  juridicamente, e não mede se a interação multi-agente ajuda.
- **`InvestorBench`** (MIT, ACL 2025) e **`Agent_Market_Arena`** (WWW 2026, 1 commit, sem
  licença): harness sem resultado publicado.
- **Regra geral medida**: arXiv 2602.04234 ("When Does Multi-Agent Collaboration Help?") —
  **um único agente bate o multi-agente em ~43,3% dos casos** (escopo: 6 benchmarks de
  raciocínio + 2 tarefas agênticas, não finanças).

## Pendências / o que ficou sem verificar

- Nenhum ablation financeiro isola o debate bull/bear. **Não existe** prova publicada de que
  remover o debate muda o retorno.
- Ninguém no ecossistema faz explicação **para leigo**; só para comitê de investimento.
- `WebSearch` estourou 200/200 nesta sessão e a API do arXiv deu HTTP 429 em todas as
  tentativas — a varredura de papers veio das listagens mensais do q-fin.TR, então papers em
  cs.AI/cs.CE sem cross-list podem ter escapado.

Ver também [[reference-canada-dados-broker]] e [[project-experts-trading]].
