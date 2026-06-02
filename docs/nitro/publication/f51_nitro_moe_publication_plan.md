# F51 Nitro-MoE Publication Plan

Goal: turn F51 Nitro-MoE from an internal engineering result into a defensible scientific artifact.

## Best Submission Path

1. Publish a reproducibility preprint only after the benchmark harness generates every table from raw logs.
2. Submit as a software/reproducibility article if the public package is the main contribution.
3. Submit as a systems/performance paper only if the benchmark matrix includes multiple models, baselines, repeated runs, and at least one independent target machine.

## Venue Fit

| Venue | Fit | Why | Requirement risk |
| --- | --- | --- | --- |
| arXiv cs.DC/cs.PF/cs.LG preprint | good after cleanup | fast dissemination and priority record | source package must compile to usable PDF; moderation can hold weak or non-scholarly submissions |
| JOSS | good only if F51 is released as research software | JOSS reviews software plus short paper | software must be open source, research-applicable, documented, tested, and the paper must not focus on new research results |
| SoftwareX | good if framed as reusable software + reproducibility package | accepts research software papers with support material | open access APC and journal template; needs public software distribution |
| ACM/USENIX-style systems venue | possible later | best fit for memory hierarchy/runtime contribution | needs stronger novelty, baselines, statistics, and comparison to prior systems |

Official notes checked:

- JOSS submitting guide: https://joss.readthedocs.io/en/latest/submitting.html
- JOSS paper format: https://joss.readthedocs.io/en/latest/paper.html
- SoftwareX open access / author information: https://www.sciencedirect.com/journal/softwarex/publish/open-access-options
- arXiv submission process: https://arxiv.github.io/arxiv-submission-core/announcement_process.html

Notes from those sources:

- JOSS requires open-source software, browsable repository, issue tracking, research application, and a paper stored with the software repo.
- JOSS paper format is 750-1750 words and includes Summary, Statement of need, State of the field, Software design, Research impact statement, AI usage disclosure, Acknowledgements, and References.
- SoftwareX is a peer-reviewed open-access journal for software papers and charges an APC.
- arXiv submission consists of a source package plus metadata and must compile to a usable PDF before leaving the working state.

## What Must Be Built Before Submission

### 1. Reproducible Benchmark Harness

Create `benchmarks/run_all.ps1` that:

- records CPU, RAM, GPU, driver, git commit, llama.cpp commit, model file hash, and command-line flags;
- runs each mode with the same prompt set;
- performs at least 5 repetitions per mode;
- records prompt tok/s, generation tok/s, peak VRAM, wall time, and failures;
- writes JSON and CSV outputs under `results/YYYY-MM-DD/`;
- generates Markdown/LaTeX tables from the result files.

### 2. Required Baselines

For each model:

- CPU-only: `-ngl 0`
- GPU-all attempt: `-ngl 999`
- llama.cpp CPU-MoE: `--cpu-moe`
- partial MoE residency: `--n-cpu-moe` sweep
- F51 cache enabled/disabled if the code path is changed

### 3. Required Target-Machine Replication

The other machine must be measured separately:

- CPU L3 about 35 MB;
- two GPUs on PCIe x16;
- about 20 GB total usable VRAM;
- profiles: `safe5` (`--n-cpu-moe 31`) and `aggressive6` (`--n-cpu-moe 30`);
- report 5 repetitions per profile, not a single launch.

Until this is done, the 20 GB numbers are simulation/engineering estimates, not paper results.

### 4. Provenance Rules

No typed result numbers in the paper. Every number must come from:

```text
raw log -> parser script -> results JSON/CSV -> generated table/macro -> paper
```

If a number does not have this chain, it stays out of the abstract and results section.

## How To Publish

1. Make a clean public repository without model weights.
2. Add license, citation file, README, install instructions, benchmark instructions, and test/smoke CI.
3. Add `paper/` with `paper.md` for JOSS or LaTeX for arXiv/SoftwareX.
4. Generate a tagged release, for example `v0.1.0-repro`.
5. Archive the release on Zenodo or another DOI provider.
6. Submit preprint to arXiv if the paper is a real measurement/reproducibility paper, not a sales note.
7. Submit to JOSS if the artifact is primarily software; submit to SoftwareX if the artifact is a reusable software package with scientific-impact framing.

## Immediate Editorial Fix To The Pasted Text

Remove the headline table with Qwen 80B speedups until logs are restored or rerun. Replace it with the traced GPT-OSS 120B MXFP4 numbers from `publication/f51_nitro_moe_claims_ledger.md`.

The current scientific title should be narrower:

> F51 Nitro-MoE: Measurement and Tensor Accounting for GPT-OSS 120B MXFP4 Inference on Consumer GPUs

Do not claim "4.6x faster" or "38.7 tok/s" in a scientific submission until the raw benchmark artifacts are regenerated.
