# Janela de contexto do modelo local

Como a janela do `llama-server` local é declarada, medida e consumida — e por
que ela não é mais um número solto no código.

**Cérebro vs. voz.** O cérebro do SuperEzio é **nuvem** — DeepSeek V4 Pro
(`deepseek-v4-pro`) nos papéis que decidem (Bob/CEO e orquestrador) desde
12/09/2026; era DeepSeek V4 Flash até 10/09. O
modelo local (Cyber-Tiel-Coder-35B-A3B-MTP / Ornith, nas 2 GPUs) é a **voz adjuvante** — não decide dinheiro.
Tudo aqui é sobre essa voz.

---

## A cadeia (fonte de verdade)

```
C:\Users\marco\f51-llamacpp\start-f51.ps1   -c 98304      (o servidor de verdade)
        │
        ▼
config/runtime.yml  →  models.local_voice.n_ctx: 98304    (declaração)
        │
        ▼
ModelConfig.n_ctx  →  ModelProvider.n_ctx                  (transporte)
        │
        ▼
gateway.local_context_fits(messages, window)               (o guard)
        │
        ▼
LOCAL_CONTEXT_HARD_TOKEN_CAP                               (fallback, se nada declarado)
```

**Regra:** a janela declarada vence a constante. A constante só vale quando
nada declara janela — o que preserva o comportamento anterior ao refactor de
11/09/2026.

O teto efetivo de **entrada** desconta a folga de saída, porque entrada e
resposta dividem o mesmo slot (`-np 1`):

```
teto_entrada = janela − LOCAL_CONTEXT_OUTPUT_RESERVE   (2.048)
```

---

## O que foi medido (11/09/2026, madrugada)

Testes rodados subindo o servidor em `:8081` e derrubando a produção em `:8080`
(inevitável: só há ~1,6 GB de VRAM livre e o teste precisa de ~17 GB).

### Teto

| contexto | `-ub` | `-ts` | KV | resultado |
|---|---|---|---|---|
| 32.768 (era o de produção) | 512 | 7,11 | q8_0 | ok |
| **98.304 (novo)** | 512 | 7,11 | q8_0 | **ok** — PP desligado no fallback |
| 65.536 | 512 | 7,11 | q8_0 | ok — PP mantido |
| 114.688 | 256 | 6,12 | q8_0 | falta 833 MiB (CUDA1) |
| 131.072 | 256 | 6,12 | q8_0 | falta 952 MiB (CUDA1) |
| 131.072 | 128 | 6,12 | q8_0 | falta 952 MiB — `-ub` não muda mais nada |
| 131.072 | 256 | 6,12 | q4_0 | falta 504 MiB (exatamente metade) |
| 131.072 | 128 | 5,13 | q8_0 | **impossível**: 11,28 GB de pesos na 1080 Ti (tem 11,26 GB) |
| 262.144 | 512 | 7,11 | q8_0 | falha: compute buffer de 1,14 GB na CUDA0 |

### Onde está o gargalo

**É a 1080 Ti (device 1), não a 2070.** Todas as falhas de KV são `CUDA1`. A
2070 tem ~575 MiB livres e não absorve mais camada. O `-ts` está **esgotado nos
dois lados**: a faixa útil é `7,11` e não mais que isso.

### `-nkvo` (KV na RAM do sistema) — caminho morto

Destrava 131.072 e 196.608, mas:

| | sem `-nkvo` (98.304) | com `-nkvo` (131.072) |
|---|---|---|
| geração | 31,9 tok/s | **6,4 tok/s** (5x pior) |
| prefill | 1.380 tok/s | 626 tok/s |

Com `-nkvo` o pipeline parallelism fica **ligado** — prova que a lentidão é o KV
cruzando PCIe, não o fallback do PP. Não usar.

### Velocidade por janela (prompt ~4,9k tokens)

| janela | PP | geração | prefill |
|---|---|---|---|
| 32.768 | ligado | ~37,8 tok/s | ~1.250 tok/s |
| 65.536 | ligado | 31,8 tok/s | 1.364 tok/s |
| 98.304 | desligado | 31,9 tok/s | 1.380 tok/s |

**O fallback de PP não custa velocidade** (`retrying without pipeline
parallelism`): 31,8 vs 31,9 é ruído. O custo de ~16% vem do KV maior, e já está
pago tanto em 65.536 quanto em 98.304 — por isso **98.304 domina 65.536**.

---

## Por que 98.304 e não 8.192

Contagens exatas via `/tokenize` do servidor real:

| arquivo | tokens | cabia em 8.000? |
|---|---|---|
| `src/core/math/financial_engine.py` | 1.647 | sim |
| `src/core/pipeline/f51_trade_gate.py` | 7.055 | sim (apertado) |
| `src/core/pipeline/nodes/tool_executor.py` | 11.710 | **não** |
| `src/core/model_serving/gateway.py` | 12.372 | **não** |
| `src/agent_server/endpoints.py` | 29.482 | **não** |
| **soma dos 5** | **62.266** | **não** |

Com o teto antigo (8.000), **3 dos 5 arquivos eram inalcançáveis** — e são
justamente onde estão os P0 da auditoria. A voz local não conseguia abrir um
arquivo médio do próprio repositório.

Com 98.304 os cinco cabem juntos, com ~36% da janela sobrando.

---

## Armadilhas conhecidas

- **O llama.cpp escreve o log inteiro no `stderr`, não no `stdout`.** Checar
  `"model loaded"` no stdout dá falso negativo. Já causou diagnóstico errado
  ("falhou" num servidor que subiu).
- **`--n-cpu-moe` tem bug aberto** em multi-GPU (issue #15136): enche uma placa
  até estourar antes de usar a segunda. Se precisar, usar `-ot` explícito.
- **A árvore de build** em `tools\llama.cpp-src\build\bin\Release` está
  misturada (arquivos de 15/08, 04/09 e 06/09). Um build limpo seria mais
  seguro, mas o atual funciona.
- **CORS aberto sem API key** — o próprio llama.cpp avisa no boot
  (`this can be a security risk`). Hoje escuta só em `127.0.0.1`; vale saber
  que existe `Tailscale serve` na frente.

---

## O que a voz local NÃO é

O modelo local **não é oráculo**. Medição de 11/09/2026: com um arquivo real de
7.099 tokens no contexto, o Ornith respondeu que `f51_trade_gate.py` tinha
**12** funções `def`. O arquivo tem **14**. Sem hedge, sem ressalva — número
errado com confiança total.

Consequência de projeto: qualquer verificador construído sobre ele tem que
confirmar com ferramenta determinística (`grep`, `pytest`, `/tokenize`). Ele
**propõe**; a ferramenta **decide**.
