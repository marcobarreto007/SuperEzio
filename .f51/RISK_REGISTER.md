# F51 Risk Register

Updated: 2026-05-21T00:00:00-04:00
Session: clean-tree-zero-retired-surface-2026-05-21

## Active Risks

### CLEAN-R1 - Training data remains referenced [LOW]

- Classification: operator tooling
- Risk: `F51_Datasets/sft_output` can look like cleanup target, but training scripts still reference it.
- Evidence: `scripts/finetune_*`, `scripts/train_qwen36_3h.py`, and VastAI scripts point to generated SFT outputs.
- Mitigation: Remove only in a dedicated training decommission pass.

### CLEAN-R2 - GitHub remains blocked [HIGH]

- Classification: policy
- Risk: Any GitHub operation violates project policy.
- Evidence: `.f51/GITHUB_POLICY.json` is active and hard-blocking.
- Mitigation: Use local commits only.
