# 20 GB VRAM Simulation With Provenance

Assumptions:

- GPT-OSS 120B MXFP4 has 36 MoE layers.
- Each MoE layer has 128 experts.
- F51 measured expert tensor stride on GPT-OSS 120B MXFP4:
  - `ffn_gate_exps`: `4,406,400` bytes per expert.
  - `ffn_up_exps`: `4,406,400` bytes per expert.
  - `ffn_down_exps`: `4,406,400` bytes per expert.
- Derived expert size: `13,219,200` bytes = `12.61 MiB` per expert.
- Derived full MoE expert layer: `128 * 13,219,200` bytes = `1.576 GiB`.
- F51 cache capacity is per CPU-MoE layer.
- Fixed GPU runtime budget is not fully constant. On the local 16 GB run, llama.cpp reported `1607.61 MiB` CUDA model buffer, `180 MiB` KV buffers, and `609.15 MiB` compute buffer at `ctx=4096`, before accounting for profile-specific residency/cache pressure. The table below keeps an extra operational margin for allocator fragmentation, display use, and two-GPU imbalance.
- Target VRAM is about `20 GiB`; real usable free VRAM can be lower if a display or desktop compositor is active.

Formula used:

```text
gpu_floor_gib =
    full_gpu_moe_layers * 1.576
  + cpu_moe_layers * cache_capacity * 12.61 MiB
  + observed_runtime_buffers
```

## Matrix

| Profile | GPU MoE layers | `--n-cpu-moe` | Cache/layer | Derived floor | Operational target | Verdict |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| local16-style | 4 | 32 | 16 | ~15.1 GiB | ~15.7 GiB | local-style baseline |
| safe5 | 5 | 31 | 16 | ~16.7 GiB | ~17.3 GiB | recommended first run |
| aggressive6 | 6 | 30 | 14 | ~17.3 GiB | ~18.4 GiB | viable test |
| experimental6_fullcache | 6 | 30 | 16 | ~18.0 GiB | ~18.9 GiB | risky if VRAM is not clean |
| 7 layers | 7 | 29 | 14 | ~18.9 GiB | ~20.0 GiB+ | not recommended |

## Decision

Ship the kit with 5 layers as the safe profile and 6 layers as the aggressive test. Do not start at 7 layers on a 20 GB target.

The 20 GB numbers are a calculation from measured tensor sizes and local runtime buffers. They are not a substitute for a real target-machine benchmark. For publication, the 20 GB dual-GPU profile must be measured on that machine and reported separately.

For two GPUs, the launcher uses `--split-mode layer` and a tensor split proportional to the detected VRAM of each GPU. If both GPUs are equal, the split will be equal. If one GPU has more VRAM, it gets a larger share.

## What To Measure On Target

1. Time to `/health`.
2. `prompt_per_second` and `predicted_per_second` from `/completion`.
3. Presence or absence of:
   - `wrong sequence id`
   - `forcing full prompt re-processing`
   - CUDA OOM
4. F51 hit-rate lines if debug is enabled.
