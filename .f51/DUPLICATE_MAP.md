# F51 Duplicate Map

Updated: 2026-05-21T20:30:00-04:00
Session: f51-inventory-full-sweep

## Functional Overlaps

### 1. Data Collection: 4 implementations

| File | Class | Role | Classification |
|------|-------|------|----------------|
| `src/core/ports/data_collector.py` | DataCollectorPort | Abstract protocol | core |
| `src/core/data_collector/collector.py` | (Collector) | Implementation | core |
| `src/core/data_collector/professional.py` | ProfessionalCollector | Implementation | core |
| `src/core/data_collector/scraper.py` | (Scraper) | Implementation | core |
| `src/adapters/data_collector/subprocess_collector.py` | SubprocessCollector | Adapter | core |

**Verdict**: Not duplicate. Proper ports+adapters pattern. **No action needed.**

---

### 2. Data Providers: overlapping capabilities

| Provider | price | candles | news | sentiment | macro |
|----------|-------|---------|------|-----------|-------|
| alpha_vantage | YES | YES | no | no | no |
| twelve_data | YES | YES | no | no | no |
| newsapi | no | no | YES | YES | no |
| news_feed (DDG) | no | no | YES | YES | no |
| reddit_provider | no | no | YES | YES | no |
| boc_provider | no | no | no | no | YES (CA) |
| fed_provider | no | no | no | no | YES (US) |
| wolfram_provider | no | no | no | no | no (math) |

**Verdict**: Intentional priority fallback. alpha_vantage (10) > twelve_data (20) for price. newsapi (5) > others (20) for news. **Not duplicate.**

---

### 3. Neural Expert systems: 1 active implementation

| File | Purpose | Classification |
|------|---------|----------------|
| `src/experts/neural_decision/neural_decision_expert.py` | Heuristics/direction probability, regime detection | core |
| `src/experts/_archive/technical_neural/` | Deleted technical neural expert (PyTorch / scikit-learn MLP) | deleted |

**Verdict**: Resolved. `technical_neural` has been deleted completely and decoupled from `QuantEngine` (which now uses a baseline statistical representation). `neural_decision_expert` remains the active implementation.

---

### 4. Collector implementations in DataHub

| File | Role | Classification |
|------|------|----------------|
| `src/core/data_collector/professional.py` | ProfessionalCollector (API-based, async) | core |
| `src/core/data_collector/scraper.py` | Web scraper | core |
| `src/core/data_collector/collector.py` | Base collector | core |

**Verdict**: Complementary — API vs scraping vs base. **Not duplicate.**

---

### 5. Model Gateway: port vs implementation

| File | Role | Classification |
|------|------|----------------|
| `src/core/ports/model_gateway.py` | ModelGatewayPort (Protocol) | core |
| `src/core/model_serving/gateway.py` | ModelGateway (implementation) | core |

**Verdict**: Proper port/implementation split. **Not duplicate.**

---

### 6. Log directories: 1 active location

| Directory | Files | Purpose | Classification |
|-----------|-------|---------|----------------|
| `runtime/logs/` | 37 | API/CEO logs, smoke tests, screenshots | doc |

**Verdict**: Resolved. Consolidated to `runtime/logs/` as the primary log storage. `output/server/` is removed.

---

### 7. .f51/tmp: stale training artifacts (8.1 GB)

| Path | Classification |
|------|----------------|
| `.f51/tmp/phase1-adapter/` | deprecated |
| `.f51/tmp/superezio-merged/` | deprecated |
| `.f51/tmp/phase1_raw/` | deprecated |
| `.f51/tmp/phase1_numerical_sft_*.jsonl` | deprecated |
| `.f51/tmp/setup_and_train_2gpu.sh` | deprecated |
| `.f51/tmp/setup_phase1_a100.sh` | deprecated |
| `.f51/tmp/merge_adapters.py` | deprecated |
| `.f51/tmp/f51_english_sft.jsonl` | deprecated |
| `.f51/tmp/treino_*.json` | deprecated |

**Total**: 27 files, 8.1 GB. Build surface removed per CLEAN-R2. Not referenced by runtime.

**Verdict**: All **deprecated**. Safe to delete when disk space needed.

---

### 8. data/fraud_datasets: 4 downloaded datasets (3.3 GB)

| Dataset | Classification |
|---------|----------------|
| Financial-Fraud-Dataset | experimental |
| Nigerian-Financial-Transactions | experimental |
| Financial_statements_fraud_dataset | experimental |
| financial-fraud-dpo-exact | experimental |
| financial_fraud_textual_dataset | experimental |

**Total**: 3.3 GB with HuggingFace .cache directories.

**Verdict**: **experimental**. May be used by fraud_rag.py. **Needs verification.**

---

### 9. data/corpus: training artifacts (21 KB)

| File | Classification |
|------|----------------|
| `data/corpus/02_dpo/dpo_batch_001.jsonl` | deprecated |
| `data/corpus/04_eval_locked/eval_cases.jsonl` | deprecated |
| `data/corpus/04_eval_locked/README.md` | deprecated |
| `data/corpus/MANIFEST.json` | deprecated |

**Verdict**: **deprecated**. Not used at runtime. Safe to delete.

---

### 10. scripts/__pycache__: stale bytecache

| File | Source (missing) | Classification |
|------|------------------|----------------|
| `finetune_qwen36_sft.cpython-312.pyc` | Deleted source | deprecated |
| `train_qwen36_3h.cpython-312.pyc` | Deleted source | deprecated |
| `serve_ceo.cpython-312.pyc` | Renamed? | deprecated |
| `server.cpython-312.pyc` | Deleted? | deprecated |
| `eval_pipeline.cpython-312.pyc` | Exists | active |

**Verdict**: 4 of 5 .pyc files reference source files that no longer exist. **Stale cache.** Safe to delete entire __pycache__/.

---

### 11. .f51/partner: external review

| File | Purpose | Classification |
|------|---------|----------------|
| `.f51/partner/review.md` | External review notes | doc |
| `.f51/partner/diff.txt` | External diff | doc |

**Verdict**: **doc**. Not runtime-relevant. Keep for historical reference.

---

### 12. Init-only modules (potential dead code)

| Module | Has non-init source? | Classification |
|--------|---------------------|----------------|
| `src/core/paths/` | No | unknown |
| `src/core/scanner/` | No | unknown |

**Verdict**: May have functionality in __init__.py (795 total lines across all inits). **Needs import verification.**

---

## Summary

| Category | Count | Action |
|----------|-------|--------|
| True duplicates (safe to remove) | 3 | `output/server/` logs, `scripts/__pycache__/`, `data/corpus/` |
| Stale/deprecated artifacts | 2 | `.f51/tmp/` (8.1 GB), `data/fraud_datasets/` (3.3 GB) — verify then optionally delete |
| Not duplicate (intentional) | 5 | Ports/adapters, priority fallbacks, complementary collectors |
| Needs verification | 3 | `technical_neural` vs `neural_decision`, `data/fraud_datasets` usage, init-only modules |
