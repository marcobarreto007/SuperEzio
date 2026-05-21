"""Build a reproducible SuperEzio intent dataset from real HF datasets.

Sources:
  - learn-abc/banking14-intents-en: real banking intent hard negatives
  - klaylouis1932/OpenFinData-Intent-Understanding-Intruct: finance intent labels
  - vibrantlabsai/fiqa: finance QA/RAG questions
  - data/intent_golden.jsonl: product-critical SuperEzio golden cases
"""

from __future__ import annotations

import argparse
import json
import random
import re
import sys
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from core.pipeline.intents import parse_user_intent, validate_intent_candidate  # noqa: E402


HF_ROWS_URL = "https://datasets-server.huggingface.co/rows"
HF_SIZE_URL = "https://datasets-server.huggingface.co/size"

DEFAULT_GOLDEN = PROJECT_ROOT / "data" / "intent_golden.jsonl"
DEFAULT_TRAIN = PROJECT_ROOT / "data" / "intent_dataset.jsonl"
DEFAULT_EVAL = PROJECT_ROOT / "data" / "intent_eval.jsonl"
DEFAULT_META = PROJECT_ROOT / "data" / "intent_dataset_sources.json"


def hf_get(endpoint: str, params: dict[str, str | int]) -> dict[str, Any]:
    query = urllib.parse.urlencode(params)
    with urllib.request.urlopen(f"{endpoint}?{query}", timeout=45) as response:
        return json.loads(response.read().decode("utf-8"))


def fetch_rows(
    dataset: str,
    config: str,
    split: str,
    limit: int,
    page_size: int = 100,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    offset = 0
    while len(rows) < limit:
        length = min(page_size, limit - len(rows))
        payload = hf_get(
            HF_ROWS_URL,
            {
                "dataset": dataset,
                "config": config,
                "split": split,
                "offset": offset,
                "length": length,
            },
        )
        batch = payload.get("rows") or []
        if not batch:
            break
        for item in batch:
            row = item.get("row", item)
            if isinstance(row, dict):
                rows.append(row)
        offset += len(batch)
    return rows


def source_size(dataset: str) -> dict[str, Any]:
    try:
        return hf_get(HF_SIZE_URL, {"dataset": dataset})
    except Exception as exc:  # noqa: BLE001 - CLI report should keep running
        return {"dataset": dataset, "error": str(exc)}


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=True, sort_keys=True) + "\n")


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            rows.append(json.loads(stripped))
    return rows


def compact_text(value: Any, limit: int = 260) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "..."


def extract_openfin_question(row: dict[str, Any]) -> str:
    instruction = str(row.get("instruction") or "")
    match = re.search(r"问句[:：]\s*(.+?)\n", instruction)
    if match:
        return compact_text(match.group(1), limit=240)
    match = re.search(r"Question[:：]\s*(.+?)\n", instruction, flags=re.I)
    if match:
        return compact_text(match.group(1), limit=240)
    return compact_text(row.get("input") or instruction, limit=240)


def plan_to_example(
    message: str,
    *,
    source: str,
    source_dataset: str,
    source_split: str,
    source_label: str,
    source_row_idx: int,
) -> dict[str, Any] | None:
    if not message:
        return None
    parsed = parse_user_intent(message)
    return {
        "message": message,
        "route": parsed.route,
        "intent": parsed.intent,
        "action": parsed.action,
        "ticker": parsed.ticker,
        "filters": parsed.filters or {},
        "required_slots": list(parsed.required_slots),
        "confidence": round(parsed.confidence, 3),
        "source": source,
        "source_dataset": source_dataset,
        "source_split": source_split,
        "source_label": source_label,
        "source_row_idx": source_row_idx,
        "reasons": list(parsed.reasons),
    }


def banking_examples(limit: int) -> list[dict[str, Any]]:
    rows = fetch_rows("learn-abc/banking14-intents-en", "default", "train", limit)
    examples: list[dict[str, Any]] = []
    for idx, row in enumerate(rows):
        message = compact_text(row.get("text"))
        example = {
            "message": message,
            "route": "general",
            "intent": "general_question",
            "action": "answer",
            "ticker": "",
            "filters": {},
            "required_slots": [],
            "confidence": 0.93,
            "source": "hf_hard_negative",
            "source_dataset": "learn-abc/banking14-intents-en",
            "source_split": "default/train",
            "source_label": str(row.get("label", "")),
            "source_row_idx": idx,
            "reasons": ["real_banking_intent_not_trading_scan"],
        }
        validated = validate_intent_candidate(message, example)
        if validated:
            examples.append(example)
    return examples


def openfin_examples(limit: int) -> list[dict[str, Any]]:
    rows = fetch_rows(
        "klaylouis1932/OpenFinData-Intent-Understanding-Intruct",
        "default",
        "train",
        limit,
    )
    examples: list[dict[str, Any]] = []
    for idx, row in enumerate(rows):
        question = extract_openfin_question(row)
        example = plan_to_example(
            question,
            source="hf_finance_intent",
            source_dataset="klaylouis1932/OpenFinData-Intent-Understanding-Intruct",
            source_split="default/train",
            source_label=str(row.get("output", "")),
            source_row_idx=idx,
        )
        if example:
            examples.append(example)
    return examples


def fiqa_examples(limit: int) -> list[dict[str, Any]]:
    rows = fetch_rows("vibrantlabsai/fiqa", "main", "train", limit)
    examples: list[dict[str, Any]] = []
    for idx, row in enumerate(rows):
        question = compact_text(row.get("question"), limit=240)
        example = plan_to_example(
            question,
            source="hf_finance_qa",
            source_dataset="vibrantlabsai/fiqa",
            source_split="main/train",
            source_label="financial_qa",
            source_row_idx=idx,
        )
        if example:
            examples.append(example)
    return examples


def golden_examples(path: Path) -> list[dict[str, Any]]:
    rows = read_jsonl(path)
    examples: list[dict[str, Any]] = []
    for idx, row in enumerate(rows):
        message = str(row.get("message") or row.get("utterance") or "").strip()
        if not message:
            continue
        candidate = dict(row)
        candidate.setdefault("source", "local_golden")
        candidate.setdefault("source_dataset", str(path.relative_to(PROJECT_ROOT)))
        candidate.setdefault("source_split", "golden")
        candidate.setdefault("source_label", candidate.get("intent", ""))
        candidate.setdefault("source_row_idx", idx)
        candidate.setdefault("reasons", ["product_golden_case"])
        if validate_intent_candidate(message, candidate):
            examples.append(candidate)
    return examples


def dedupe(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    unique: list[dict[str, Any]] = []
    for row in rows:
        key = re.sub(r"\s+", " ", row["message"].strip().lower())
        if key in seen:
            continue
        seen.add(key)
        item = dict(row)
        item["id"] = f"intent_{len(unique) + 1:05d}"
        unique.append(item)
    return unique


def split_rows(rows: list[dict[str, Any]], eval_ratio: float) -> tuple[list[dict], list[dict]]:
    rng = random.Random(51)
    shuffled = list(rows)
    rng.shuffle(shuffled)
    eval_size = max(1, int(len(shuffled) * eval_ratio))
    return shuffled[eval_size:], shuffled[:eval_size]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--max-banking", type=int, default=420)
    parser.add_argument("--max-openfin", type=int, default=300)
    parser.add_argument("--max-fiqa", type=int, default=220)
    parser.add_argument("--eval-ratio", type=float, default=0.2)
    parser.add_argument("--golden", type=Path, default=DEFAULT_GOLDEN)
    parser.add_argument("--train-output", type=Path, default=DEFAULT_TRAIN)
    parser.add_argument("--eval-output", type=Path, default=DEFAULT_EVAL)
    parser.add_argument("--meta-output", type=Path, default=DEFAULT_META)
    args = parser.parse_args()

    rows: list[dict[str, Any]] = []
    rows.extend(golden_examples(args.golden))
    rows.extend(banking_examples(args.max_banking))
    rows.extend(openfin_examples(args.max_openfin))
    rows.extend(fiqa_examples(args.max_fiqa))
    rows = dedupe(rows)
    train_rows, eval_rows = split_rows(rows, args.eval_ratio)

    write_jsonl(args.train_output, train_rows)
    write_jsonl(args.eval_output, eval_rows)

    metadata = {
        "generated_by": "scripts/build_hf_intent_dataset.py",
        "total_examples": len(rows),
        "train_examples": len(train_rows),
        "eval_examples": len(eval_rows),
        "sources": {
            "learn-abc/banking14-intents-en": source_size("learn-abc/banking14-intents-en"),
            "klaylouis1932/OpenFinData-Intent-Understanding-Intruct": source_size(
                "klaylouis1932/OpenFinData-Intent-Understanding-Intruct"
            ),
            "vibrantlabsai/fiqa": source_size("vibrantlabsai/fiqa"),
            "local_golden": str(args.golden),
        },
    }
    args.meta_output.parent.mkdir(parents=True, exist_ok=True)
    args.meta_output.write_text(
        json.dumps(metadata, ensure_ascii=True, indent=2, sort_keys=True),
        encoding="utf-8",
    )

    print(f"intent examples: {len(rows)}")
    print(f"train: {args.train_output} ({len(train_rows)})")
    print(f"eval: {args.eval_output} ({len(eval_rows)})")
    print(f"metadata: {args.meta_output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
