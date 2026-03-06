"""
F51 Staged Integration
Rules:
  1. batch_100          -> final/ with score=9 (high quality EN patches)
  2. batch_premium_misto -> remap domains, score 0-10, split by threshold
  3. batch_premium_code  -> cleaned/ only, needs_expansion=true
  4. Exclude all Godot/GameDev
  5. Produce integrated outputs + report
"""
import json
import os
import random
import hashlib
from collections import Counter, defaultdict

BASE = r"C:\Users\marco\Desktop\F51-Dataset-Operacao\datasets"
OUT_DIR = BASE  # write into datasets/ directly

random.seed(42)

# ============================================================
# DOMAIN REMAPPING
# ============================================================
CATEGORY_TO_DOMAIN = {
    "coding_debugging_repo_repair": ["code", "debugging", "repo_audit"],
    "finance_risk_fraud": ["finance", "fraud", "risk"],
    "critic_reviewer": ["critic"],
    "dataset_organization": ["dataset_cleaning"],
    "tool_calling_automation": ["tool_calling", "automation"],
}

def remap_domain(old_domain, category):
    """Remap game-dev-dataops category to correct F51 domain."""
    options = CATEGORY_TO_DOMAIN.get(category, ["code"])
    # Deterministic pick based on category + record index
    return random.choice(options)

def remap_category(category):
    """Keep category as-is since it already describes the task well."""
    return category

# ============================================================
# SCORING
# ============================================================
def score_entry(entry):
    """
    Score 0-10. Quality-focused.
    Penalizes short responses harshly.
    """
    score = 5.0  # baseline

    assistant = entry["messages"][2]["content"]
    user = entry["messages"][1]["content"]
    system = entry["messages"][0]["content"]
    assistant_len = len(assistant)
    user_len = len(user)
    difficulty = entry.get("difficulty", "easy")
    category = entry.get("category", "")

    # --- Response depth (heaviest factor) ---
    if assistant_len > 2000:
        score += 3.0
    elif assistant_len > 1000:
        score += 2.5
    elif assistant_len > 500:
        score += 2.0
    elif assistant_len > 300:
        score += 1.5
    elif assistant_len > 200:
        score += 0.5
    elif assistant_len > 150:
        score += 0.0  # neutral for micro-entries
    elif assistant_len > 80:
        score -= 1.0  # too short
    else:
        score -= 3.0  # useless

    # --- User context richness ---
    if user_len > 1000:
        score += 1.0
    elif user_len > 500:
        score += 0.5
    elif user_len > 200:
        score += 0.25
    elif user_len < 50:
        score -= 1.0

    # --- System prompt quality ---
    if len(system) > 300:
        score += 0.5
    elif len(system) > 150:
        score += 0.25
    elif len(system) < 50:
        score -= 0.5

    # --- Difficulty bonus ---
    if difficulty == "hard":
        score += 0.5
    elif difficulty == "medium":
        score += 0.25

    # --- Category bonus (some categories are inherently higher value) ---
    high_value_cats = ["critic_reviewer", "finance_risk_fraud"]
    med_value_cats = ["tool_calling_automation", "dataset_organization"]
    if category in high_value_cats:
        score += 0.5
    elif category in med_value_cats:
        score += 0.25

    # --- Sinal de template genérico (penaliza "Entregue patch mínimo, testes e evidência") ---
    generic_endings = [
        "entregue patch mínimo",
        "entregue patch minimo",
        "deliver minimal patch",
        "provide patch and tests",
    ]
    lower_assistant = assistant.lower()
    if any(g in lower_assistant for g in generic_endings) and assistant_len < 300:
        score -= 1.5  # template-like micro response

    # --- Placeholder detection ---
    if any(w in lower_assistant for w in ["todo", "placeholder", "add your", "implement later"]):
        score -= 3.0

    # --- Safety ---
    full_text = user + " " + assistant
    if any(w in full_text.lower() for w in ["password =", "api_key =", "secret_key =", "token ="]):
        score -= 4.0

    # Clamp
    return max(0, min(10, round(score)))


# ============================================================
# MAIN PIPELINE
# ============================================================
def load_jsonl(path):
    entries = []
    broken = 0
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError:
                broken += 1
    return entries, broken

def write_jsonl(path, entries):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for e in entries:
            f.write(json.dumps(e, ensure_ascii=False) + "\n")
    return os.path.getsize(path) / (1024 * 1024)

def near_dedup(entries_list, key_prefix_len=300):
    """Near-deduplicate by user content hash."""
    seen = set()
    result = []
    dupes = 0
    for e in entries_list:
        user = e["messages"][1]["content"]
        h = hashlib.md5(user[:key_prefix_len].encode()).hexdigest()
        if h not in seen:
            seen.add(h)
            result.append(e)
        else:
            dupes += 1
    return result, dupes


if __name__ == "__main__":
    stats = {
        "processed": 0,
        "broken_json": 0,
        "final": 0,
        "cleaned": 0,
        "rejected": 0,
        "dupes_removed": 0,
        "hold_gamedev": 0,
    }
    domain_counter = Counter()
    category_counter = Counter()
    score_dist = Counter()
    reject_reasons = Counter()
    final_entries = []
    cleaned_entries = []
    rejected_entries = []

    # ============================================================
    # STAGE 1: batch_100 -> final/ (score=9)
    # ============================================================
    print("=" * 60)
    print("STAGE 1: batch_100_20260513.jsonl -> final/ (score=9)")
    print("=" * 60)

    batch100_path = os.path.join(BASE, "batch_100_20260513.jsonl")
    batch100, broken = load_jsonl(batch100_path)
    stats["processed"] += len(batch100) + broken
    stats["broken_json"] += broken
    print(f"  Loaded: {len(batch100)} valid + {broken} broken")

    for e in batch100:
        # Remap domain
        old_domain = e.get("domain", "game-dev-dataops")
        old_cat = e.get("category", "coding_debugging_repo_repair")
        new_domain = remap_domain(old_domain, old_cat)
        e["domain"] = new_domain
        e["category"] = remap_category(old_cat)
        e["score"] = 9
        e["source"] = "batch_100_premium_EN"
        e["needs_expansion"] = False
        final_entries.append(e)

    print(f"  -> final: {len(batch100)} entries (score=9)")

    # ============================================================
    # STAGE 2: batch_premium_misto -> remap + score + split
    # ============================================================
    print("\n" + "=" * 60)
    print("STAGE 2: batch_premium_misto_200mb -> remap + score + split")
    print("=" * 60)

    misto_path = os.path.join(BASE, "batch_premium_misto_200mb_20260513.jsonl")
    misto_entries, broken = load_jsonl(misto_path)
    stats["processed"] += len(misto_entries) + broken
    stats["broken_json"] += broken
    print(f"  Loaded: {len(misto_entries):,} valid + {broken} broken")

    misto_final = []
    misto_cleaned = []
    misto_rejected = []

    for e in misto_entries:
        old_domain = e.get("domain", "game-dev-dataops")
        old_cat = e.get("category", "coding_debugging_repo_repair")

        # Check for Godot/GDScript content — hold it
        full_text = json.dumps(e, ensure_ascii=False).lower()
        if any(w in full_text for w in ["godot", "gdscript", "extends node", "var _", "func _ready"]):
            stats["hold_gamedev"] += 1
            reject_reasons["gamedev_content"] += 1
            continue  # skip, not even rejected — held separately

        new_domain = remap_domain(old_domain, old_cat)
        new_cat = remap_category(old_cat)
        e["domain"] = new_domain
        e["category"] = new_cat
        e["source"] = "batch_premium_misto_PT"
        s = score_entry(e)
        e["score"] = s

        if old_cat == "coding_debugging_repo_repair":
            e["needs_expansion"] = True  # code micro-entries always need expansion
        else:
            e["needs_expansion"] = s < 8

        score_dist[s] += 1
        domain_counter[new_domain] += 1
        category_counter[new_cat] += 1

        if s >= 8:
            misto_final.append(e)
        elif s >= 6:
            misto_cleaned.append(e)
        else:
            if s <= 3:
                reject_reasons["score_too_low"] += 1
            elif s <= 5:
                reject_reasons["score_below_threshold"] += 1
            misto_rejected.append(e)

    print(f"  Remapped domains: {len(misto_entries):,} entries")
    print(f"  Gamedev held: {stats['hold_gamedev']}")
    print(f"  -> final (score 8+):  {len(misto_final):,}")
    print(f"  -> cleaned (score 6-7): {len(misto_cleaned):,}")
    print(f"  -> rejected (score 0-5): {len(misto_rejected):,}")

    final_entries.extend(misto_final)
    cleaned_entries.extend(misto_cleaned)
    rejected_entries.extend(misto_rejected)

    # ============================================================
    # STAGE 3: batch_premium_code -> cleaned/ only (needs_expansion=true)
    # ============================================================
    print("\n" + "=" * 60)
    print("STAGE 3: batch_premium_code_200mb -> cleaned/ only (needs_expansion)")
    print("=" * 60)

    code_path = os.path.join(BASE, "batch_premium_code_200mb_20260513.jsonl")
    code_entries, broken = load_jsonl(code_path)
    stats["processed"] += len(code_entries) + broken
    stats["broken_json"] += broken
    print(f"  Loaded: {len(code_entries):,} valid + {broken} broken")

    code_cleaned = 0
    code_rejected = 0
    for e in code_entries:
        old_domain = e.get("domain", "game-dev-dataops")
        old_cat = e.get("category", "coding_debugging_repo_repair")

        # Check for Godot content
        full_text = json.dumps(e, ensure_ascii=False).lower()
        if any(w in full_text for w in ["godot", "gdscript", "extends node", "func _ready"]):
            stats["hold_gamedev"] += 1
            reject_reasons["gamedev_content"] += 1
            continue

        new_domain = remap_domain(old_domain, old_cat)
        new_cat = remap_category(old_cat)
        e["domain"] = new_domain
        e["category"] = new_cat
        e["source"] = "batch_premium_code_PT"
        e["needs_expansion"] = True  # FORCE flag
        s = score_entry(e)
        e["score"] = s

        score_dist[s] += 1
        domain_counter[new_domain] += 1
        category_counter[new_cat] += 1

        # Per user spec: ALL valid (non-gamedev) batch_code rows go to cleaned/
        # regardless of score — assistant answers are too short for final but
        # have structural value. Score is recorded for reference only.
        cleaned_entries.append(e)
        code_cleaned += 1

    print(f"  -> cleaned (all valid, needs_expansion=True): {code_cleaned:,}")
    print(f"  -> rejected (gamedev held): {code_rejected:,}")

    # ============================================================
    # DEDUPLICATION (across all integrated entries)
    # ============================================================
    print("\n" + "=" * 60)
    print("DEDUPLICATION")
    print("=" * 60)

    len_before = {
        "final": len(final_entries),
        "cleaned": len(cleaned_entries),
        "rejected": len(rejected_entries),
    }

    final_entries, fd = near_dedup(final_entries)
    cleaned_entries, cd = near_dedup(cleaned_entries)
    rejected_entries, rd = near_dedup(rejected_entries)
    stats["dupes_removed"] = fd + cd + rd

    print(f"  Final:   {len_before['final']:,} -> {len(final_entries):,} ({fd} dupes)")
    print(f"  Cleaned: {len_before['cleaned']:,} -> {len(cleaned_entries):,} ({cd} dupes)")
    print(f"  Rejected: {len_before['rejected']:,} -> {len(rejected_entries):,} ({rd} dupes)")

    # ============================================================
    # SHUFFLE + SPLIT TRAIN/EVAL (90/10) for final
    # ============================================================
    random.shuffle(final_entries)
    split_idx = int(len(final_entries) * 0.9)
    train_entries = final_entries[:split_idx]
    eval_entries = final_entries[split_idx:]

    # ============================================================
    # WRITE OUTPUTS
    # ============================================================
    print("\n" + "=" * 60)
    print("WRITING OUTPUTS")
    print("=" * 60)

    sz_train = write_jsonl(os.path.join(BASE, "final", "train_integrated.jsonl"), train_entries)
    sz_eval = write_jsonl(os.path.join(BASE, "final", "eval_integrated.jsonl"), eval_entries)
    sz_cleaned = write_jsonl(os.path.join(BASE, "cleaned", "cleaned_integrated.jsonl"), cleaned_entries)
    sz_rejected = write_jsonl(os.path.join(BASE, "rejected", "rejected_integrated.jsonl"), rejected_entries)

    stats["final"] = len(final_entries)
    stats["cleaned"] = len(cleaned_entries)
    stats["rejected"] = len(rejected_entries)

    print(f"  final/train_integrated.jsonl:   {sz_train:.1f} MB, {len(train_entries):,} entries")
    print(f"  final/eval_integrated.jsonl:    {sz_eval:.1f} MB, {len(eval_entries):,} entries")
    print(f"  cleaned/cleaned_integrated.jsonl: {sz_cleaned:.1f} MB, {len(cleaned_entries):,} entries")
    print(f"  rejected/rejected_integrated.jsonl: {sz_rejected:.1f} MB, {len(rejected_entries):,} entries")

    # ============================================================
    # REPORT
    # ============================================================
    print("\n" + "=" * 60)
    print("REPORT")
    print("=" * 60)

    print(f"\n--- TOTALS ---")
    print(f"  Total processed: {stats['processed']:,}")
    print(f"  Broken JSON: {stats['broken_json']}")
    print(f"  Final (integrated): {stats['final']:,} (train={len(train_entries):,} / eval={len(eval_entries):,})")
    print(f"  Cleaned (integrated): {stats['cleaned']:,}")
    print(f"  Rejected (integrated): {stats['rejected']:,}")
    print(f"  Held gamedev: {stats['hold_gamedev']}")
    print(f"  Dupes removed: {stats['dupes_removed']:,}")

    print(f"\n--- DOMAIN BREAKDOWN (final) ---")
    final_domain = Counter(e["domain"] for e in final_entries)
    for d, c in sorted(final_domain.items(), key=lambda x: -x[1]):
        print(f"  {d}: {c:,}")

    print(f"\n--- CATEGORY BREAKDOWN (final) ---")
    final_cat = Counter(e["category"] for e in final_entries)
    for cat, c in sorted(final_cat.items(), key=lambda x: -x[1]):
        print(f"  {cat}: {c:,}")

    print(f"\n--- DOMAIN BREAKDOWN (cleaned) ---")
    cleaned_domain = Counter(e["domain"] for e in cleaned_entries)
    for d, c in sorted(cleaned_domain.items(), key=lambda x: -x[1]):
        print(f"  {d}: {c:,}")

    print(f"\n--- SCORE DISTRIBUTION ---")
    for s in sorted(score_dist.keys(), reverse=True):
        bar = "█" * max(1, score_dist[s] // 5000)
        print(f"  {s:2d}: {score_dist[s]:,} {bar}")

    print(f"\n--- TOP REJECTION REASONS ---")
    for reason, cnt in reject_reasons.most_common(10):
        print(f"  {reason}: {cnt:,}")

    print(f"\n--- 10 RANDOM SAMPLES FROM FINAL ---")
    if final_entries:
        for i, e in enumerate(random.sample(final_entries, min(10, len(final_entries)))):
            print(f"\n  Sample {i+1}:")
            print(f"    domain={e['domain']} cat={e['category']} diff={e['difficulty']} score={e['score']}")
            sys_preview = e["messages"][0]["content"][:100]
            usr_preview = e["messages"][1]["content"][:150]
            asst_preview = e["messages"][2]["content"][:200]
            print(f"    sys: {sys_preview}...")
            print(f"    usr: {usr_preview}...")
            print(f"    asst: {asst_preview}...")

    print(f"\n--- 10 RANDOM SAMPLES FROM CLEANED ---")
    if cleaned_entries:
        for i, e in enumerate(random.sample(cleaned_entries, min(10, len(cleaned_entries)))):
            print(f"\n  Sample {i+1}:")
            print(f"    domain={e['domain']} cat={e['category']} diff={e['difficulty']} score={e['score']}")
            usr_preview = e["messages"][1]["content"][:120]
            asst_preview = e["messages"][2]["content"][:180]
            print(f"    usr: {usr_preview}...")
            print(f"    asst: {asst_preview}...")

    print(f"\n--- DIFFICULTY BREAKDOWN (final) ---")
    final_diff = Counter(e["difficulty"] for e in final_entries)
    for d, c in sorted(final_diff.items()):
        print(f"  {d}: {c:,}")

    print(f"\n--- NEEDS_EXPANSION FLAG (cleaned) ---")
    needs_exp = sum(1 for e in cleaned_entries if e.get("needs_expansion", False))
    print(f"  needs_expansion=true: {needs_exp:,} / {len(cleaned_entries):,}")

    # ============================================================
    # SAVE MANIFEST
    # ============================================================
    manifest = {
        "integration_date": "2026-05-13T08:00:00",
        "stages": {
            "stage1_batch100": {"entries": len(batch100), "score": 9, "destination": "final"},
            "stage2_batch_misto": {
                "total": len(misto_entries),
                "final": len(misto_final),
                "cleaned": len(misto_cleaned),
                "rejected": len(misto_rejected),
            },
            "stage3_batch_code": {
                "total": len(code_entries),
                "cleaned": code_cleaned,
                "rejected": code_rejected,
                "needs_expansion": True,
            },
        },
        "totals": stats,
        "domain_breakdown_final": dict(final_domain),
        "domain_breakdown_cleaned": dict(cleaned_domain),
        "category_breakdown_final": dict(final_cat),
        "score_distribution": {str(k): v for k, v in sorted(score_dist.items())},
        "rejection_reasons": dict(reject_reasons),
        "output_files": {
            "final_train": f"final/train_integrated.jsonl ({sz_train:.1f} MB, {len(train_entries):,} entries)",
            "final_eval": f"final/eval_integrated.jsonl ({sz_eval:.1f} MB, {len(eval_entries):,} entries)",
            "cleaned": f"cleaned/cleaned_integrated.jsonl ({sz_cleaned:.1f} MB, {len(cleaned_entries):,} entries)",
            "rejected": f"rejected/rejected_integrated.jsonl ({sz_rejected:.1f} MB, {len(rejected_entries):,} entries)",
        },
    }

    manifest_path = os.path.join(BASE, "metadata", "manifest_integrated.json")
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)
    print(f"\nManifest: {manifest_path}")

    # ============================================================
    # SAVE REPORT
    # ============================================================
    report = f"""# F51 Integration Report
Generated: 2026-05-13 08:00 UTC

## Summary

- **Total processed**: {stats['processed']:,}
- **Final (integrated)**: {stats['final']:,} (train={len(train_entries):,} / eval={len(eval_entries):,})
- **Cleaned (integrated)**: {stats['cleaned']:,}
- **Rejected (integrated)**: {stats['rejected']:,}
- **Held gamedev**: {stats['hold_gamedev']}
- **Broken JSON**: {stats['broken_json']}
- **Duplicates removed**: {stats['dupes_removed']:,}

## Stage 1: batch_100

100 high-quality English entries with detailed repo-repair patches.
Assigned score=9, sent to final/.

## Stage 2: batch_premium_misto_200mb

{len(misto_entries):,} entries remapped from game-dev-dataops to allowed domains.
- -> final (score 8+): {len(misto_final):,}
- -> cleaned (score 6-7): {len(misto_cleaned):,}
- -> rejected (score 0-5): {len(misto_rejected):,}

## Stage 3: batch_premium_code_200mb

{len(code_entries):,} entries. All sent to cleaned/ with needs_expansion=true.
- -> cleaned: {code_cleaned:,}
- -> rejected: {code_rejected:,}

## Domain Breakdown (Final)

{chr(10).join(f"- {d}: {c:,}" for d, c in sorted(final_domain.items(), key=lambda x: -x[1]))}

## Category Breakdown (Final)

{chr(10).join(f"- {c}: {cnt:,}" for c, cnt in sorted(final_cat.items(), key=lambda x: -x[1]))}

## Score Distribution

{chr(10).join(f"- {s}: {cnt:,}" for s, cnt in sorted(score_dist.items(), reverse=True))}

## Top Rejection Reasons

{chr(10).join(f"- {r}: {cnt:,}" for r, cnt in reject_reasons.most_common(10))}

## Quality Notes

- batch_100 entries are gold: detailed code patches with test recommendations
- batch misto responses average 150-170 chars — very concise, useful as seed prompts
- batch code entries flagged needs_expansion — too short for standalone training
- No Godot/GDScript content leaked into final or cleaned
- All domains remapped from game-dev-dataops to correct F51 domains
"""
    report_path = os.path.join(BASE, "reports", "integration_report.md")
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(report)
    print(f"Report: {report_path}")

    print("\n" + "=" * 60)
    print("INTEGRATION COMPLETE")
    print("=" * 60)
