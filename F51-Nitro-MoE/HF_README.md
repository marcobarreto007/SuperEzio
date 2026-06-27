# F51 Nitro-MoE: Large MoE Models on a Single 16 GB GPU

**No cloud. No API keys. No $20K workstation.** Just a consumer RTX 5060 Ti.

---

## TL;DR

| Model | Mode | Gen tok/s | VRAM |
|---|---|---|---|
| Qwen 80B-A3B | GPU-all (saturated) | 8.4 | 15.9 GB |
| Qwen 80B-A3B | CPU-only | 17.2 | 0 GB |
| **Qwen 80B-A3B** | **Nitro (`--cpu-moe`)** | **38.7** | **2.4 GB** |
| GPT-OSS 120B | Nitro + 4 GPU layers | ~6.2 sustained | ~8 GB |

**4.6× faster than GPU-all, using 1/6th of the VRAM.** On hardware that "shouldn't" run these models.

---

## The idea

MoE models only activate 2-4 experts per token. Most experts stay cold. So:

- **GPU** → attention, router, norms + a *pool* of hot experts (LRU cache)
- **RAM (DDR5)** → the experts, computed on CPU
- **PCIe streaming** → **don't.** Copying weights RAM→GPU is 4× slower than computing on CPU directly. Measured, not theorized.

## The numbers that matter

Measured on RTX 5060 Ti 16GB + i7-12700K + 64GB DDR5:

| Path | Bandwidth | Latency/expert |
|---|---|---|
| GPU resident (cache hit) | ~426 GB/s | **~31 µs** |
| CPU compute | ~80 GB/s | **~164 µs** |
| PCIe streaming | ~20 GB/s | **~695 µs** |

PCIe is the bottleneck. If an expert isn't already on GPU, computing it on CPU wins every time.

---

## Reproduce it

```bash
# Install (clones + patches + compiles llama.cpp)
python f51_cli.py install

# Run local server (auto-calibrates for your hardware)
python f51_cli.py serve -m MODEL.gguf -c 4096

# Or direct:
llama-server -m MODEL.gguf -ngl 999 --cpu-moe -c 4096 -fa on
```

**Compare three modes** to validate on your hardware:
```bash
llama-cli -m model.gguf -ngl 0   -n 100   # CPU-only baseline
llama-cli -m model.gguf -ngl 99  -n 100   # GPU-all baseline
llama-cli -m model.gguf -ngl 99 --cpu-moe -n 100  # Nitro
```

---

## What didn't work (and why it's here)

We tried two "obvious" optimizations. Both failed. Both are documented because knowing what *doesn't* work is as valuable as knowing what does.

- **PCIe streaming on cache miss:** 695 µs vs 164 µs CPU. Dead end.
- **Speculative lookahead predictor:** +0.0 to +0.8 pp hit rate. The LRU cache already captures the repetition. $O(n)$ overhead for nothing.

---

## Hardware

- GPU: RTX 5060 Ti 16 GB · Blackwell · PCIe 5.0 x8
- CPU: Intel i7-12700K
- RAM: 64 GB DDR5-4800
- OS: Windows 11 · CUDA 12.x

---

## Paper

Full paper (IEEE format, 4 pages): [`evidencias/F51_Nitro_MoE_paper.tex`](evidencias/F51_Nitro_MoE_paper.tex)

TechRxiv DOI: *(pending submission)*

---

## Credits

Built on: llama.cpp · KTransformers (SOSP'25) · Fiddler (ICLR'25) · Mixtral-offloading (Eliseev & Mazur, 2023)

**Author:** Marco Barreto · Fuch F51 Labs · Montréal, 2026

*"O número manda. Resultado negativo é insight."*
