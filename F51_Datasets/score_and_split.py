"""
F51 Dataset Scorer + Train/Eval Splitter
Scores each entry 0-10, splits 90/10 train/eval, and organizes into the datasets/ directory.
"""
import json
import os
import hashlib
import random
from collections import Counter

INPUT = r"C:\Users\marco\Desktop\F51_Datasets\sft_output\f51_sft_combined.jsonl"
DATASETS_DIR = r"C:\Users\marco\Desktop\F51-Dataset-Operacao\datasets"

random.seed(42)

# ============================================================
# SCORING
# ============================================================
def score_entry(entry):
    """
    Score 0-10 based on: source quality, response depth, realism, usefulness, clarity.
    All entries in this batch are structurally valid (we generated them).
    """
    score = 5.0  # baseline

    domain = entry.get("domain", "")
    category = entry.get("category", "")
    difficulty = entry.get("difficulty", "easy")
    metadata = entry.get("metadata", {})
    source = metadata.get("source", "")

    assistant_msg = entry["messages"][2]["content"]
    assistant_len = len(assistant_msg)
    user_msg = entry["messages"][1]["content"]
    user_len = len(user_msg)

    # --- Source quality bonus (0 to +2.5) ---
    source_bonus = {
        "AdaptLLM/ConvFinQA": 2.5,
        "ninty-seven/MultiAgentFraudBench": 2.0,
        "zefang-liu/phishing-email-dataset": 1.5,
        "amitkedia/Financial-Fraud-Dataset": 1.5,
        "CiferAI/Cifer-Fraud-Detection-Dataset-AF": 1.0,
        "TheFinAI/fiqa-sentiment-classification": 1.0,
    }
    for key, bonus in source_bonus.items():
        if key in str(source):
            score += bonus
            break

    # --- Category bonus (0 to +1.0) ---
    if category in ("financial_qa", "social_fraud"):
        score += 1.0
    elif category in ("phishing_detection", "document_fraud"):
        score += 0.5
    elif category == "transaction_risk":
        score += 0.0  # template-generated, lower uniqueness
    elif category == "sentiment_analysis":
        score += -0.5  # short, lower training value

    # --- Difficulty bonus (0 to +1.0) ---
    if difficulty == "hard":
        score += 1.0
    elif difficulty == "medium":
        score += 0.5

    # --- Response depth (0 to +1.5) ---
    if assistant_len > 2000:
        score += 1.5
    elif assistant_len > 1000:
        score += 1.0
    elif assistant_len > 500:
        score += 0.5
    elif assistant_len < 200:
        score -= 1.0  # too short to teach anything

    # --- User context richness (0 to +0.5) ---
    if user_len > 1500:
        score += 0.5
    elif user_len > 800:
        score += 0.25

    # --- Safety check (0 to -3.0) ---
    full_text = user_msg + " " + assistant_msg
    lower_text = full_text.lower()
    if any(term in lower_text for term in ['password', 'api_key', 'secret_key', 'token=', '@gmail.com', '@yahoo.com']):
        score -= 3.0
    if 'hack' in lower_text and 'fraud' not in lower_text:
        score -= 1.0

    # --- Originality check ---
    # Template-generated CiferAI entries: penalize repetition
    if "Transaction data:" in user_msg and "TRANSFER" in assistant_msg:
        # Check for template markers
        score -= 0.5  # Slight penalty for template-generated

    # Clamp to 0-10
    score = max(0, min(10, round(score)))
    return score


def classify_entry(score):
    """Map score to output directory."""
    if score >= 8:
        return "final"
    elif score >= 6:
        return "cleaned"
    else:
        return "rejected"


# ============================================================
# MAIN
# ============================================================
if __name__ == "__main__":
    print("Loading entries...")
    entries = []
    with open(INPUT, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                entries.append(json.loads(line))
    print(f"Loaded: {len(entries):,} entries")

    # Score each entry
    print("Scoring...")
    scored_entries = []
    score_dist = Counter()
    for entry in entries:
        s = score_entry(entry)
        entry["score"] = s
        scored_entries.append(entry)
        score_dist[s] += 1

    print("\nScore Distribution:")
    for s in sorted(score_dist.keys(), reverse=True):
        bar = "█" * (score_dist[s] // 2000)
        print(f"  {s:2d}: {score_dist[s]:,} {bar}")

    # Classify into final/cleaned/rejected
    final_entries = []
    cleaned_entries = []
    rejected_entries = []
    hold_gamedev = []

    for e in scored_entries:
        classification = classify_entry(e["score"])
        if classification == "final":
            final_entries.append(e)
        elif classification == "cleaned":
            cleaned_entries.append(e)
        else:
            rejected_entries.append(e)

    print("\nClassification:")
    print(f"  final (8-10): {len(final_entries):,}")
    print(f"  cleaned (6-7): {len(cleaned_entries):,}")
    print(f"  rejected (0-5): {len(rejected_entries):,}")

    # Near-deduplication within final and cleaned sets
    print("\nNear-dedup within final and cleaned...")
    def near_dedup(entries_list):
        seen_hashes = set()
        result = []
        dupes = 0
        for e in entries_list:
            user = e["messages"][1]["content"]
            h = hashlib.md5(user[:300].encode()).hexdigest()
            if h not in seen_hashes:
                seen_hashes.add(h)
                result.append(e)
            else:
                dupes += 1
        return result, dupes

    final_entries, final_dupes = near_dedup(final_entries)
    cleaned_entries, cleaned_dupes = near_dedup(cleaned_entries)
    print(f"  Final near-dupes removed: {final_dupes}")
    print(f"  Cleaned near-dupes removed: {cleaned_dupes}")

    # Split train/eval (90/10) from final entries
    random.shuffle(final_entries)
    split_idx = int(len(final_entries) * 0.9)
    train_entries = final_entries[:split_idx]
    eval_entries = final_entries[split_idx:]

    print("\nTrain/Eval Split:")
    print(f"  train: {len(train_entries):,}")
    print(f"  eval: {len(eval_entries):,}")

    # Write output files to datasets/ directory
    os.makedirs(os.path.join(DATASETS_DIR, "final"), exist_ok=True)
    os.makedirs(os.path.join(DATASETS_DIR, "cleaned"), exist_ok=True)
    os.makedirs(os.path.join(DATASETS_DIR, "rejected"), exist_ok=True)
    os.makedirs(os.path.join(DATASETS_DIR, "scored"), exist_ok=True)

    def write_jsonl(path, entries_list):
        with open(path, "w", encoding="utf-8") as f:
            for e in entries_list:
                f.write(json.dumps(e, ensure_ascii=False) + "\n")
        return os.path.getsize(path) / (1024 * 1024)

    print("\nWriting output files...")
    sz_train = write_jsonl(os.path.join(DATASETS_DIR, "final", "train.jsonl"), train_entries)
    sz_eval = write_jsonl(os.path.join(DATASETS_DIR, "final", "eval.jsonl"), eval_entries)
    sz_cleaned = write_jsonl(os.path.join(DATASETS_DIR, "cleaned", "cleaned.jsonl"), cleaned_entries)
    sz_rejected = write_jsonl(os.path.join(DATASETS_DIR, "rejected", "rejected.jsonl"), rejected_entries)
    sz_scored = write_jsonl(os.path.join(DATASETS_DIR, "scored", "scored.jsonl"), scored_entries)

    total_final_sz = sz_train + sz_eval
    print(f"  final/train.jsonl: {sz_train:.1f} MB ({len(train_entries):,} entries)")
    print(f"  final/eval.jsonl: {sz_eval:.1f} MB ({len(eval_entries):,} entries)")
    print(f"  cleaned/cleaned.jsonl: {sz_cleaned:.1f} MB ({len(cleaned_entries):,} entries)")
    print(f"  rejected/rejected.jsonl: {sz_rejected:.1f} MB ({len(rejected_entries):,} entries)")
    print(f"  scored/scored.jsonl: {sz_scored:.1f} MB ({len(scored_entries):,} entries)")

    # Update manifest
    manifest = {
        "dataset_name": "F51 Synthetic Dataset - Code Finance Critic",
        "created_by": "F51 Labs",
        "processed_date": "2026-05-13T06:00:00",
        "domains": ["fraud", "finance"],
        "excluded_domains": ["gamedev", "godot", "gdscript"],
        "total_raw_examples": len(scored_entries),
        "total_cleaned_examples": len(cleaned_entries),
        "total_final_examples": len(final_entries),
        "total_final_train": len(train_entries),
        "total_final_eval": len(eval_entries),
        "total_rejected_examples": len(rejected_entries),
        "total_hold_gamedev_examples": 94,
        "estimated_size_mb": round(sz_train + sz_eval + sz_cleaned + sz_scored, 1),
        "final_train_mb": round(sz_train, 1),
        "final_eval_mb": round(sz_eval, 1),
        "estimated_tokens": sum(len(json.dumps(e, ensure_ascii=False)) for e in train_entries) // 4,
        "estimated_eval_tokens": sum(len(json.dumps(e, ensure_ascii=False)) for e in eval_entries) // 4,
        "score_distribution": {str(k): v for k, v in sorted(score_dist.items())},
        "sources": {
            "CiferAI/Cifer-Fraud-Detection-Dataset-AF": len([e for e in scored_entries if "CiferAI" in str(e.get("metadata", {}).get("source", ""))]),
            "amitkedia/Financial-Fraud-Dataset": len([e for e in scored_entries if "amitkedia" in str(e.get("metadata", {}).get("source", ""))]),
            "zefang-liu/phishing-email-dataset": len([e for e in scored_entries if "phishing" in str(e.get("metadata", {}).get("source", ""))]),
            "ninty-seven/MultiAgentFraudBench": len([e for e in scored_entries if "MultiAgent" in str(e.get("metadata", {}).get("source", ""))]),
            "AdaptLLM/ConvFinQA": len([e for e in scored_entries if "ConvFinQA" in str(e.get("metadata", {}).get("source", ""))]),
            "TheFinAI/fiqa-sentiment-classification": len([e for e in scored_entries if "fiqa" in str(e.get("metadata", {}).get("source", ""))]),
        },
        "quality_notes": [
            "496 MB combined SFT dataset built from 6 public Hugging Face datasets",
            "All entries converted to unified domain/category/difficulty + messages[system/user/assistant] format",
            "Rule-based scoring: source quality + response depth + difficulty + clarity + safety",
            "Template-generated CiferAI transaction risk entries form the bulk (377k entries)",
            "High-quality sources: ConvFinQA (8,514), MultiAgentFraudBench (14,700), phishing (18,634)",
            "94 gamedev entries remain held from previous processing run — not included in final",
        ],
        "known_risks": [
            "CiferAI transaction risk entries use rule-based templates, not LLM-generated explanations — lower depth than ideal",
            "Heavy imbalance toward easy difficulty (370k easy vs 7.6k hard) — may bias model toward simpler responses",
            "Financial-fraud split is 99% fraud vs 1% finance — need more finance diversity",
            "No code, python, debugging, or tool_calling domain entries yet",
            "LEIAME.md still contains plaintext API keys — rotate before git operations",
        ],
        "next_actions": [
            "Generate LLM-enriched explanations for top 10k CiferAI entries using DeepSeek/Gemini",
            "Generate ~50k entries across code/python/debugging/refactoring domains",
            "Balance difficulty distribution with more medium/hard synthetic cases",
            "Add tool_calling and automation domain entries",
            "Run QLoRA fine-tuning test with this dataset on Qwen2.5-Coder-7B",
            "Re-verify no secrets in final dataset",
        ]
    }

    manifest_path = os.path.join(DATASETS_DIR, "metadata", "manifest.json")
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)
    print(f"\nManifest updated: {manifest_path}")

    # Category breakdown for final entries
    final_cats = Counter()
    for e in final_entries:
        final_cats[f"{e['domain']}/{e['category']}"] += 1
    print("\nFinal category breakdown:")
    for cat, cnt in final_cats.most_common():
        print(f"  {cat}: {cnt:,}")

    # Difficulty breakdown for final entries
    final_diffs = Counter()
    for e in final_entries:
        final_diffs[e['difficulty']] += 1
    print("\nFinal difficulty breakdown:")
    for d, cnt in final_diffs.most_common():
        print(f"  {d}: {cnt:,}")
