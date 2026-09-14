# MIKE ↔ SuperEzio — plano do plano de controle

Desenho consolidado de 11/09/2026, a partir de três arquitetos independentes
(bridge, lado do MIKE, lado do SuperEzio). Somente leitura sobre o código real;
toda afirmação abaixo tem arquivo:linha.

**Decisões do dono:** bridge só em loopback · MIKE com controle total **exceto
ordens** (tudo paper) · MIKE híbrido (framework no repo dele, artefatos no Ezio).

---

## 1. O que não existe hoje (verificado)

| suposição | realidade |
|---|---|
| "o Ezio emite SSE" | **não** — só `StreamingResponse` NDJSON (`endpoints.py:1329,:2056`) e um `EventHub` in-process sem consumidor externo (`src/core/body/event_bus.py:188`) |
| "existe rota de comando" | **não** — rotas são leitura + `/task/submit` + `/paper/approve\|reject` (`endpoints.py:2388-2402`) |
| "o MIKE tem que falar um protocolo novo" | **não** — já existe `/v1/notifications/stream` (`mike/core/server/routers/autonomy.py:799-826`, fila 32, ping 30s) |
| "o flag de paper governa o modo paper" | **não** — `is_paper_submit_enabled()` (`settings.py:316`) **não é chamado em lugar nenhum do repo** |

Consequência: **o bridge nasce como polling + diff**, e exige **1 rota de
comando nova** no Ezio. Sem ela não há contrato de comando — só leitura.

---

## 2. O bridge

Mora em `SuperEzio\bridge\` (artefato de trabalho no Ezio, por decisão).
Python próprio, uvicorn em **127.0.0.1:8009**. `start.ps1`/`stop.ps1` copiam o
padrão verificado do Ezio — PID+StartTime em JSON (`start.ps1:103`,
`stop.ps1:14-18`, que recusa matar PID reutilizado).

```
Ezio :8002                                     MIKE
  │ poll 30s: /health, /health/details,          ▲
  │ /cockpit/summary, /trades/history,           │
  │ /sentiment/alerts                            │
  ▼                                              │
bridge :8009 ── diff vs snapshot ──► SSE ────────┘
  ▲            (reusa /v1/notifications/stream)
  └── POST /commands  (allowlist, default-deny)
```

Envelope de evento: `event_type`, `seq`, `ts`, `source`, `payload`,
`snapshot_id`. Falhas: Ezio cai → bridge `degraded`, comandos 503, **sem fila**;
Ezio reinicia → `boot_id` novo → emite `ezio.restarted` e re-baseia; comando em
voo → estado `unknown`, **nunca "aplicado"**, reenvio só com o mesmo
`command_id` (idempotente).

Auth: **nenhuma** (decisão do dono, 12/09/2026). O bridge é o único cliente,
roda na mesma máquina, e a fronteira é **topológica**: `HOST = "127.0.0.1"` é
**constante** em `bridge/config.py:20`, então origem externa não consegue nem
abrir o socket. O portão que sobra é a **allowlist default-deny** dos `kind`.
Não há token a vazar, rotacionar ou esquecer.

O Ezio confere a origem (`_require_loopback`, `control_endpoints.py`) **porque o
bind dele vem de env var** (`SUPEREZIO_HOST`) — o do bridge não. É defesa em
profundidade onde ela é necessária, não cerimônia simétrica.

**Nunca passa pelo bridge:** credencial IBKR e `ibkr_adapter.py:130`; qualquer
`kind` fora da allowlist (inclusive shell/Python genérico); chat livre como
backdoor; e-mail/calendário/memória da família; credenciais nos dois sentidos;
SQLite/traces como transporte; proxy de frontend; **bind fora de loopback**, e
o bridge **nunca** atrás do cloudflared.

---

## 3. A trava (o achado mais importante)

> **RESOLVIDO EM 2026-09-12.** O gate deixou de ser tautológico: `freeze_snapshot`
> é medido, copiado e exigido. Abaixo, o diagnóstico de 11/09 e o estado atual.

**Diagnóstico (11/09/2026).** `build_order_gate_metadata` gravava
`execution_freeze: False` **literal**. Só chegava ali se
`decision.status == "ALLOW"`, e ALLOW pressupunha GATE 1 aprovado. O campo era
tautologia, não medição. O leitor em `ibkr_adapter.py` (default `True`) era
**inalcançável**: se a chave faltasse, `gate_status != "ALLOW"` barrava antes.

**Estado atual (12/09/2026)** — o desenho correto foi implementado:
1. `evaluate_trade_gate` amostra `snapshot_execution_freeze()` **dentro** do
   gate (`f51_trade_gate.py:545`) e guarda em `decision.freeze_snapshot`, com
   timestamp e fonte.
2. `build_order_gate_metadata` **copia** esse snapshot (`:469`, `:493`) — nunca
   litera; grava `execution_freeze`, `freeze_sampled_at` e `freeze_source`.
3. Validador: ALLOW sem `freeze_snapshot` é **recusado** por
   `_require_freeze_snapshot` (`:426`).
4. O adapter recusa metadata sem `freeze_sampled_at` (`ibkr_adapter.py:106`) e
   reamostra no connect (`:147`) — a checagem deixou de ser inalcançável.

**Risco de seis meses:** alguém vai "consertar" o literal para `True` e congelar
todo trade legítimo — ensinando a equipe a desligar o gate.

---

## 4. Paper-only estrutural

Hoje paper é **configuração**, e frágil: paper vs live é só `IBKR_PORT`
(`ibkr_service.py:22`, `ibkr_adapter.py:137,:183`) — **trocar uma env var vira
live**. O rótulo "paper" do cockpit (`endpoints.py:387-402`) é display.

Estrutural = topologia, não permissão:
- allowlist de **porta** validada em `settings`, não `os.getenv` no ponto de uso
- allowlist de **conta**: o número da conta paper vem de arquivo em `.f51/`,
  não de env, e é conferido antes do submit
- uma função única `assert_paper_topology()` chamada na construção do socket

Trocar passa a exigir editar disco e reiniciar — não setar variável.

---

## 5. O que o MIKE pode fazer

**Pode mutar:** `/task/submit`, `/task/cancel`, `/feedback`,
`/bob/ibkr/recover`.

**Read-only explícito:**
- freeze e **qualquer env var** (`F51_TRADING_EXECUTION_FREEZE`,
  `SUPEREZIO_ENABLE_PAPER_ORDER_SUBMIT`, `SUPEREZIO_LIVE_TRADING_DISABLED`,
  `IBKR_PORT`)
- toda a família `/trade/manual/*` e `/trade/execute` (`:2642-2937`) — são
  atestações de fato do mundo; se o MIKE as preenche, o journal perde valor de
  evidência
- `/paper/approve|reject`, `/evidence/*`, `/auth/register` (`auth.py:396`,
  hoje público)
- **MIKE nunca recebe `SUPEREZIO_API_KEY`**

`_require_trading_auth` (`:2564`) devolve vazio sem `SUPEREZIO_API_KEY` ou com
`SUPEREZIO_OPEN_ACCESS` (`:2571`) — **fechar isso antes de emitir credencial**.

---

## 6. Identidade e loop do MIKE

**Identidade:** `config/soul.json:68-74` já tem `self_awareness`
(`my_location`, `my_server`, `my_soul`, `my_port`). É ali que entra o plano de
controle do Ezio. Cadeia: `mike_config.py:579` → `mike_lifecycle.py:463` →
`SOUL_PROMPT` (`mike_chat_core.py:172`) → system prompt. As invariantes
("ordem nunca; paper é o chão") vão em `golden_rules` (`:75-80`).

**Loop:** o `mission_engine` já tem o necessário — `_recover_orphaned_steps`
(`:516`), store atômico `_save_locked` (`:273`). Missão de correção = 4 passos:
observar → diagnosticar → propor → aceite determinístico (`pytest -q` +
`ruff check`, a definição de pronto do `CLAUDE.md`), com exit code gravado.

**Kill switch, duas camadas:**
- **A (real):** todo acesso do MIKE ao Ezio passa por tool que chama
  `assert_not_frozen` no primeiro statement. Hoje ele só aparece em 2 lugares
  (`mike_auto_reply.py:415`, `mike_workspace_mcp.py:184`).
- **B (o freeze gate):** implementado em 12/09/2026 — o produtor que sabe dizer
  `True` existe e é exigido (§3).

**Verificação:** o modelo errou 14→12 com 7.099 tokens no contexto — **contexto
maior agrava, não cura**. Contagem/existência/hash/exit code vêm de ferramenta.
CoVe (`mike_verify_chain.py:168`) só propõe o que verificar e aponta contradição
entre prosa e saída de ferramenta, **nunca** é fonte de fato. Regra dura:
afirmação sem `command`+`exit_code` é **rejeitada**, não revisada.

**Correção de rota:** `MIKE_CTX_SIZE` (`mike_config.py:526`) só vira `n_ctx` se
**o MIKE subir o servidor** (`mike_llm_boot.py:95`). Nesta máquina quem serve é
o F51 em `:8080` — subir a variável **não aumenta o cérebro**. O que ela ainda
faz é cortar histórico (`mike_chat_builder.py:412`) e limitar o orçamento a 85%
(`:404`); subir para ~32768 vale por isso, não por janela. O `--ctx-size` do F51
é 98304 (medido em 11/09, ver `LOCAL_CONTEXT_WINDOW.md`).

---

## 7. Divergência registrada (arquiteto 3, antes de executar)

> "Um controlador que pode escrever em `src/` não tem trava nenhuma — ele edita
> a trava. O limite duro tem que ser: MIKE lê tudo, conversa, cancela task e
> propõe; **não escreve em `src/`, nem no ambiente do processo**. Sem isso, os
> itens 2–4 são decorativos."

Esta divergência **contraria** a decisão de "controle total" e precisa de
resposta explícita do dono antes de qualquer código.

---

## 8. Ordem de construção proposta

| fase | entrega | por quê nesta ordem |
|---|---|---|
| **0** | fechar `_require_trading_auth` e `/auth/register` público | hoje `auth_required: false`; emitir credencial antes disso é entregar a chave da porta |
| **1** | §3 — o produtor que sabe dizer `True` + `assert_paper_topology()` | sem trava que funcione, todo o resto é decoração |
| **2** | rota de comando no Ezio (allowlist, default-deny) + `bridge/events.toml` | contrato antes do processo |
| **3** | o bridge (`:8009`) + `start/stop.ps1` | só depois de 0–2 |
| **4** | identidade no `soul.json` + missão no `mission_engine` | por último: é o que mais depende do resto estar de pé |

## 9. Riscos de seis meses

- **Sem lock de escrita**, dois agentes editando `src/` produzem conflito
  silencioso e **o `pytest` verde mente**. O lock tem que existir **antes** do
  primeiro patch.
- **O diff de snapshot** vira a fonte dos eventos; feature nova do Ezio exige
  editar lista em *outro* repo e ninguém lembra. Sintoma: MIKE cego. Mitigação:
  `bridge/events.toml` + teste que quebra quando rota nova não estiver
  classificada.
- **Não há lugar canônico para propostas** de patch: `.f51/` tem 23 arquivos de
  estado e nenhum diretório de propostas.
