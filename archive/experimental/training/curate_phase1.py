"""
Curate Phase 1 dataset — Numerical Literacy + Forecasting with SuperEzio persona.
Combines: TAT-QA-CoT, FinGPT Forecaster, flare-finqa
Target: ~2,500 high-quality samples for 1-hour A100 training.
"""
import json
import random
from pathlib import Path

random.seed(42)

RAW = Path(r"C:\Users\marco\Desktop\SuperEzio\.f51\tmp\phase1_raw")
OUT = Path(r"C:\Users\marco\Desktop\SuperEzio\.f51\tmp")
OUT.mkdir(parents=True, exist_ok=True)

# ============================================================
# SUPER-EZIO PERSONA — Numerical + Forecasting Edition
# ============================================================
SYSTEM = """You are Bob, CEO Quant of SuperEzio Trust OS — an AI financial analysis platform.

Your mission is evidence-based mathematical financial analysis. You operate in 3 modes:

1. NUMERICAL REASONING: Extract financial figures from documents/tables, then perform multi-step arithmetic to compute answers. Always show your work step-by-step.

2. RISK PROJECTION: Given fundamentals + context, project probabilistic outcomes with confidence intervals. Separate FACT (verifiable data) from INFERENCE (reasoned projection). Never give buy/sell orders.

3. FRAUD & ANOMALY DETECTION: Identify patterns like structuring, shell company layering, pump schemes, social engineering, and financial statement irregularities.

OUTPUT FORMAT (prefer structured):
- For calculations: show EXTRACTION → COMPUTATION → RESULT
- For projections: show EVIDENCE → ANALYSIS → PROJECTION with confidence (0-1)
- For fraud: show INDICATORS → PATTERN → VERDICT with risk flags

You never invent financial data, prices, or metrics. Every number must be traceable to source evidence.
Markets: Focus on Canadian (TSX, TSX-V) and US (NYSE, NASDAQ, OTC) equities."""

# ============================================================
# LOAD RAW DATA
# ============================================================

def load_jsonl(path):
    data = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            if line.strip():
                data.append(json.loads(line))
    return data

print("Loading raw datasets...")
tatqa = load_jsonl(RAW / "tatqa_cot_train.jsonl")
forecaster = load_jsonl(RAW / "fingpt_forecaster_train.jsonl")
flare = load_jsonl(RAW / "ChanceFocus_flare-finqa_train.jsonl")
convfinqa = load_jsonl(RAW / "FinGPT_fingpt-convfinqa_train.jsonl")

print(f"  TAT-QA-CoT: {len(tatqa)}")
print(f"  Forecaster: {len(forecaster)}")
print(f"  flare-finqa: {len(flare)}")
print(f"  ConvFinQA: {len(convfinqa)}")

# ============================================================
# CURATION — TAT-QA-CoT (best quality, has CoT)
# ============================================================
print("\nCurating TAT-QA-CoT...")
tatqa_samples = []

for row in tatqa:
    if not row.get("answers") or not row.get("messages"):
        continue

    # Get the user question
    user_msg = row["messages"][0]["content"] if row["messages"] else ""
    if not user_msg:
        continue

    # Get the CoT answer
    cot = row["answers"][0] if row["answers"] else ""
    # Skip if answer is too short (likely bad quality)
    if len(cot) < 50:
        continue

    # Build enhanced user prompt: include document context
    context = row.get("document", "")
    if context and len(context) > 3000:
        context = context[:3000] + "..."

    full_question = user_msg
    if context:
        full_question = f"Based on the following financial document, answer the question step-by-step:\n\nDOCUMENT:\n{context}\n\nQUESTION: {user_msg}"

    tatqa_samples.append({
        "messages": [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": full_question},
            {"role": "assistant", "content": cot.strip()},
        ],
        "domain": "numerical_reasoning",
        "source": "TAT-QA-CoT",
    })

# Sort by answer length (longer = more detailed reasoning) and take top 1200
tatqa_samples.sort(key=lambda x: len(x["messages"][2]["content"]), reverse=True)
tatqa_samples = tatqa_samples[:1200]
print(f"  Selected: {len(tatqa_samples)} (top by reasoning depth)")

# ============================================================
# CURATION — FinGPT Forecaster (direct projection)
# ============================================================
print("\nCurating FinGPT Forecaster...")
forecaster_samples = []

for row in forecaster:
    prompt = row.get("prompt", "")
    answer = row.get("answer", "")
    label = row.get("label", "")
    symbol = row.get("symbol", "")

    if not prompt or not answer:
        continue

    # Extract query between <</SYS>> and [/INST]
    if "<</SYS>>" in prompt and "[/INST]" in prompt:
        user_query = prompt.split("<</SYS>>", 1)[1].split("[/INST]", 1)[0].strip()
    else:
        user_query = prompt.replace("[INST]", "").replace("[/INST]", "").strip()

    if len(user_query) < 50:
        continue

    # Format answer with label
    enhanced_answer = f"[Prediction: {symbol} — {label}]\n\n{answer.strip()}"

    forecaster_samples.append({
        "messages": [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": user_query[:3000]},
            {"role": "assistant", "content": enhanced_answer[:4000]},
        ],
        "domain": "forecasting",
        "source": "FinGPT-Forecaster",
    })

# Take all ~1230
random.shuffle(forecaster_samples)
forecaster_samples = forecaster_samples[:800]
print(f"  Selected: {len(forecaster_samples)}")

# ============================================================
# CURATION — flare-finqa (numerical extraction + computation)
# ============================================================
print("\nCurating flare-finqa...")
flare_samples = []

for row in flare:
    query_text = row.get("query", "")
    answer = row.get("answer", "")
    question = row.get("text", "")

    if not query_text or not answer:
        continue

    # Skip yes/no answers — we want numerical reasoning
    if answer.lower() in ("yes", "no", "true", "false"):
        continue

    # The query contains the context, text contains the question
    # Build a proper prompt
    full_question = f"{query_text}\n\nQuestion: {question}"
    if len(full_question) > 4000:
        full_question = full_question[:4000] + "..."

    # For numerical answers, add a reasoning wrapper
    enhanced_answer = f"Based on the financial data provided:\nResult: {answer}"

    flare_samples.append({
        "messages": [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": full_question},
            {"role": "assistant", "content": enhanced_answer},
        ],
        "domain": "numerical_reasoning",
        "source": "flare-finqa",
    })

# Take top 500 by context length (richer context = better quality)
flare_samples.sort(key=lambda x: len(x["messages"][1]["content"]), reverse=True)
flare_samples = flare_samples[:500]
print(f"  Selected: {len(flare_samples)}")

# ============================================================
# MERGE + SHUFFLE + SAVE
# ============================================================
all_samples = tatqa_samples + forecaster_samples + flare_samples
random.shuffle(all_samples)

# Generate train (95%) and eval (5%) splits
split = int(len(all_samples) * 0.95)
train = all_samples[:split]
eval_samples = all_samples[split:]

# Save train
train_path = OUT / "phase1_numerical_sft_train.jsonl"
with open(train_path, "w", encoding="utf-8") as f:
    for s in train:
        f.write(json.dumps(s, ensure_ascii=False) + "\n")

# Save eval
eval_path = OUT / "phase1_numerical_sft_eval.jsonl"
with open(eval_path, "w", encoding="utf-8") as f:
    for s in eval_samples:
        f.write(json.dumps(s, ensure_ascii=False) + "\n")

print(f"\n{'=' * 60}")
print(f"DATASET CURATION COMPLETE")
print(f"{'=' * 60}")
print(f"  Train: {len(train)} samples → {train_path}")
print(f"  Eval:  {len(eval_samples)} samples → {eval_path}")
print(f"  Total: {len(all_samples)} samples")

# Stats
domains = {}
sources = {}
total_user_len = 0
total_assistant_len = 0
for s in all_samples:
    d = s["domain"]
    domains[d] = domains.get(d, 0) + 1
    src = s["source"]
    sources[src] = sources.get(src, 0) + 1
    total_user_len += len(s["messages"][1]["content"])
    total_assistant_len += len(s["messages"][2]["content"])

print(f"\n  By domain:")
for d, c in sorted(domains.items()):
    print(f"    {d}: {c}")

print(f"\n  By source:")
for src, c in sorted(sources.items()):
    print(f"    {src}: {c}")

print(f"\n  Avg user msg length: {total_user_len // len(all_samples):,} chars")
print(f"  Avg assistant msg length: {total_assistant_len // len(all_samples):,} chars")

# Estimate training time
print(f"\n{'=' * 60}")
print(f"TRAINING TIME ESTIMATES")
print(f"{'=' * 60}")
# L40S: ~10 samples/min
# A100 80GB: ~35-45 samples/min (bigger batch + faster compute)
for gpu, spm in [("1x L40S 46GB", 10), ("1x A100 80GB", 40), ("2x A100 80GB", 70)]:
    minutes = len(train) / spm
    hours = minutes / 60
    print(f"  {gpu}: {minutes:.0f} min ({hours:.1f}h)")

print("\nDone!")
