# SuperEzio Financeiro Roadmap — Bob Core Runtime

**Atualizado em 2026-09-19.** Fonte canônica de topologia: `config/runtime.yml` e
`config/model_manifest.json`. O **estado operacional vivo** (como sobe, portas, o que não está no
git, armadilhas) fica em `~/.mapa/projetos/superezio.md` — este documento é de **direção**, não de
estado.

## Estado Atual

- **Runtime:** API/UI em `127.0.0.1:8002`. O servidor LLM `:8080` **não é deste repositório** — quem
  sobe é o **mike**; o alias servido é `f51-local` (Ornith-1.5-35B-A3B por baixo).
- **Modelos de IA: 100% em nuvem**, na API oficial `https://api.deepseek.com`, com separação por
  papel desde 12/09/2026 — quem decide (Bob/CEO e orquestrador) roda `deepseek-v4-pro`; experts,
  judge e auditor rodam `deepseek-v4-flash`. Z.ai GLM-5.3 é caminho opcional, religável por env.
  *(O documento anterior dizia "runtime híbrido com o CEO local" e experts no V4 Pro — ambos
  deixaram de ser verdade em 12/09.)*
- **Modo de produto:** pesquisa e validação paper (`mission.phase = research_paper_validation_only`).
  A apprenticeship de 14 dias do IBKR paper está **expirada**.
- **Broker: offline.** Medido em 19/09: `runtime_broker.status = offline`, `paper = false`,
  `equity = null`. Sem execução.
- **Fontes externas: liberadas.** A política DISK ONLY foi **revogada em 14/09/2026** (regra 1 do
  `CLAUDE.md`, override registrado em `.f51/checkpoints/latest.json`). Pode buscar, clonar, instalar
  e adotar de qualquer fonte sem pedir OK. A única exceção é **gastar dinheiro**.

## P0 — Pronto Para Demo Local

- [x] Consolidar o runtime no cérebro local compartilhado em `127.0.0.1:8080`.
- [x] Remover fallback de LLM em nuvem das superfícies ativas de runtime.
      *(Superado em 12/09: a decisão mudou para 100% nuvem — ver Estado Atual.)*
- [x] Corrigir o contrato oficial de runtime para o endpoint compartilhado.
- [x] Corrigir shim legado `core.pipeline.nodes.collect_experts`.
- [x] Corrigir smoke de browser para a UI atual (`#user-inp`, `msg-ceo`).
- [x] Corrigir botão de chart para chamar `loadChart()` sem passar evento bruto.
- [x] Corrigir `/cockpit/portfolio` e `/health/details` para não marcar broker como paper conectado
      quando o snapshot vivo está offline.
- [x] Reiniciar a API e validar `/health`, `/health/details`, chart e chat — **19/09**.
- [x] **`DATA: DEGRADADO` no rodapé** — não era dado ruim, era campo ausente: o payload do
      chart-data nunca teve carimbo de tempo, e o front só sabia dizer "degradado". Corrigido nos
      dois lados e no ar — **19/09** (`73fa115e`).
- [ ] Rodar browser smoke completo com chat.

## P1 — Gates De Qualidade

- [x] `python -m ruff check src tests` — limpo, 19/09.
- [x] `python -m ruff format --check src tests` — limpo, 19/09.
- [x] `python -m pytest tests -q` — **3139 passed, 3 skipped, exit 0** (859s), 19/09.
- [x] Suíte completa não quebra na coleta.
- [x] Contratos e smokes focados passam.

## P2 — Broker E Execução Paper

- [ ] Abrir o IB Gateway paper. ⚠️ A porta é **`4002`** (`start.ps1:120` define `IBKR_PORT`) — este
      documento citava `7497`, que é de outra configuração.
- [ ] Confirmar `scripts/broker_readiness_probe.py --provider ibkr --json --timeout 5`.
- [ ] Só depois disso permitir `paper_order_enabled`.
- [ ] Manter `can_submit_orders=false` quando a probe real falhar.
- [ ] Registrar toda hipótese paper no PaperJournal com estado `research_only` enquanto o broker
      estiver offline.
- [ ] 🔴 **`TD` não é commission-free.** Medido em 19/09: `td_commission_eligibility('TD','TSX')` →
      `NOT_LISTED`. O cockpit analisa, por padrão, um ativo que **fura a própria regra de taxa
      zero**, e nada na tela avisa. Ou o default muda, ou a tela diz.
- [ ] 🔴 **Toda ordem do caminho autônomo morre no gate.** `auto_execute_paper.py:405-415` monta os
      args **sem** o alvo; `tool_executor.py:493-499` lê o alvo **só** dos args → `None` →
      `execution_policy.py:162-166` bloqueia. O alvo existe (`auto_execute_paper.py:982-995`, 2,5× o
      stop) e vai só para o journal. **É seguro — e é beco sem saída.** Decisão: consertar o alvo ou
      assumir o beco.
- [ ] **Sufixo `.TO`.** Os prompts mandam escolher *"VFV.TO, XEQT.TO, ZEB.TO"*
      (`strategy_speech.py:152,159,169`) e `is_commission_free` só faz `strip().upper()`
      (`td_universe.py:163-167`) — `VFV` está no universo, **`VFV.TO` não**. Normalizar o sufixo, ou
      parar de sugerir `.TO` nos prompts.

## P3 — Treino E Avaliação — **NÃO APLICÁVEL NO ESTADO ATUAL**

Os modelos passaram a ser 100% em nuvem (12/09/2026), então treinar LoRA local saiu da rota do
produto. Os itens abaixo ficam como **histórico**: não são trabalho pendente. Reabrir só se o treino
local voltar a ser decisão de arquitetura.

- [~] Avaliar qualidade da LoRA best com prompts de tool-calling, broker offline e negações.
- [~] Se rodar novo treino longo, usar checkpoint periódico e registrar hash final.
- [~] Promover adapter apenas depois de eval de resposta, não só loss/hash.

> **Um item desta lista não era de treino:** *"corrigir roteamento de negação — 'não recomende
> compra' não pode virar scan de oportunidades"* é comportamento de **runtime**, e continua valendo
> independentemente de haver treino. Ele foi movido para P2 (ver último item de lá) — se não foi,
> trate como pendente.

## P4 — Limpeza Histórica E Segurança

- [ ] Arquivar ou renomear scripts legados de treino/bench que ainda citam nomes de modelo antigos.
- [ ] Separar whitepapers/carreira/Nitro históricos da documentação ativa do produto.
- [ ] Manter checkpoints antigos como evidência, mas fora da rota operacional padrão.
- [ ] Atualizar guias de comprador/setup para Bob Core.
- [ ] 🔴 **Rotacionar os tokens.** `runtime/test_token.json` foi rastreado e empurrado desde 20/07
      (`d02f0c40`); saiu do índice em 18/09 (`844b7e8c`), mas **a origem não foi rotacionada** —
      corrigir o git não corrige o vazamento. **Ação do dono.** Há token HF hardcoded em 14
      arquivos, ainda não checados.
- [ ] 🔴 **O manifest TD vence ~26/09** (`MAX_AGE_DAYS=7` + `verified_at` 19/09). A correção de 19/09
      é verdadeira hoje e **não é durável** — decidir entre injetar o relógio ou renovar o manifest
      a cada ciclo.
- [ ] **Frestas medidas** — nenhuma aprova ordem sozinha, mas cada uma é uma porta: o preflight do
      kill switch é melhor-esforço (exceção só loga e segue); bypass de comissão por cota free-trade
      desenhado **sem produtor**; `td_universe.py:151-155` tem `@lru_cache` lendo o JSON sem validação
      de idade; `STOP_LIMIT` passa na sobrevivência mas a env exige exatamente `"LMT"`;
      `#statusbar-deep` tem **dois escritores** e quem renderiza por último vence.

## Critério De Pronto

O sistema só deve ser chamado de pronto quando:

- A API sobe em `127.0.0.1:8002` e `/health` responde 200 **com corpo próprio** — porta aberta não é
  serviço de pé.
- O cérebro local (`:8080`, servido pelo **mike**) responde — ou o sistema opera declaradamente sem
  ele, já que os modelos de decisão estão em nuvem.
- `/health/details` não contradiz a probe real do broker.
- Chart renderiza no browser.
- `/task/submit` chega em `STREAM_END` com resposta coerente ao intent.
- Ruff passa (`check` **e** `format --check`).
- Contratos oficiais e smokes focados passam.
- A suíte completa passa inteira, sem quebra de coleta.
