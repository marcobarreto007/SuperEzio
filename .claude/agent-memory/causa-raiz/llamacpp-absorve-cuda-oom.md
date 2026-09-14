---
name: llamacpp-absorve-cuda-oom
description: O llama-server local (build própria em tools\llama.cpp-src) loga cudaMalloc OOM, "retenta sem pipeline parallelism" e CONTINUA servindo — sucesso que mente; incidente 2026-09-13 a 0,98 tok/s
metadata:
  type: project
---

Classe de falha descoberta no incidente de 2026-09-13 (modelo local "de pé e errado", ~80 tokens em 80 s):

- Quando a VRAM não cabe, o build local do llama.cpp **não morre**: loga `E ... cudaMalloc failed: out of memory` + `graph_reserve: failed to allocate compute buffers` + `W sched_reserve: ... retrying without pipeline parallelism` e segue — imprime `model loaded`, `/health` 200, `/props` com n_ctx certo, e serve a **0,98 tok/s (≈1/40 da baseline de 40 tok/s)**. Se o retry também falhar, aí sim morre (`llama_server: exiting due to model loading error` — ver `logs\fit-iq3.err.log`).
- Prova: `logs\server.err.log` da run de 2026-09-13 (PID 14728) vs `logs\ab-35b-q3kxl.err.log` (mesmo modelo, sem OOM, 40,4 tok/s).
- O retry sem paralelismo de pipeline pede buffer menor (ex.: 377→240 MiB em `fit-iq3.err.log`), então quando ele passa, a device estava a poucas centenas de MB do necessário.
- Com `-ts 7,11 -c 98304`, a RTX 2070 (device 0, display) vive com ~0,3–0,7 GB de folga: **qualquer crescimento de apps na placa de display (browser/Electron) pode flipar o load para OOM** — sem nenhum erro visível para quem só olha o cliente.

**Why:** é a explicação mais provável para futuros episódios "servidor sobe, tudo lento, sem erro" — e a evidência fica só no stderr do load, que é sobrescrito a cada start.
**How to apply:** em sintoma "lento mas de pé", grep `cudaMalloc|retrying without pipeline|graph_reserve` no `server.err.log` ANTES de qualquer outra hipótese; ancorar sempre contra um `ab-*.err.log` do mesmo modelo; não confundir com contenção de clientes (eles só falam HTTP em :8080). Ver [[local-brain-serving-stack]].
