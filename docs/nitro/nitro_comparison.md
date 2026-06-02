# F51 Nitro-MoE — Comparative Analysis
## With vs Without the technique

---

## 35B-A3B (Qwen3.6-35B-A3B IQ4_XS)

| Metric              | CPU-only       | GPU-all        | **Nitro (F51)** | vs CPU | vs GPU-all |
|---------------------|---------------|----------------|-----------------|--------|------------|
| Generation tok/s    | 22.68         | 9.89           | **42.04**       | +85%   | +325%      |
| Prompt tok/s        | 19.08         | 34.56          | **67.12**       | +252%  | +94%       |
| VRAM used           | 0 GB          | 15.6 GB        | **2.5 GB**      | —      | -84%       |
| RAM used            | 22 GB         | 22 GB          | 22 GB           | —      | —          |
| 256K context?       | Yes           | OOM            | **Yes**         | —      | —          |
| 256K gen tok/s      | ~12 (est.)    | —              | **43.83**       | +265%  | ∞          |
| 256K VRAM           | 0 GB          | —              | **5.67 GB**     | —      | —          |

---

## 80B-A3B (Qwen3-Coder-Next 80B IQ4_XS)

| Metric              | CPU-only       | GPU-all        | **Nitro (F51)** | vs CPU | vs GPU-all |
|---------------------|---------------|----------------|-----------------|--------|------------|
| Generation tok/s    | 17.18         | 8.41           | **38.67**       | +125%  | +360%      |
| Prompt tok/s        | ~15 (est.)    | ~25 (est.)     | **~242**        | +1513% | +868%      |
| VRAM used           | 0 GB          | 15.9 GB        | **2.4 GB**      | —      | -85%       |
| RAM used            | 40 GB         | 0.2 GB         | 38 GB           | —      | —          |
| 256K context?       | Yes (slow)    | OOM            | **Yes**         | —      | —          |
| 256K gen tok/s      | ~8 (est.)     | —              | **39.22**       | +390%  | ∞          |
| 256K VRAM           | 0 GB          | —              | **6.3 GB**      | —      | —          |
| Real 240K prompt    | ~8h (est.)    | —              | **12m55s**      | ~37x   | ∞          |

---

## 200B+ (DeepSeek-Coder-V2 236B IQ4_XS projected)

| Metric              | CPU-only       | GPU-all        | **Nitro (F51)** | vs CPU | vs GPU-all |
|---------------------|---------------|----------------|-----------------|--------|------------|
| Generation tok/s    | ~5-8          | OOM            | **~12-20***     | +150%  | ∞          |
| Prompt tok/s        | ~8 (est.)     | OOM            | **~150-250**    | +1800% | ∞          |
| VRAM used           | 0 GB          | >16 GB         | **~12-14 GB**   | —      | —          |
| RAM used            | 120+ GB       | —              | ~110 GB         | —      | —          |
| 256K context?       | Marginal      | No             | **Yes**         | —      | —          |
| Cold tier needed?   | No            | —              | **Yes (NVMe)**  | —      | —          |
| Cold miss penalty   | —             | —              | ~190ms/expert   | —      | —          |

*Dependente de: expert persistence em VRAM, cluster packing NVMe, multi-stream PCIe

---

## The death of GPU-all

```
80B GPU-all:  8.41 tok/s, 15.9 GB VRAM ← saturou, colapsou
80B CPU-only: 17.18 tok/s, 0 GB VRAM   ← mais rapido que GPU-all!
80B Nitro:    38.67 tok/s, 2.4 GB VRAM ← 4.6x GPU-all, 2.3x CPU-only
```

GPU-all é o pior dos 3 modos no 80B. A VRAM saturada força oversubscription do driver NVIDIA — o runtime faz swap silencioso entre VRAM e RAM via GTT. Cada acesso a peso vira page fault. O resultado é pior que CPU puro.

---

## O que a tabela prova

1. **Nitro vence CPU-only** em todos os tamanhos testados (1.85x–2.25x)
2. **Nitro vence GPU-all** por margem crescente com o tamanho do modelo (3.6x no 80B)
3. **GPU-all é contraproducente** em modelos MoE grandes — mais VRAM não é a resposta
4. **O custo Nitro é RAM, não VRAM** — DDR5 custa ~$3-5/GB, GDDR6X custa ~$15-20/GB
5. **A curva escala** — o 80B é 2.3x maior que o 35B, mas a queda de geração Nitro foi só 7%
