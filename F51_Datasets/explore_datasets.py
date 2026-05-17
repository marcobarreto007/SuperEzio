"""
F51 Dataset Explorer — Understand structure of each downloaded dataset.
Samples rows, prints columns, helps design SFT conversion.
"""
import pandas as pd
import os
import json

RAW = r"C:\Users\marco\Desktop\F51_Datasets\raw_downloads"
OUT = r"C:\Users\marco\Desktop\F51_Datasets\exploration_report.json"
report = {}

def explore_parquet(path, name):
    df = pd.read_parquet(path)
    info = {
        "rows": len(df),
        "columns": list(df.columns),
        "dtypes": {c: str(df[c].dtype) for c in df.columns},
        "sample": None,
        "nulls": {c: int(df[c].isna().sum()) for c in df.columns}
    }
    # Get first row as sample (convert to string-truncated dict)
    try:
        row = df.iloc[0].to_dict()
        sample = {}
        for k, v in row.items():
            s = str(v)
            if len(s) > 500:
                s = s[:500] + "..."
            sample[k] = s
        info["sample"] = sample
    except:
        info["sample"] = "ERROR"

    print(f"\n{'='*60}")
    print(f"Dataset: {name}")
    print(f"Rows: {info['rows']:,}")
    print(f"Columns: {info['columns']}")
    print(f"Nulls: {info['nulls']}")
    print("Sample row:")
    for k, v in (info["sample"] or {}).items():
        print(f"  {k}: {v}")
    return info

if __name__ == "__main__":
    for fname in os.listdir(RAW):
        if fname.endswith(".parquet"):
            path = os.path.join(RAW, fname)
            name = fname.replace(".parquet", "")
            try:
                report[name] = explore_parquet(path, name)
            except Exception as e:
                print(f"\n  FAILED {name}: {e}")
                report[name] = {"error": str(e)}

    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    print(f"\n\nReport saved to: {OUT}")
