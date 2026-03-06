"""
Download and explore Phase 1 datasets: FinQA, TAT-QA-CoT, FinGPT Forecaster.
"""
import json
from pathlib import Path
from datasets import load_dataset

OUT = Path(r"C:\Users\marco\Desktop\SuperEzio\.f51\tmp\phase1_raw")
OUT.mkdir(parents=True, exist_ok=True)

# ----- 1. FinQA -----
print("=" * 60)
print("[1/3] FinQA")
print("=" * 60)
try:
    ds = load_dataset("dreamerdeo/finqa", split="train")
    print(f"  Columns: {ds.column_names}")
    print(f"  Rows: {len(ds)}")
    for i in range(3):
        print(f"  --- Sample {i} ---")
        for k, v in ds[i].items():
            print(f"    {k}: {str(v)[:200]}")
    ds.to_json(str(OUT / "finqa_train.jsonl"))
    print(f"  Saved: finqa_train.jsonl ({len(ds)} rows)")
except Exception as e:
    print(f"  [ERROR] {e}")

# ----- 2. TAT-QA-Arithmetic-CoT -----
print("\n" + "=" * 60)
print("[2/3] TAT-QA-Arithmetic-CoT")
print("=" * 60)
try:
    ds = load_dataset("cerebras/TAT-QA-Arithmetic-CoT", split="train")
    print(f"  Columns: {ds.column_names}")
    print(f"  Rows: {len(ds)}")
    for i in range(3):
        print(f"  --- Sample {i} ---")
        for k, v in ds[i].items():
            print(f"    {k}: {str(v)[:200]}")
    ds.to_json(str(OUT / "tatqa_cot_train.jsonl"))
    print(f"  Saved: tatqa_cot_train.jsonl ({len(ds)} rows)")
except Exception as e:
    print(f"  [ERROR] {e}")

# ----- 3. FinGPT Forecaster -----
print("\n" + "=" * 60)
print("[3/3] FinGPT Forecaster DOW30")
print("=" * 60)
try:
    ds = load_dataset("FinGPT/fingpt-forecaster-dow30-202305-202405", split="train")
    print(f"  Columns: {ds.column_names}")
    print(f"  Rows: {len(ds)}")
    for i in range(3):
        print(f"  --- Sample {i} ---")
        for k, v in ds[i].items():
            print(f"    {k}: {str(v)[:300]}")
    ds.to_json(str(OUT / "fingpt_forecaster_train.jsonl"))
    print(f"  Saved: fingpt_forecaster_train.jsonl ({len(ds)} rows)")
except Exception as e:
    print(f"  [ERROR] {e}")

print("\nDone!")
