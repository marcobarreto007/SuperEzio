# F51 Layer 2 — Estado e Instruções Pós-Reboot

2026-05-28

## Estado Atual

O código do Layer 2 (async H2D streams com ring buffer) está implementado e compilado.
O diff está limpo e revisado — só o que importa.

### Arquivos modificados (não commitados em C:\llama.cpp)

```
ggml/include/ggml.h              — guard #ifndef __cplusplus para stdbool.h
ggml/src/ggml-cuda/f51_nitro.cuh — ring buffer de 4 eventos (F51_H2D_EVENT_RING)
ggml/src/ggml-cuda/ggml-cuda.cu  — ativa async H2D stream + ring buffer sync
```

### Binário compilado

- `C:\llama.cpp\build\bin\ggml-cuda.dll` — compilado hoje 08:17, contém as mudanças
- `C:\llama.cpp\build\bin\llama-server.exe` — de ontem, não mudou

### O que foi corrigido na revisão

- VMM pool size 32→64 GB: **revertido** (não pertence ao Layer 2)
- Default cache capacity 256→16: **revertido** (era leftover de benchmark)

---

## Por que o server não bootava antes

O driver CUDA/WDDM ficou em estado zoado após crashes consecutivos.
`cudaMallocHost` falhava → o modelo tentava alocar tudo na VRAM → OOM.
**Nenhuma das mudanças nossas afeta o load do modelo.**
O reboot deve resolver.

---

## Instruções Pós-Reboot

### 1. Verificar que o build está ok

```bat
cd C:\llama.cpp\build
ninja -j4 ggml-cuda.dll
```

Se disser "no work to do", já está compilado.

### 2. Verificar GPU limpa

```powershell
nvidia-smi --query-gpu=memory.free,memory.total --format=csv
```

Deve mostrar ~15700+ MiB livres.

### 3. Boot do server com Layer 2 ATIVADO

Usa o batch file pronto:

```bat
C:\F51_LAB\start_layer2.bat
```

Conteúdo dele:
```bat
@echo off
set F51_MOE_CACHE=1
set F51_CACHE_CAP=26
set F51_DEBUG=1
set GGML_OP_OFFLOAD_MIN_BATCH=1
set F51_LAYER2_ENABLED=1
echo Layer 2 ENABLED — starting server...
C:\llama.cpp\build\bin\llama-server.exe -m C:\F51_LAB\models\GLM-4.5-Air\IQ4_XS\GLM-4.5-Air-IQ4_XS-00001-of-00002.gguf --host 0.0.0.0 --port 8080 -ngl 999 -c 2048 -np 4 > C:\F51_LAB\f51_server_stdout.log 2> C:\F51_LAB\f51_server_stderr.log
```

### 4. Aguardar o load (~40s para GLM-4.5-Air)

Monitorar:
```powershell
Get-Content "C:\F51_LAB\f51_server_stderr.log" -Tail 5
```

Quando aparecer `HTTP server listening on port 8080`, o server está pronto.

Verificar:
```bash
curl -s http://localhost:8080/health
```

### 5. Rodar benchmark Layer 2 ON

```bash
for i in 1 2 3; do
  echo "=== WARMUP $i ==="
  curl -s http://localhost:8080/completion -H "Content-Type: application/json" -d '{"prompt": "The capital of France is", "n_predict": 50, "temperature": 0}' | jq '.timings.predicted_per_second'
  sleep 2
done

echo "=== BENCHMARK 1: Layer 2 ON ==="
curl -s http://localhost:8080/completion -H "Content-Type: application/json" -d '{"prompt": "Explain the theory of relativity in simple terms.", "n_predict": 100, "temperature": 0}' | jq '.timings'
```

### 6. Rodar baseline (Layer 2 OFF)

Matar o server atual e usar o batch baseline:

```bat
C:\F51_LAB\start_baseline.bat
```

Conteúdo dele:
```bat
@echo off
set F51_MOE_CACHE=1
set F51_CACHE_CAP=26
set F51_DEBUG=1
set GGML_OP_OFFLOAD_MIN_BATCH=1
set F51_LAYER2_ENABLED=0
echo Baseline (Layer 2 DISABLED) — starting server...
C:\llama.cpp\build\bin\llama-server.exe -m C:\F51_LAB\models\GLM-4.5-Air\IQ4_XS\GLM-4.5-Air-IQ4_XS-00001-of-00002.gguf --host 0.0.0.0 --port 8080 -ngl 999 -c 2048 -np 4 > C:\F51_LAB\f51_server_stdout.log 2> C:\F51_LAB\f51_server_stderr.log
```

Repetir os mesmos benchmarks.

---

## O que esperar

Com IQ4_XS o ganho do Layer 2 é limitado pelo PCIe (~64ms por token em H2D).
O ring buffer resolve a race condition, mas o bottleneck real é o formato do modelo.

| Cenário | tok/s esperado |
|---|---|
| CPU direto | ~15 |
| GPU offload sem Layer 2 | ~5.7 |
| GPU offload com Layer 2 | ~5.7-6.5 (ganho marginal com IQ4_XS) |

O F51 foi desenhado pra FP16. Com FP16:
- GPU dequant é 10-50x mais rápido
- CPU faria 0.5-2 tok/s
- GPU com F51 faria 10-30 tok/s
- **Aí o cache de experts vira o fator decisivo.**

---

## Logs para verificar

- `C:\F51_LAB\f51_server_stderr.log` — stderr do server
- `C:\F51_LAB\f51_server_stdout.log` — stdout do server
- `C:\F51_LAB\f51_moe_cache.log` — log do F51 cache (se F51_DEBUG=1)
- `C:\F51_LAB\f51_scheduler.log` — log do scheduler (se existir)

## Se o server não bootar de novo

1. Verificar se há processos zumbis: `Get-Process -Name "llama-server" -ErrorAction SilentlyContinue`
2. Verificar logs de erro: `Get-Content C:\F51_LAB\f51_server_stderr.log -Tail 20`
3. Tentar com menos layers: `-ngl 46` em vez de `-ngl 999`
4. Se nada funcionar, rodar `nvidia-smi --gpu-reset` (provavelmente não disponível em WDDM)
