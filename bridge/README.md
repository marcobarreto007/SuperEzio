# bridge — MIKE ↔ SuperEzio (Fase 3)

Processo Python próprio. Coleta o Ezio por **polling + diff**, publica o diff no
MIKE pelo canal de notificação que já existe e aceita comando allowlistado.
Desenho: `docs/architecture/MIKE_EZIO_BRIDGE.md` §1–§2.

```
Ezio :8002  ──poll 30s──▶  bridge :8009  ──POST /v1/notifications/send──▶  MIKE :8083
                                   ▲
                                   └── POST /commands (allowlist, default-deny)
```

## Como sobe

```powershell
.\bridge\start.ps1
.\bridge\stop.ps1                          # recusa matar PID reutilizado
```

Direto, sem o script: `python -m bridge.main` (a partir da raiz do repo).

## Portas

| quem | porta | bind |
|---|---|---|
| bridge (este processo) | **8009** | **127.0.0.1**, sempre — o bind é constante no código, não há env para mudar |
| Ezio (alvo da coleta) | 8002 | `BRIDGE_EZIO_BASE_URL` |
| MIKE (alvo da publicação) | 8083 | `BRIDGE_MIKE_BASE_URL` |

Nunca atrás de túnel. `start.ps1` recusa subir se a 8009 já estiver ocupada.

## Superfície do bridge

| rota | o que é |
|---|---|
| `GET /health` | estado do bridge, do Ezio e do MIKE |
| `GET /snapshot` | hash por rota, sem despejar corpos |
| `GET /events/recent?limit=` | ring buffer de eventos |
| `POST /poll` | força um ciclo agora (diagnóstico) |
| `POST /commands` | **único ponto de mutação** — allowlist default-deny |

### Sem credencial (decisão de projeto, 12/09/2026)

Não há token em lugar nenhum: nem na entrada (`/commands`) nem na saída (a rota
de comando do Ezio). O bridge é o único cliente, roda na mesma máquina, e a
fronteira é **topológica** — o bind é `127.0.0.1`, constante no código, não há
env que o mude. Não existe credencial a vazar, rotacionar ou esquecer. O portão
que sobra é a **allowlist default-deny** dos `kind`: fora dela, **403** antes de
falar com o Ezio.

## Configuração

`bridge/events.toml` é o **inventário canônico das rotas do Ezio** (Fase 2). O
bridge **lê** esse arquivo, nunca escreve:

- rotas coletadas = entradas com `snapshot = true` (hoje: `/health`,
  `/health/details`, `/cockpit/summary`, `/trades/history?limit=50`,
  `/sentiment/alerts`);
- allowlist de comando = `[commands] allowed`;
- vocabulário de eventos = `[events]` (o bridge não inventa nome de evento).

Ambiente (nenhum arquivo `.env` é lido):

| variável | efeito |
|---|---|
| `BRIDGE_EZIO_COMMAND_PATH` | sobrescreve o caminho da rota de comando (default: `[commands] route` do inventário) |
| `BRIDGE_POLL_INTERVAL_S` | intervalo do ciclo (default 30) |
| `BRIDGE_EZIO_BASE_URL`, `BRIDGE_MIKE_BASE_URL`, `BRIDGE_PORT` | endpoints |

## O que passa

- **Leitura** das rotas com `snapshot = true`, por GET, com timeout.
- **Eventos** de mudança para o MIKE: `POST /v1/notifications/send` — a rota que
  já existe. O envelope (`event_type`, `seq`, `ts`, `source`, `payload`,
  `snapshot_id`) vai no corpo da notificação. Não há protocolo novo.
- **Comando** de um `kind` da allowlist (`task.submit`, `task.cancel`,
  `feedback`, `bob.ibkr.recover`), repassado como
  `{"command_id", "kind", "params", "issued_by"[,"ttl_s"]}` para
  `POST /control/commands` no Ezio — exatamente os campos do `ControlCommand`
  da Fase 2, que é `extra="forbid"` (campo a mais vira 422).

### Estados do comando

O Ezio é a autoridade: se o corpo da resposta traz `state`, vale o dele
(`applied`/`rejected`/`denied` → applied/rejected/rejected, `unknown`/
`in_flight` → unknown). Sem `state` no corpo, cai no HTTP:

| resposta do Ezio | estado | HTTP devolvido | significa |
|---|---|---|---|
| 2xx | `applied` | 200 | executado |
| 4xx, 409, **503** | `rejected` | 400 | nada foi executado |
| 5xx, timeout, erro de transporte | `unknown` | **202** | em voo — reenvie com o mesmo `command_id` |
| rota ausente (404/405) | — | 503 | Fase 2 não subiu a rota; nada foi gravado |

## O que NÃO passa

- Credencial IBKR, `SUPEREZIO_API_KEY`, e qualquer rota da família `/trade/*`,
  `/paper/approve|reject`, `/evidence/*`, `/auth/*`.
- **Shell/Python genérico**: `kind` fora da allowlist = **403**, antes de falar
  com o Ezio.
- Escrita em `src/`, em variável de ambiente ou no freeze.
- Proxy de frontend, SQLite/traces como transporte, e-mail/calendário/memória
  da família.

## Regras duras (implementadas, com teste)

1. **Bind só em loopback.** Constante no código.
2. **Comando não persiste.** Sem fila, sem disco: se o Ezio não está de pé na
   última coleta, `/commands` devolve 503 e nada é guardado.
3. **Comando em voo que morre = `unknown`**, nunca `applied` (timeout, erro de
   transporte e 5xx do Ezio caem aqui; 5xx devolve **202**, não 200). Reenvio só
   com o **mesmo `command_id`**; um `command_id` já `applied`/`rejected` não é
   reenviado. O `503` do Ezio é o oposto: "nada foi executado" = `rejected`.
4. **Rota de comando ausente = 503** (`command_route_absent`), e o comando não é
   registrado — dá para reenviar quando a rota existir.
5. **Degradação não derruba o bridge**: corpo que não parseia, rota que devolve
   erro e MIKE fora do ar viram evento/contador, não exceção.
6. **Mandato de Sobrevivência ($1.000 CAD & Taxa Zero — MIKE ↔ Ezio)**: Nenhuma
   ordem ou intenção de trade é aceita se gerar corretagem $> 0$ (exclusividade
   dos 108 ETFs Commission-Free do TD ou cota TD Easy Trade auditada), se o
   risco exceder $1.5\%$ ($15 CAD), se a razão R:R for $< 2.5:1$, ou se o tipo
   de ordem for a mercado (MARKET). Fail-closed total.

## Testes

```bash
python -m pytest bridge/tests -q     # hermético, sem rede
python -m ruff check bridge/
```

A suíte do repo (`tests/`) não cobre este diretório (`testpaths = tests`).
