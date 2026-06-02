# F51 Nitro-MoE Claims Ledger

Purpose: convert the pasted article into a publishable evidence ledger. A number is only publishable if it is backed by a raw log, source artifact, command, and hardware record.

Generated evidence JSON: `publication/results/f51_mxfp4_current_evidence.json`
Parser: `publication/scripts/extract_f51_evidence.ps1`

## Current Verdict

The current repo is not ready for a scientific journal submission as-is. It has publishable evidence for the GPT-OSS 120B MXFP4 local run and the SWA checkpoint fix. It does not yet have enough raw evidence in this repo for the Qwen 80B headline claims or the microbenchmark latency/bandwidth claims.

## Hardware Inventory Measured In This Session

| Item | Real value | Source |
| --- | ---: | --- |
| CPU | Intel Core i7-12700K | `Get-CimInstance Win32_Processor` |
| CPU cores / threads | 12 / 20 | `Get-CimInstance Win32_Processor` |
| CPU L3 cache | 25,600 KiB | `Get-CimInstance Win32_Processor` |
| RAM | 68,417,347,584 bytes = 63.72 GiB | `Get-CimInstance Win32_ComputerSystem` |
| GPU | NVIDIA GeForce RTX 5060 Ti | `nvidia-smi` and `logs/f51_mxfp4.log` |
| GPU VRAM | 16,310-16,311 MiB | `nvidia-smi`, `logs/f51_mxfp4.log:1-2` |
| Driver | 595.97 | `nvidia-smi` |

Important: the "35 MB L3 / 20 GB VRAM / two GPUs" machine is a target machine, not this local measurement. Do not mix those numbers into the local paper until that machine is benchmarked.

## Publishable Numbers Found Locally

| Claim | Value | Status | Evidence |
| --- | ---: | --- | --- |
| GPT-OSS 120B MXFP4 model size | 59.02 GiB, 4.34 BPW | traced | `logs/f51_mxfp4.log:65` |
| MoE layers | 36 | traced | `logs/f51_mxfp4.log:86` |
| Experts per MoE layer | 128 | traced | `logs/f51_mxfp4.log:37`, `logs/f51_mxfp4.log:104` |
| Experts selected per token | 4 | traced | `logs/f51_mxfp4.log:38`, `logs/f51_mxfp4.log:105` |
| Expert FFN length | 2880 | traced | `logs/f51_mxfp4.log:42` |
| Per-expert tensor bytes, MXFP4 | 13,219,200 bytes = 12.61 MiB | derived from trace | `logs/f51_mxfp4.log:183-185` |
| Full MoE expert layer, MXFP4 | 1,692,057,600 bytes = 1.576 GiB | derived | `128 * 13,219,200` |
| All MoE expert tensors, MXFP4 | 60,914,073,600 bytes = 56.73 GiB | derived | `36 * 128 * 13,219,200` |
| CUDA model buffer at load | 1607.61 MiB | traced | `logs/f51_mxfp4.log:145` |
| KV buffers at ctx 4096 | 144.00 + 36.00 MiB | traced | `logs/f51_mxfp4.log:164`, `logs/f51_mxfp4.log:169` |
| CUDA compute buffer | 609.15 MiB | traced | `logs/f51_mxfp4.log:177` |
| Prompt processing speed, one local MXFP4 run | 4.22 tok/s over 68 tokens | traced | `logs/f51_mxfp4.log:514` |
| Generation speed, one local MXFP4 run | 3.22 tok/s over 33 tokens | traced | `logs/f51_mxfp4.log:515` |
| F51 decode hit-rate checkpoints | 67.9% to 87.6% across token 50-600 | traced | `logs/f51_mxfp4.log:535-547` |
| SWA checkpoint fix smoke result | zero `wrong sequence id` across four external requests | externally reported, not full benchmark | `evidencias/f51_swa_checkpoint_fix_2026-05-30.md` |

## Claims That Must Be Downgraded Until Re-Benchmarked

| Pasted claim | Current publication status | What to do |
| --- | --- | --- |
| Qwen 80B GPU-all = 8.4 tok/s | untraced in current raw logs | rerun and save raw logs |
| Qwen 80B CPU-only = 17.2 tok/s | untraced in current raw logs | rerun and save raw logs |
| Qwen 80B Nitro = 38.7 tok/s | untraced in current raw logs | rerun and save raw logs |
| Qwen 80B at 256K context = 39.2 or 39-43 tok/s | untraced in current raw logs | rerun with full command, prompt file, output hash |
| GPU resident expert = 31 microseconds | untraced raw microbench output | rerun `f51_microbench.cu` and archive JSON/CSV |
| CPU expert = 164 microseconds | untraced raw microbench output | rerun `f51_microbench.cu` and archive JSON/CSV |
| PCIe streaming = 695 microseconds | untraced raw microbench output | rerun `f51_microbench.cu` and archive JSON/CSV |
| speculative prefetch = +0.0 to +0.8 pp | untraced final result table | rerun cache simulator and save config/output |
| "4.6x faster than GPU-all" | not publishable yet | only valid after CPU-only/GPU-all/Nitro reruns with same prompt and repetitions |

## Replacement Headline For Scientific Use

Use this until the Qwen and microbench numbers are revalidated:

> On a local RTX 5060 Ti 16 GB system, GPT-OSS 120B MXFP4 exposes 36 MoE layers with 128 experts per layer and 4 selected experts per token. The traced MXFP4 expert tensors imply 12.61 MiB per expert and 1.576 GiB per full expert layer. A local llama.cpp/F51 run loaded the 59.02 GiB model with 1607.61 MiB of CUDA model buffer, 180 MiB of KV buffer, and 609.15 MiB of CUDA compute buffer at context 4096. In the currently archived run, generation speed was 3.22 tok/s over 33 generated tokens, and F51 cache hit-rate checkpoints ranged from 67.9% to 87.6% between token 50 and token 600.

This is less flashy than the pasted text, but it is defensible.
