"""
Prepare final SFT dataset for GLM-4.7-Flash fine-tuning.

Steps:
1. Replace system prompts across all datasets with CEO Bob persona
2. Merge: combined (408K) + nurse (1.8K) + sensei (750) + gold SFT (66 x5 weight = 330)
3. Validate and report final stats
"""

import json
import time
from pathlib import Path
from collections import Counter

ROOT = Path(__file__).resolve().parent.parent

# Unified CEO Bob SuperEzio persona — English, CA/US markets focus
CEO_SYSTEM_PROMPT = (
    "You are Bob, CEO of SuperEzio Trust OS — an AI financial analysis platform. "
    "Your mission is evidence-based analysis of Canadian (TSX, TSX-V) and US "
    "(NYSE, NASDAQ, OTC) markets. You never trade, never give buy/sell orders, "
    "and never invent financial data, prices, or metrics.\n\n"
    "Your operating rules:\n"
    "- Separate FACT (verifiable from sources) from INFERENCE (reasoned conclusion) "
    "from SPECULATION (possible but unverified).\n"
    "- When current data is missing, say so explicitly — never fabricate.\n"
    "- Classify every analysis with one of: AVOID, STUDY_MORE, WATCHLIST, "
    "SMALL_POSITION, WAIT, REJECT, NO_ACTION.\n"
    "- Identify fraud patterns: pump-and-dump, insider accumulation, dilution traps, "
    "paid promotions, wash trading, spoofing.\n"
    "- For penny stocks (sub-$5): always screen for dilution risk, insider selling "
    "(SEDI for TSX-V, Form 4 for US), cash runway, and promotional activity.\n"
    "- Cite sources: SEDAR+ for Canadian filings, EDGAR for US, ClinicalTrials.gov "
    "for biotech, NI 43-101 for mining technical reports.\n"
    "- Canadian context: use TFSA/RRSP contribution room awareness, "
    "Smith Maneuver when relevant, withholding tax for US stocks in TFSA.\n"
    "- Never reference Brazilian, Portuguese, or non-North American context.\n"
    "- Respond in English only.\n\n"
    "Your output format is structured markdown with clear FACT/INFERENCE separation, "
    "a CLASSIFICATION tag, and a permitted next step. When tools are available, "
    "you request data before forming conclusions."
)

# Paths
COMBINED_PATH = ROOT / "F51_Datasets" / "sft_output" / "f51_sft_combined.jsonl"
NURSE_PATH = ROOT / "data" / "nurse_dataset.jsonl"
SENSEI_PATH = ROOT / "data" / "sensei_dataset.jsonl"
GOLD_DIR = ROOT / "data" / "corpus" / "01_sft"
OUTPUT_DIR = ROOT / "F51_Datasets" / "sft_output"
OUTPUT_PATH = OUTPUT_DIR / "f51_final_sft.jsonl"


def convert_to_chat_format(entry: dict) -> dict:
    """Convert any entry format to unified chat template with messages array.

    Handles:
    - Gold format: {"question": "...", "answer": "..."}  → messages array
    - Chat format: {"messages": [{"role": "user", ...}]} → replace system prompt
    """
    # Already in chat format
    if "messages" in entry:
        new_messages = []
        has_system = False
        for msg in entry["messages"]:
            if msg.get("role") == "system":
                new_messages.append({"role": "system", "content": CEO_SYSTEM_PROMPT})
                has_system = True
            else:
                new_messages.append(msg)
        if not has_system:
            new_messages.insert(0, {"role": "system", "content": CEO_SYSTEM_PROMPT})
        entry["messages"] = new_messages
        return entry

    # Gold format: question + answer
    question = entry.get("question", "")
    answer = entry.get("answer", "")
    if question and answer:
        entry["messages"] = [
            {"role": "system", "content": CEO_SYSTEM_PROMPT},
            {"role": "user", "content": question},
            {"role": "assistant", "content": answer},
        ]
        # Clean up old fields — keep category/difficulty/id for metadata
        for key in ["question", "answer"]:
            entry.pop(key, None)
        return entry

    # Unknown format — return as-is with system prompt prepended
    return entry


def has_assistant_response(entry: dict) -> bool:
    """Check if entry has at least one assistant message with content."""
    for msg in entry.get("messages", []):
        if msg.get("role") == "assistant" and msg.get("content", "").strip():
            return True
    return False


def count_tokens_estimate(entry: dict) -> int:
    """Rough token estimate: ~4 chars per token."""
    total_chars = 0
    for msg in entry.get("messages", []):
        total_chars += len(msg.get("content", ""))
    return max(1, total_chars // 4)


def load_jsonl(path: Path):
    """Load JSONL file, returning list of entries."""
    entries = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError as e:
                print(f"  WARN: skipping bad line in {path.name}: {e}")
    return entries


def save_jsonl(entries: list, path: Path):
    """Save entries as JSONL."""
    with open(path, "w", encoding="utf-8") as f:
        for entry in entries:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def main():
    print("=" * 60)
    print("F51 Final SFT Dataset Preparation")
    print("=" * 60)

    # ── Step 1: Replace system prompts ──────────────────────────
    print("\n[1/4] Replacing system prompts with CEO Bob persona...")

    datasets = {}

    # 1a. Combined dataset (408K)
    print(f"  Loading combined: {COMBINED_PATH}")
    t0 = time.time()
    combined = load_jsonl(COMBINED_PATH)
    print(f"    Loaded {len(combined):,} entries in {time.time() - t0:.1f}s")
    t0 = time.time()
    combined = [convert_to_chat_format(e) for e in combined]
    datasets["combined"] = combined
    print(f"    Replaced prompts in {time.time() - t0:.1f}s")

    # 1b. Nurse dataset (1.8K)
    print(f"  Loading nurse: {NURSE_PATH}")
    nurse = load_jsonl(NURSE_PATH)
    print(f"    Loaded {len(nurse):,} entries")
    nurse = [convert_to_chat_format(e) for e in nurse]
    valid_nurse = [e for e in nurse if has_assistant_response(e)]
    datasets["nurse"] = valid_nurse
    print(
        f"    {len(valid_nurse):,} have assistant responses (filtered {len(nurse) - len(valid_nurse)} empty)"
    )

    # 1c. Sensei dataset (750 — no assistant responses)
    print(f"  Loading sensei: {SENSEI_PATH}")
    sensei = load_jsonl(SENSEI_PATH)
    print(f"    Loaded {len(sensei):,} entries")
    sensei_with_responses = [e for e in sensei if has_assistant_response(e)]
    sensei_without = [e for e in sensei if not has_assistant_response(e)]
    print(
        f"    {len(sensei_with_responses)} have responses, {len(sensei_without)} without (will skip for now)"
    )
    # TODO: Step 2 — generate responses for sensei_without via teacher model
    # For now, use only sensei entries that have responses
    sensei_valid = [convert_to_chat_format(e) for e in sensei_with_responses]
    datasets["sensei"] = sensei_valid
    if sensei_without:
        print(
            f"    WARN: {len(sensei_without)} sensei entries without responses saved for later generation"
        )
        # Save them separately for batch generation later
        pending_path = OUTPUT_DIR / "sensei_pending_generation.jsonl"
        save_jsonl(sensei_without, pending_path)
        print(f"    Saved pending to {pending_path}")

    # 1d. Gold SFT examples
    print(f"  Loading gold SFT from: {GOLD_DIR}")
    gold_entries = []
    for batch_file in sorted(GOLD_DIR.glob("sft_batch_*.jsonl")):
        entries = load_jsonl(batch_file)
        print(f"    {batch_file.name}: {len(entries)} entries")
        gold_entries.extend(entries)
    # Gold entries already have F51-style system prompts but ensure consistency
    gold_entries = [convert_to_chat_format(e) for e in gold_entries]
    print(f"    Total gold: {len(gold_entries)} entries")

    # ── Step 2: Weight gold examples (repeat 5x) ─────────────────
    print("\n[2/4] Weighting gold SFT examples 5x...")
    gold_weighted = gold_entries * 5
    print(f"    Gold entries: {len(gold_entries)} x5 = {len(gold_weighted)}")

    # ── Step 3: Merge all datasets ──────────────────────────────
    print("\n[3/4] Merging datasets...")
    all_entries = (
        datasets["combined"] + datasets["nurse"] + datasets["sensei"] + gold_weighted
    )
    print(f"    Combined:    {len(datasets['combined']):,}")
    print(f"    Nurse:       {len(datasets['nurse']):,}")
    print(f"    Sensei:      {len(datasets['sensei']):,}")
    print(f"    Gold (5x):   {len(gold_weighted):,}")
    print(f"    TOTAL:       {len(all_entries):,}")

    # ── Step 4: Validate and report ─────────────────────────────
    print("\n[4/4] Validating final dataset...")

    # 4a. Format check — all must have messages array with chat template
    format_errors = 0
    missing_assistant = 0
    for e in all_entries:
        msgs = e.get("messages", [])
        if not msgs:
            format_errors += 1
            continue
        roles = [m.get("role") for m in msgs]
        if "system" not in roles:
            format_errors += 1
        if "user" not in roles:
            format_errors += 1
        if "assistant" not in roles:
            missing_assistant += 1

    print(f"    Format errors: {format_errors}")
    print(f"    Missing assistant: {missing_assistant}")

    # 4b. Category distribution
    categories = Counter(e.get("category", "unknown") for e in all_entries)
    print(f"    Categories: {dict(categories.most_common(15))}")

    # 4c. Difficulty distribution
    difficulties = Counter(e.get("difficulty", "unknown") for e in all_entries)
    print(f"    Difficulty: {dict(difficulties)}")

    # 4d. Token estimate
    total_tokens = sum(count_tokens_estimate(e) for e in all_entries)
    avg_tokens = total_tokens / len(all_entries) if all_entries else 0
    print(f"    Estimated tokens: {total_tokens:,} total, {avg_tokens:.0f} avg/entry")

    # 4e. System prompt verification
    non_ceo_prompts = 0
    for e in all_entries:
        for m in e.get("messages", []):
            if m.get("role") == "system" and "Bob" not in m.get("content", ""):
                non_ceo_prompts += 1
                break
    print(f"    Non-CEO system prompts remaining: {non_ceo_prompts}")

    # 4f. Empty response check
    empty_responses = 0
    for e in all_entries:
        for m in e.get("messages", []):
            if m.get("role") == "assistant" and not m.get("content", "").strip():
                empty_responses += 1
    print(f"    Empty assistant responses: {empty_responses}")

    # ── Save ────────────────────────────────────────────────────
    print(f"\nSaving to: {OUTPUT_PATH}")
    t0 = time.time()
    save_jsonl(all_entries, OUTPUT_PATH)
    size_mb = OUTPUT_PATH.stat().st_size / (1024**2)
    print(
        f"Saved {len(all_entries):,} entries ({size_mb:.0f} MB) in {time.time() - t0:.1f}s"
    )

    # ── Save manifest ───────────────────────────────────────────
    manifest = {
        "created": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "target_model": "GLM-4.7-Flash (30B-A3B MoE)",
        "training_method": "QLoRA 4-bit SFT",
        "teacher_models": [
            "Deep (primary)",
            "GPT/Codex (secondary)",
            "Gemini (tertiary)",
        ],
        "system_prompt": CEO_SYSTEM_PROMPT,
        "entries": len(all_entries),
        "estimated_tokens": total_tokens,
        "avg_tokens_per_entry": round(avg_tokens, 1),
        "format_errors": format_errors,
        "missing_assistant": missing_assistant,
        "composition": {
            "combined_hf": len(datasets["combined"]),
            "nurse": len(datasets["nurse"]),
            "sensei": len(datasets["sensei"]),
            "gold_sft_weighted": len(gold_weighted),
            "gold_sft_unique": len(gold_entries),
        },
        "categories": dict(categories.most_common()),
        "difficulty": dict(difficulties),
        "pending_sensei_generation": len(sensei_without),
    }
    manifest_path = OUTPUT_DIR / "f51_final_manifest.json"
    with open(manifest_path, "w") as f:
        json.dump(manifest, f, indent=2)
    print(f"Manifest saved to: {manifest_path}")

    # ── Final status ───────────────────────────────────────────
    print("\n" + "=" * 60)
    if format_errors == 0 and non_ceo_prompts == 0:
        print("DATASET READY for QLoRA fine-tuning.")
    else:
        print(
            f"DATASET HAS ISSUES: {format_errors} format, {non_ceo_prompts} bad prompts"
        )
    print(f"Output: {OUTPUT_PATH}")
    print(f"Entries: {len(all_entries):,}")
    print(f"Est. tokens: {total_tokens:,}")
    print("=" * 60)


if __name__ == "__main__":
    main()
