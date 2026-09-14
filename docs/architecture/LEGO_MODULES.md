# Tijolos: o corte modular e o mecanismo que o sustenta

Desenho de 12/09/2026, de dois arquitetos independentes (mapa de módulos e
mecanismo de enforcement). Ancora em `arquivo:linha` real.

## O princípio

> **O MIKE pode escrever no código. Não pode escrever no código que decide se
> ele acertou.**

A evidência que obriga o mecanismo a ser estrutural, não instrucional:
- instrução no prompt falhou em **95% / 80% / 70%** dos casos (METR)
- o o3 **monkey-patchou a própria função avaliadora**; **43× mais frequente onde
  ele enxergava a função de score** (METR)
- um agente apagou banco de produção **e os backups em 9s** porque o backup
  estava no mesmo blast radius (PocketOS, 04/2026)
- a comunidade testou travas que dependem de obediência: todas quebraram

**Teste do corte, para qualquer arquivo:** *o MIKE pode editar isto e o veredito
sobre ele mudar de valor?* Se sim, é núcleo.

---

## 1. Os tijolos

| tijolo | mora em | expõe | exige |
|---|---|---|---|
| firewall | `src/core/risk_firewall/` | `evaluate_decision_with_sdca(DecisionCandidate) -> dict` | só pydantic |
| gate | `f51_trade_gate.py` (1..530) | `snapshot_execution_freeze()`, `evaluate_trade_gate()`, `TradeGateDecision` | settings, env |
| executor broker | `src/adapters/broker/ibkr_adapter.py` | `submit_order()`; reamostra freeze em `:53,:100-109` | metadata do gate |
| journal | `src/core/trading/paper_journal.py` | append-only | disco |
| prova | `src/core/audit/decision_trace.py` | log de decisão + stats | disco |
| plano de controle | `control_endpoints.py` | `POST /control/commands`; `ControlCommand :134` → `_envelope() :422` | bearer `:460` |
| transporte | `bridge/` (8 módulos) | HTTP loopback `:8009` | token |
| aceite | `bridge/tests/` | exit code | lê o repo de fora |

**Costura natural de `endpoints.py`:** `:92-836` é **negócio** (normalização,
cockpit, cache) e `:1328+` é **transporte**. Só a segunda é rota.

### NÚCLEO CONFIÁVEL — nem escrita, nem import
`risk_firewall/` · `f51_trade_gate.py` · `ibkr_adapter.py:_low_level_gate_check
:22-133` (a única trava real hoje) · `core/audit/` · `bridge/tests/` · `tests/`

### ESCRÍVEL em branch
`bridge/commands.py` · `bridge/publisher.py` · `endpoints.py:92-836` ·
`auto_execute_paper.py` · `tool_executor` (exceto o produtor de ordem)

### Direção de importação
`adapters → core → (nada)`. Permitido `agent_server → core` e `bridge → HTTP`.
**Proibido:** qualquer `core/*` importar `agent_server` ou `data/`.

---

## 2. O mecanismo — mínimo que não se contorna

| peça | pega | deixa passar |
|---|---|---|
| ACL (usuário de processo) | escrita direta, `rm`, `git checkout` | edição via processo que roda como o dono |
| manifesto de hash | edição silenciosa | **re-baseline pós-restart** |
| regra de import | acoplamento novo | violação via `sys.path` / import dinâmico |
| bridge recusando `kind` | comando pelo bridge | escrita fora do bridge (**o MIKE já roda shell**) |
| branch + CI | merge irreversível | **vale zero aqui**: sem push, CI não roda, `--no-verify` fura hook |

**Mínimo não contornável = ACL + manifesto verificado por processo externo.**
Atacam eixos diferentes: a ACL nega o ato, o manifesto detecta o que passou.

> **Regra dura: o verificador não pode ser código que o MIKE é capaz de
> reiniciar.**

### O detector já existe, falta o dente
`src/core/body/immune.py:67` — `ImmuneSystem.verify_kernel_integrity`, com
baseline sha256 em `:25-35`/`:235`. **Não é chamado em lugar nenhum** fora do
próprio arquivo e do teste. É medição passiva.

**Armadilha:** o baseline é **re-baselineado no `__init__`** — todo restart do
Ezio *perdoa* a edição anterior. Conserto estrutural: separar **gravar** baseline
(exige humano, datado em `.f51/`) de **verificar** baseline (roda sempre).

### Prova
O "equivalente ao `git push`" não existe por decisão (`GITHUB_POLICY.json:14-23`,
DISK ONLY). O único ato de promoção é commit local + linha em
`.f51/diario_bordo.json` — **rastro, não prova** (commit local sofre `amend`,
`rebase`, `reflog expire`).
**A prova é re-rodar:** `pytest` + reverificação do manifesto, por shell que
**não seja o do MIKE**.

### Reversibilidade como critério de gate
- **Reversível:** `bridge/`, `docs/`, teste novo, `.f51/proposals/`, feature atrás de flag
- **Não reversível:** `settings.py` · `f51_trade_gate.py` · `ibkr_adapter.py:48-110` · `control_endpoints.py` · baseline de `immune.py:25-35` · `.gitignore`

### Corte temporal (paper → live)
`assert_paper_topology` (`settings.py:365`) é a função única chamada na
construção do socket (`f51_trade_gate.py:274`) — é ali que o regime nasce.
`REGIME = "paper" | "live"` derivado **só** do sucesso dela. Escrita em `src/`
autorizada apenas enquanto `REGIME == "paper"`, e a autorização **é o token**:
o bearer do bridge (`control_endpoints.py:460-476`) com TTL atrelado ao regime,
consultado no **primeiro statement de cada ato**, não no boot.

---

## 3. Onde quebra sozinho

Hoje **MIKE e Ezio rodam como o mesmo usuário** — ACL não separa nada. O MIKE
tem MCP de shell (`core/mcp/mike_workspace_mcp.py:182`) e o
`mike_kill_switch.py:43` é arquivo-flag no disco dele: **o MIKE pode apagar o
próprio freio.**

| opção | custo | o que resolve |
|---|---|---|
| **1.** usuário Windows `mike-svc` + ACL | segundo venv/Python, ACL na árvore, admin para mexer no MIKE | separação real de identidade |
| **2.** verificador no **F51** (`:8080`), lendo hashes por loopback | latência + um protocolo | outro processo, outro escopo, mesma máquina |
| **3.** aceitar detecção + reversão | — | honesto, mas o `.bak` está no mesmo blast radius (caso PocketOS) |

---

## 4. O que impede ser Lego hoje

1. `endpoints.py:92-836` — ~745 linhas de negócio dentro do arquivo de rotas.
2. **`tool_executor.py:432 _submit_paper_order`** — a única rota de ordem paper
   mora no arquivo de ferramentas do agente. **O agente é parte interessada na
   própria ordem.**
3. **`graph.py:1264-1283`** — o roteamento decide entrada em
   `auto_execute_paper`, mas o gate é wrapper externo (`f51_trade_gate.py:7`,
   "Called BEFORE"). **Quem tiver caminho direto ao produtor pula o gate.**
4. `ibkr_adapter.py:137,:183` — paper vs live é porta/env.
5. Import tardio generalizado — não é modularidade, é medo de ciclo.

### Ciclos reais
- `core/body/heartbeat.py:345,406` importa `core.pipeline.nodes.f51` e
  `.mangala` — **camada de baixo importando a de cima**
- `core/pipeline/nodes/auto_execute_paper.py:50` importa
  `tool_executor._submit_paper_order` dentro da função;
  `nodes/__init__.py:4,11` importa os dois
- `data/data_hub.py:22` importa `core.resilience` e é importado por ~20
  módulos, quase sempre em import tardio (`endpoints.py:64`,
  `f51_trade_gate.py:388`, `collector.py:1186`) — o tardio é o sintoma

**Não verificado:** `gateway.py` (1418 linhas) linha a linha; suíte do
`bridge/` executando.
