# Fase 4b — Correção: Isolamento real de dados por especialista

Gerado: 2026-07-19
Escopo: `src/core/pipeline/nodes/experts.py`
Depende de: `phase4_expert_isolation.md` (achado original)
Pesquisa base: TradingAgents (Xiao et al., arXiv:2412.20138, TauricResearch), FinRobot
(AI4Finance-Foundation, arXiv:2405.14767), AIMM (arXiv:2512.16103).

## O que mudou

A Fase 4 encontrou que todos os especialistas, red team, juízes e auditor recebiam a mesma
`data_context` bruta, sem filtragem, e que o juiz não via os vereditos dos especialistas —
contradizendo a arquitetura descrita ("momentum não vê notícias", "só o juiz recebe tudo").

Implementado:

1. **`EXPERT_CONTEXT_MODULES`**: mapa role → tupla de módulos do `math_report` que aquele role
   pode ver. Ex.: `momentum_technical` vê `technical_indicators`/`price_series`/`penny_momentum`,
   NÃO vê `dcf_proxy` (fundamental) nem `crisis_aggregate` (macro). `sentiment` e
   `social_forensics` deliberadamente não veem `technical_indicators` — inspirado no design da
   AIMM, que pontua manipulação a partir de sinais de coordenação/engajamento + preço-volume cru,
   não de indicadores técnicos (para não deixar o analista social racionalizar um padrão de
   gráfico em vez de evidência real de coordenação).

2. **`build_role_context(role, math_report, raw_context)`**: fatia `math_report["modules"]`
   pelos módulos permitidos ao role, formata como texto compacto. Roles sem entrada no mapa
   (red team, roles desconhecidos) mantêm o comportamento anterior (contexto completo) — não
   quebra nada que já funcionava, só resolve os 6 roles nomeados.

3. **`build_judge_context(expert_results)`**: para `judge_agent_*`/`auditor_agent`/provider
   `daytrade_judge`/`daytrade_auditor`, monta um resumo estruturado dos vereditos dos
   especialistas (role, verdict, confidence, top_signals, top_risks) em vez de reenviar o
   `data_context` bruto. Agora o juiz de fato arbitra os vereditos, não repete a mesma análise
   pela sétima vez.

4. **`node_expert`** foi alterado para escolher `build_judge_context` (roles de arbitragem) ou
   `build_role_context` (analistas nomeados) em vez de usar `state["data_context"]` cru
   diretamente. `state["math_report"]` e `state["expert_results"]` já chegavam disponíveis via
   `{**working_state, ...}` em `graph.py` — não foi necessário alterar `graph.py`.

5. **Prompts reescritos** (`EXPERT_PROMPTS`) para cada um dos 6 roles, com:
   - Referência explícita ao papel equivalente em TradingAgents (Fundamentals/Technical/
     Sentiment Analyst, Risk Manager, Bear Researcher para o contrarian).
   - Um "anti-guessing contract" comum (`_ANTI_GUESSING_CONTRACT`) instruindo cada expert a
     declarar `NO_DATA` em vez de inventar número que não está na sua seção — e a nunca afirmar
     preço/ratio/percentual fora do que recebeu.
   - `NO_DATA` adicionado como valor de `verdict` em todos os 6 schemas (antes só alguns tinham).

## Por que isso resolve o achado original

- `momentum_technical` agora **não recebe** `crisis_aggregate`/`dcf_proxy` — logo não pode mais
  "ver notícias/macro" mesmo se estivessem no `data_context` bruto.
- `sentiment`/`social_forensics` agora **não recebem** `technical_indicators` — resolve
  especificamente o caso que a Fase 4 citou.
- O juiz agora recebe `expert_results` resumido, não o pacote de mercado cru — resolve
  "só o juiz recebe tudo no final" (tudo = os vereditos, não os dados brutos de novo).

## O que NÃO foi resolvido nesta correção (fora de escopo, registrado)

- **Réplicas** (`SUPEREZIO_EXPERT_REPLICAS`) continuam rodando o mesmo role com o mesmo contexto
  fatiado — isso mede variância de amostragem do modelo, não diversidade informacional. Não é
  um bug, é uma limitação conhecida do "mesmo cérebro" que o operador apontou; resolver isso
  exigiria trocar de provedor por role (custo/complexidade maior), fora do escopo desta correção.
- O red team (`red_team_agent_N`) ainda usa o fallback genérico com `context[:3000]` sem
  segmentação — não tinha um role nomeado equivalente nos 6 experts, decisão consciente de não
  inventar uma taxonomia de dados para ele nesta rodada.
- Nenhuma chamada real ao DeepSeek foi feita para validar a qualidade das respostas com os novos
  prompts — isso requer o servidor/API configurados, fora do alcance desta sessão (paper-only,
  sem credenciais ativas verificadas).

## Verificação

```
python -m py_compile src\core\pipeline\nodes\experts.py   → exit 0
python -m pytest tests/ -k "math_hub or gateway or expert_dialogue or providers or experts or trinity or contract_experts" -q
  → 84 passed, 0 failed
python -m pytest tests/ -q --ignore=tests/test_property_f51.py
  → 498 passed, 5 failed (mesmas 5 falhas pré-existentes confirmadas via git stash antes desta sessão), 2 skipped
```

Nenhuma regressão nova introduzida.
