"""
F51 Dataset Downloader — Hugging Face + GitHub
Downloads selected fraud/finance datasets and saves to disk for conversion.
Token is scoped for read-only dataset access.
"""

import os
import json
from datasets import load_dataset, get_dataset_config_names
from huggingface_hub import login

HF_TOKEN = "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"
OUT_DIR = r"C:\Users\marco\Desktop\F51_Datasets\raw_downloads"

login(token=HF_TOKEN)
os.makedirs(OUT_DIR, exist_ok=True)

DATASETS = [
    # (hf_id, config, split, local_name)
    ("amitkedia/Financial-Fraud-Dataset", None, None, "financial_fraud_amitkedia"),
    ("CiferAI/Cifer-Fraud-Detection-Dataset-AF", None, None, "cifer_fraud_detection"),
    ("difraud/difraud", None, None, "difraud_phishing"),
    ("zefang-liu/phishing-email-dataset", None, None, "phishing_email_zefang"),
    ("ninty-seven/MultiAgentFraudBench", None, None, "multiagent_fraud_bench"),
    ("ibm-research/finqa", None, None, "finqa"),
    ("AdaptLLM/ConvFinQA", None, None, "convfinqa"),
    ("TheFinAI/fiqa-sentiment-classification", None, None, "fiqa_sentiment"),
]

RESULTS = {}


def download_safely(dataset_id, config, split, local_name):
    """Download dataset, handling splits/configs gracefully."""
    result = {"id": dataset_id, "local_name": local_name, "splits": {}, "error": None}
    try:
        # Discover configs
        try:
            configs = get_dataset_config_names(dataset_id)
        except Exception:
            configs = [None]
        if config is not None:
            configs = [config]

        for cfg in configs:
            cfg_name = cfg if cfg else "default"
            try:
                dataset = load_dataset(
                    dataset_id, cfg, split=split, trust_remote_code=True, token=HF_TOKEN
                )
            except Exception:
                # Try without config
                try:
                    dataset = load_dataset(
                        dataset_id, split=split, trust_remote_code=True, token=HF_TOKEN
                    )
                except Exception as e2:
                    result["error"] = f"config={cfg}: {e2}"
                    continue

            if isinstance(dataset, dict):
                for spl, ds in dataset.items():
                    key = f"{cfg_name}/{spl}"
                    df = ds.to_pandas()
                    path = os.path.join(OUT_DIR, f"{local_name}__{cfg_name}__{spl}.parquet")
                    df.to_parquet(path)
                    sz_mb = os.path.getsize(path) / (1024 * 1024)
                    result["splits"][key] = {
                        "rows": len(df),
                        "cols": list(df.columns),
                        "size_mb": round(sz_mb, 2),
                    }
                    print(f"  [OK] {key}: {len(df)} rows, {sz_mb:.1f} MB")
            else:
                key = cfg_name
                df = dataset.to_pandas()
                path = os.path.join(OUT_DIR, f"{local_name}__{key}.parquet")
                df.to_parquet(path)
                sz_mb = os.path.getsize(path) / (1024 * 1024)
                result["splits"][key] = {
                    "rows": len(df),
                    "cols": list(df.columns),
                    "size_mb": round(sz_mb, 2),
                }
                print(f"  [OK] {key}: {len(df)} rows, {sz_mb:.1f} MB")
    except Exception as e:
        result["error"] = str(e)
        print(f"  [FAIL] {e}")

    RESULTS[local_name] = result
    return result


if __name__ == "__main__":
    for ds_id, cfg, spl, lname in DATASETS:
        print(f"\n{'=' * 60}")
        print(f"Downloading: {ds_id} -> {lname}")
        print(f"{'=' * 60}")
        download_safely(ds_id, cfg, spl, lname)

    # Summary
    print(f"\n{'=' * 60}")
    print("DOWNLOAD SUMMARY")
    print(f"{'=' * 60}")
    total_rows = 0
    total_mb = 0
    for name, r in RESULTS.items():
        if r["error"]:
            print(f"  {name}: FAILED — {r['error']}")
        else:
            rows = sum(s["rows"] for s in r["splits"].values())
            mb = sum(s["size_mb"] for s in r["splits"].values())
            total_rows += rows
            total_mb += mb
            print(f"  {name}: {len(r['splits'])} split(s), {rows} rows, {mb:.1f} MB")
    print(f"\n  TOTAL: {total_rows} rows, {total_mb:.1f} MB")

    # Save manifest
    manifest_path = os.path.join(OUT_DIR, "download_manifest.json")
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(RESULTS, f, indent=2, ensure_ascii=False)
    print(f"\nManifest saved to: {manifest_path}")
