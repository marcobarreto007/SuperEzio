# Roadmap — SuperEzio como Consultor Financeiro em Linguagem Natural

Atualizado: 2026-07-19
Objetivo definido pelo operador: "um consultor em tempo real em linguagem natural, um amigo
correto e matemático". Não é um sistema de day-trade automatizado — é um copiloto que
conversa, explica, calcula certo, e nunca inventa fato.

Este documento complementa (não substitui) `ROADMAP.md` (focado em infraestrutura/deploy do
runtime) e consolida achados de `docs/audit/phase1-8` + testes ao vivo realizados nesta sessão
(19/07/2026, servidor real rodando, requests reais via `/task/submit`).

## O fluxo completo, testado ao vivo hoje

```
Usuário (UI web ou API)
  → POST /task/submit (envelope A2A)
    → orchestrator_primary (regex → golden dataset → CEO LLM se disponível)
      → CASE_OPENED (tipo de caso, mandato, steps exigidos)
      → auto_full_analysis
        → MathHub (14 módulos: preço, técnicos, retorno, Sharpe, VaR, Kelly,
          DCF, crise, quantum, portfolio HRP, F51, penny momentum, trading losses)
        → node_collector (dados de mercado, se ticker presente)
        → comitê de especialistas (6 roles × N réplicas, DeepSeek)
        → red team + judge + auditor (camadas extras opcionais)
        → F51 Verdict (confidence unificada)
        → neural_decision
        → sdca_firewall (veto determinístico local)
        → guardrail_hub (30 guardrails agregados)
        → trinity (segunda opinião sentiment/fundamental, se ticker presente)
      → agent (Bob, ReAct loop, síntese final em linguagem natural)
      → explanation (streaming interpretability)
    → STREAM_END (resposta final + trace completo)
```

**Confirmado ao vivo nesta sessão**: cada etapa acima roda de verdade e produz eventos reais no
stream NDJSON — não é diagrama aspiracional, é comportamento observado com o servidor no ar.

## O que já funciona hoje (verificado, não suposto)

- **Servidor sobe e responde** (`/health`, `/health/details`, `/task/submit`) com FastAPI + streaming NDJSON real.
- **MathHub roda os 14 módulos e retorna estrutura correta** — incluindo o F51 unificado, corrigido nesta sessão (ver abaixo).
- **Gates de segurança funcionam em camada, com falha segura real**: sem CEO reachable, o sistema entra sozinho em `MAN_AT_WORK` mode e bloqueia ordens ("NO TRADING ORDERS UNTIL CLEARED") — isso é uma proteção autônoma genuína, não decorativa.
- **SDCA firewall roda localmente, sem rede/LLM**, produz veredito determinístico (`ALLOW`/`BLOCK`) com `human_summary` legível.
- **Guardrail hub agrega 30 guardrails** e reporta contagem de bloqueio real.
- **Fallback de síntese é honesto**: quando o agente não consegue sintetizar resposta (CEO offline), o sistema **admite isso explicitamente** em vez de fingir ("Isto é uma falha interna de síntese, não falta de detalhe no teu pedido") e ainda entrega um framework mínimo útil.
- **UI web existe e é completa**: chat, gráfico com timeframe, status de broker IBKR, SDCA lab, ops console — não é placeholder.
- **Isolamento de dados por especialista** (corrigido nesta sessão): momentum não vê mais fundamentals/macro, sentiment não vê mais indicadores técnicos — diversidade real de perspectiva, não só de prompt.

## Bugs corrigidos nesta sessão (com evidência de execução real, não só teste unitário)

1. **F51 quebrava em toda chamada real**: `DecisionFactors.__init__() got an unexpected keyword argument 'risk'` — `math_hub.py` passava `risk=` mas a classe usa `danger=`. Confirmado ao vivo via `/task/submit`, corrigido, re-testado ao vivo: `f51_unified` agora retorna `"status": "ok"`.
2. **Gates de segurança duplicados e não sincronizados** (`F51_TRADING_EXECUTION_FREEZE` vs `SUPEREZIO_LIVE_TRADING_DISABLED`) — unificados; `SUPEREZIO_LIVE_TRADING_DISABLED` agora tem default seguro (`True`).
3. **Suíte de testes inteira era frágil contra a existência de um `.env` real** — 5 testes assumiam ambiente sem env vars nunca setadas; corrigido com isolamento explícito via `monkeypatch`/fixture `autouse`.

## Bugs encontrados HOJE, ainda NÃO corrigidos

1. **`KeyError: 'provider'` nos agentes de red team** (`red_team_agent_1/2/3`) — erro genuíno de código, distinto da falta de credencial DeepSeek (que é esperada/honesta). Precisa de investigação com traceback completo dentro do contexto real do LangGraph (tentativa de reprodução isolada falhou por exigir um `runnable context` que só existe dentro do grafo real rodando). **Prioridade alta** — o red team é uma camada de veto de segurança; se ele sempre falha, essa camada de proteção está sempre ausente silenciosamente.
2. **`.f51/ENTRYPOINT_MAP.md` menciona um "14-day IBKR paper brokerage apprenticeship" com `end_date: 2026-06-19`** — já expirou há um mês. Isso é injetado no prompt do Bob como contexto de identidade; se perguntado, Bob provavelmente descreve um estado de treinamento desatualizado. Não trava nada tecnicamente, mas é uma inconsistência que o próprio "consultor" carregaria pra conversa com você.
3. Achados **P1/P2 ainda abertos** de `docs/audit/phase5-7` (não escopo desta sessão): spider_sense inconsistente no F51, critic fail-open em erro de LLM, idempotência sem marcação clara de sucesso, `exec()` dinâmico em `custom_tools.py`, cache de experts sem TTL/LRU, DataHub aceita `{}` como resultado utilizável.

## O que falta para o objetivo "consultor real" especificamente

Isto não é sobre broker/execução (que já é corretamente gateado e travado) — é sobre a
qualidade e confiabilidade da conversa em si:

### Bloqueadores diretos
- **Nenhum provider LLM está configurado** (`DEEPSEEK_API_KEY` ausente) — sem isso, os 6 especialistas + juiz + auditor + CEO nunca respondem de verdade; o sistema roda inteiramente em modo fallback matemático + mensagens genéricas. Para o objetivo de "consultor em tempo real", isto é o bloqueador nº1: sem chave de API real, o produto não conversa, só calcula.
- **CEO local (Bob Core GGUF) não existe nesta máquina** (`C:\llama.cpp\` ausente) — o orquestrador cai em modo `passthrough` (confirmado no log: `model_status: "passthrough"`), sem classificação de intenção por LLM real, só regex/golden dataset. Isso limita a qualidade de entendimento de perguntas fora do script esperado.

### Correções de qualidade (não bloqueadoras, mas relevantes ao "amigo correto")
- Corrigir o `KeyError('provider')` do red team (item acima) — sem isso, uma camada de "ele te avisa quando está errado" está ausente.
- Investigar e corrigir os achados P1 do F51 (`spider_sense`, `critic fail-open`) — um critic que falha *aberto* (aceita por padrão em erro) é o oposto de "matemático e correto"; deveria falhar fechado.
- Atualizar ou remover a referência ao apprenticeship de 14 dias expirado, para o Bob não carregar uma auto-descrição desatualizada na conversa.
- Decidir conscientemente: os especialistas com réplicas (`SUPEREZIO_EXPERT_REPLICAS=3`) usam todos o mesmo modelo (DeepSeek V4 Pro) — a "segunda opinião" mede variância de amostragem, não perspectivas de modelos diferentes. Isso é aceitável para um MVP, mas vale documentar essa limitação nas respostas que o Bob dá ao usuário quando ele perguntar "você tem certeza disso?".

### Já correto e não precisa de trabalho adicional
- A separação entre "isto é cálculo determinístico" (MathHub, SDCA) e "isto é síntese/opinião de LLM" (especialistas, CEO) já existe estruturalmente e é o padrão certo (mesmo usado por sistemas reais como FinRobot, pesquisado na sessão anterior).
- O sistema nunca finge sucesso quando falha — isso é a base certa para "amigo correto": prefere admitir "não consegui sintetizar" a inventar uma resposta.

## Critério de pronto para "consultor real" (proposto)

O sistema pode ser chamado de "consultor em tempo real" quando:

1. Ao menos um provider LLM real está configurado e respondendo (`DEEPSEEK_API_KEY` ou equivalente) — sem isso, nada abaixo importa.
2. O `KeyError('provider')` do red team está corrigido e o red team roda com taxa de sucesso mensurável.
3. Uma sessão de chat real (UI → `/task/submit` → resposta) foi conduzida pelo operador com perguntas abertas (não só "analyze TICKER") e a resposta foi julgada honesta, útil, e sem números inventados.
4. O critic do F51 falha fechado (bloqueia/rebaixa confiança) em erro de LLM, não aberto.
5. As referências desatualizadas de identidade/treinamento (apprenticeship expirado) foram corrigidas ou removidas do contexto injetado no Bob.

## Próximo passo recomendado

Configurar `DEEPSEEK_API_KEY` no `.env` (decisão do operador, é a chave de API real, não devo
pedir nem gerar) e repetir o teste ao vivo de `analyze SHOP for me` para observar a primeira
resposta real e completa do comitê de especialistas + CEO — isso vai revelar rapidamente se a
qualidade da conversa bate com "amigo correto e matemático" ou se precisa de ajuste de prompt.
