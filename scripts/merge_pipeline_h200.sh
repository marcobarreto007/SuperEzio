#!/bin/bash
# SuperEzio Merge Pipeline — H200
# Executar passo a passo. Cada step valida antes de continuar.
set -euo pipefail

log() { echo "=== [$(date '+%H:%M:%S')] $1 ==="; }

# ── Step 1: Dependencies ──────────────────────────────────────────
log "STEP 1: Installing dependencies"

# Remove any conda transformers that shadow pip installs
rm -rf /opt/conda/lib/python3.10/site-packages/transformers* 2>/dev/null || true
rm -rf /opt/conda/lib/python3.10/site-packages/peft* 2>/dev/null || true

pip install --upgrade pip
pip install "transformers>=4.57.1" peft accelerate

log "Verifying transformers has qwen3_5_moe..."
python -c "
from transformers.models.auto.configuration_auto import CONFIG_MAPPING
assert 'qwen3_5_moe' in CONFIG_MAPPING, 'FATAL: qwen3_5_moe NOT in CONFIG_MAPPING'
print('OK: qwen3_5_moe is supported')
print('transformers version:', __import__('transformers').__version__)
"

log "STEP 1 done"
