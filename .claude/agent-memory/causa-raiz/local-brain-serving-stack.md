---
name: local-brain-serving-stack
description: Stack de serving do modelo local (:8080 llama-server, clientes :8083/:8002), onde ficam os logs, e os números de baseline desta máquina
metadata:
  type: reference
---

O modelo local da máquina roda num único llama-server em `http://127.0.0.1:8080`:

- Launcher: `C:\Users\marco\f51-llamacpp\start-f51.ps1` (auto-start via pasta Startup; `stop-f51.ps1` para). Logs em `C:\Users\marco\f51-llamacpp\logs\` — **`server.err.log` é sobrescrito a cada start** (história antiga só existe nos `ab-*.err.log` e `fit-*.err.log`).
- Modelo atual: `C:\Users\marco\models\ornith-1.5-35b-a3b\Ornith-1.5-35B-A3B-Q3_K_XL.gguf` (~16 GB), flags `-ngl 999 -sm layer -ts 7,11 -fa on -ctk q8_0 -ctv q8_0 -c 98304 -np 1`.
- **Quem usa as placas é o cérebro :8080, não os serviços.** Clientes são HTTP puro em `:8080/v1`: MIKE (:8083, `C:\Users\marco\Desktop\mike`) e Ezio (:8002, SuperEzio — `src/core/model_serving/providers.py:66`). Nenhum deles segura VRAM por si.
- Hardware: RTX 2070 8 GB = device 0 e placa do display; GTX 1080 Ti 11 GB = device 1; RTX 3060 morta (Code 31 desde 2026-09-04). Driver NVIDIA 610.60 desde ~09-10/11 (antes 580.97); a 1080 Ti já "sumiu" da enumeração em 09-07 e 09-11 (relógios diferentes).
- Baselines medidas: **40,4 tok/s gen / 150–180 tok/s prefill** com este modelo a 32k ctx (`f51-llamacpp\logs\ab-35b-q3kxl.err.log`); usuário reporta ~40 tok/s / ~1250 tok/s na config de produção (98k) em 2026-09-12 à noite.
- Monitor do MIKE (`mike\logs\monitor_history.jsonl`) reporta **só o maior cartão** (1080 Ti; `mike/core/autonomy/mike_monitor.py:98`) — não serve para observar a 2070.

**Why:** sessões futuras que investigam o modelo local perdem muito tempo sem saber onde está o log certo e que os serviços :8083/:8002 são clientes, não concorrentes de GPU.
**How to apply:** ao diagnosticar lentidão local, ler primeiro `f51-llamacpp\logs\server.err.log` da run atual e comparar com os `ab-*.err.log`; lembrar que o estado "93,8% na 1080 Ti" é o próprio modelo, não processo estranho. Ver [[llamacpp-absorve-cuda-oom]].
