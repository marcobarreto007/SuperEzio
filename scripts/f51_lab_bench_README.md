# F51 Chama Lab — Etapa 1 (inventário + 3 testes)

## 1. Inventário

No **CMD** (como administrador se `wmic` falhar):

```cmd
cd /d C:\Users\marco\Desktop\SuperEzio Financeiro
scripts\f51_lab_inventory.cmd
```

Ou manualmente os comandos que já tens — resultado em `C:\F51_LAB\inventory.txt`.

## 2. Três testes isolados (mesmo modelo, mesma máquina)

Pré-requisito: CEO GGUF + `llama-server.exe` (SuperEzio Financeiro).

Modelo: `models\superezio-ceo-intent-merged.Q4_K_M.gguf`  
Binário: `llama.cpp\bin\llama-server.exe`

Regista em `C:\F51_LAB\bench_notes.txt`: tokens/s, RAM usada, VRAM (nvidia-smi), qualquer OOM.

### Teste 1 — CPU-only

```cmd
llama.cpp\bin\llama-server.exe -m models\superezio-ceo-intent-merged.Q4_K_M.gguf -ngl 0 -c 4096 --port 8091 --reasoning off
```

Numa segunda janela:

```cmd
curl http://127.0.0.1:8091/health
```

Gera 1 resposta curta via UI do llama ou `curl` chat — anota latência.

### Teste 2 — GPU normal (teu perfil atual)

```cmd
scripts\serve_ceo_llamacpp.ps1 -Port 8092 -GpuLayers 28 -ContextLength 8192
```

(Ajusta `-GpuLayers` se OOM: 20, 24, 28.)

Anota tokens/s no log do servidor.

### Teste 3 — CPU base + GPU offload (híbrido explícito)

Exemplo: poucas layers na GPU, resto CPU — mede trade-off PCIe/RAM:

```cmd
llama.cpp\bin\llama-server.exe -m models\superezio-ceo-intent-merged.Q4_K_M.gguf -ngl 12 -c 8192 --port 8093 -fa on -ctk q8_0 -ctv q8_0 --reasoning off --mlock
```

Depois repete com `-ngl 28` e compara.

## 3. O que já sabemos do projeto (até o agente ler o PC)

| Item | Valor documentado |
|------|-------------------|
| GPU | RTX **5060 Ti** ~16 GB (única GPU) |
| RAM | **64 GB** DDR5-6000 (persona Bob) |
| OS | Windows 11 build 26200 |
| Motor inferência local | **llama.cpp** `llama-server` (CUDA) |
| CEO | Qwen3.6-35B merged **Q4_K_M** @ `:8082` |
| Arbitro | Qwen menor @ `:8084` (quando GGUF baixado) |
| PyTorch | no venv SuperEzio — `torch.cuda` no `/health/details` |
| Cloud experts | DeepSeek, Grok, Gemini (opcional) |

Confirma tudo com `inventory.txt` — números reais batem com isto ou não.

## 4. Próximo passo (depois dos 3 testes)

Cola aqui `inventory.txt` + 3 linhas por teste (ngl, tok/s, OOM sim/não). Aí desenhamos F51 Nitro sem tocar no llama.cpp ainda.
