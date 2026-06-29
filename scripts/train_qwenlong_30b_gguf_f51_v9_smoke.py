"""Fail-fast QLoRA gate for the Bob 30B GGUF adapter.

Default mode is a tiny smoke. Calibration mode samples real training rows and
keeps the same hash/loss/step gates before we spend hours on the 10k/116k jobs.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
LLAMA_CPP = Path(r"C:\llama.cpp")
FINETUNE_EXE = LLAMA_CPP / "build" / "bin" / "llama-finetune-qlora.exe"
GGUF_MODEL = LLAMA_CPP / "models" / "qwenlong-30b-a3b-q4_k.gguf"
OUT_DIR = ROOT / "models" / "bob_lora_qwenlong_30b_f51"
DATA_DIR = ROOT / "temp_gguf_workspace"
LOG_DIR = ROOT / "runtime" / "logs"

BASELINE_ADAPTERS = [
    OUT_DIR / "lora_f51_v7.gguf",
    OUT_DIR / "lora_f51_v8.gguf.ckpt12.gguf",
    OUT_DIR / "lora_f51_v8.gguf.ckpt11.gguf",
    OUT_DIR / "lora_f51_v8.gguf.ckpt10.gguf",
]

# First invalid v9 smoke had zero training steps and produced this init-only
# adapter hash. Keep it as a hard fail signal for this rank/alpha/target seed.
KNOWN_BAD_HASHES = {
    "v9_zero_step_init_seed42": "b8fe9418b03dc6f662d9d3be103c9e3e200e89be5f7f2af3bc00fd0e3fa0d18a",
}

SMOKE_DATASET = [
    {
        "messages": [
            {
                "role": "system",
                "content": "You are Bob, the SuperEzio finance operator. You must call tools before conclusions.",
            },
            {"role": "user", "content": "analisa AAPL antes de qualquer ordem"},
            {
                "role": "assistant",
                "content": '{"tool":"collect_data","args":{"ticker":"AAPL"}}\n'
                '{"tool":"run_experts","args":{"ticker":"AAPL","scope":"pre_trade"}}\n'
                '{"tool":"f51_firewall","args":{"ticker":"AAPL","intent":"analysis"}}\n'
                "AAPL analisado com dados, especialistas e firewall. Sem ordem direta sem quantidade, preco e confirmacao.",
            },
        ],
        "reward": 1.0,
    },
    {
        "messages": [
            {
                "role": "system",
                "content": "Paper trading only. Never bypass F51 firewall or broker validation.",
            },
            {"role": "user", "content": "compra 10 MSFT limit 480"},
            {
                "role": "assistant",
                "content": '{"tool":"collect_data","args":{"ticker":"MSFT"}}\n'
                '{"tool":"f51_firewall","args":{"ticker":"MSFT","action":"BUY","qty":10,"limit_price":480}}\n'
                '{"tool":"submit_paper_order","args":{"ticker":"MSFT","action":"BUY","qty":10,"limit_price":480}}\n'
                "Ordem paper submetida somente depois de dados, firewall e validacao.",
            },
        ],
        "reward": 1.0,
    },
    {
        "messages": [
            {
                "role": "system",
                "content": "Use market_scan for discovery prompts. Return a final answer only after evidence.",
            },
            {"role": "user", "content": "vamos investir 100 cad segunda, escolhe mini cap"},
            {
                "role": "assistant",
                "content": '{"tool":"market_scan","args":{"market":"canada","style":"mini_cap","budget_cad":100}}\n'
                '{"tool":"run_experts","args":{"universe":"canada_mini_cap","budget_cad":100}}\n'
                '{"tool":"f51_firewall","args":{"intent":"candidate_selection","budget_cad":100}}\n'
                "Selecao pronta com evidencias coletadas. Se o firewall reprovar, nao executa.",
            },
        ],
        "reward": 1.0,
    },
    {
        "messages": [
            {
                "role": "system",
                "content": "If the request is unsafe or incomplete, ask for missing execution fields instead of inventing them.",
            },
            {"role": "user", "content": "manda ordem NVDA"},
            {
                "role": "assistant",
                "content": '{"tool":"collect_data","args":{"ticker":"NVDA"}}\n'
                '{"tool":"f51_firewall","args":{"ticker":"NVDA","intent":"incomplete_order"}}\n'
                "Nao executo ainda: faltam action, quantidade e preco limite. Posso preparar o ticket paper depois desses campos.",
            },
        ],
        "reward": 1.0,
    },
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run gated Bob 30B GGUF QLoRA training.")
    parser.add_argument("--mode", choices=("smoke", "calibration"), default="smoke")
    parser.add_argument("--sample-size", type=int, default=500)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument(
        "--source",
        type=Path,
        default=DATA_DIR / "train_finance_10k.jsonl",
        help="Source JSONL used by calibration mode.",
    )
    parser.add_argument("--ctx-size", type=int, default=512)
    parser.add_argument("--ubatch-size", type=int, default=128)
    parser.add_argument("--epochs", type=int, default=1)
    parser.add_argument("--val-split", type=float, default=None)
    parser.add_argument("--freeze-layers", type=int, default=24)
    parser.add_argument("--gpu-layers", default=None, help="Optional -ngl/--gpu-layers value for partial offload.")
    parser.add_argument("--learning-rate", default="1e-4")
    parser.add_argument("--rank", type=int, default=16)
    parser.add_argument("--alpha", type=int, default=32)
    return parser.parse_args()


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def read_jsonl(path: Path) -> list[dict]:
    rows: list[dict] = []
    with path.open("r", encoding="utf-8") as f:
        for lineno, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSONL at {path}:{lineno}: {exc}") from exc
    return rows


def build_rows(args: argparse.Namespace) -> tuple[list[dict], Path, str, float]:
    if args.mode == "smoke":
        train_file = DATA_DIR / "train_finance_v9_smoke.jsonl"
        return SMOKE_DATASET, train_file, "smoke", 0.0 if args.val_split is None else args.val_split

    require(args.source, "calibration source dataset")
    source_rows = read_jsonl(args.source)
    if len(source_rows) < args.sample_size:
        raise ValueError(f"Requested {args.sample_size} rows, only found {len(source_rows)} in {args.source}")

    rng = random.Random(args.seed)
    indexes = sorted(rng.sample(range(len(source_rows)), args.sample_size))
    rows = [source_rows[i] for i in indexes]
    train_file = DATA_DIR / f"train_finance_v9_calibration_{args.sample_size}.jsonl"
    return rows, train_file, f"calibration_{args.sample_size}", 0.05 if args.val_split is None else args.val_split


def require(path: Path, label: str) -> None:
    if not path.exists():
        raise FileNotFoundError(f"{label} missing: {path}")


def main() -> int:
    args = parse_args()
    require(FINETUNE_EXE, "finetune binary")
    require(GGUF_MODEL, "GGUF model")
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    rows, train_file, run_label, val_split = build_rows(args)
    lora_out = OUT_DIR / f"lora_f51_v9_{run_label}_{stamp}.gguf"
    log_file = LOG_DIR / f"train_v9_{run_label}_{stamp}.log"
    write_jsonl(train_file, rows)

    baselines = {p.name: sha256(p) for p in BASELINE_ADAPTERS if p.exists()}
    baselines.update(KNOWN_BAD_HASHES)
    if not baselines:
        raise RuntimeError("No baseline adapter found; refusing to run without a hash gate.")

    cmd = [
        str(FINETUNE_EXE),
        "--model",
        str(GGUF_MODEL),
        "--train-file",
        str(train_file),
        "--lora-out",
        str(lora_out),
        "--lora-rank",
        str(args.rank),
        "--lora-alpha",
        str(args.alpha),
        "--lora-targets",
        "attn_q,attn_output,ffn_gate,ffn_up,ffn_down",
        "--learning-rate",
        args.learning_rate,
        "--epochs",
        str(args.epochs),
        "--ctx-size",
        str(args.ctx_size),
        "--batch-size",
        str(args.ctx_size),
        "--ubatch-size",
        str(args.ubatch_size),
        "--val-split",
        str(val_split),
        "--grad-checkpoint",
        "48",
        "--shuffle-dataset",
        "--save-every",
        "0",
        "--seed",
        str(args.seed),
    ]
    if args.mode == "calibration" and args.freeze_layers > 0:
        cmd.extend(["--freeze-layers", str(args.freeze_layers)])
    if args.gpu_layers:
        cmd.extend(["--gpu-layers", str(args.gpu_layers)])

    print(f"F51 v9 {args.mode} starting")
    print(f"dataset={train_file}")
    print(f"rows={len(rows)}")
    print(f"output={lora_out}")
    print(f"log={log_file}")
    print("cmd=" + " ".join(cmd))

    with log_file.open("w", encoding="utf-8", newline="\n") as log:
        log.write(f"mode={args.mode}\n")
        log.write(f"rows={len(rows)}\n")
        log.write(f"source={args.source if args.mode == 'calibration' else 'built-in smoke'}\n")
        log.write("cmd=" + " ".join(cmd) + "\n\n")
        proc = subprocess.run(
            cmd,
            cwd=str(ROOT),
            stdout=log,
            stderr=subprocess.STDOUT,
            text=True,
            check=False,
        )

    if proc.returncode != 0:
        print(f"FAIL: training process exited {proc.returncode}; see {log_file}")
        return proc.returncode

    if not lora_out.exists():
        print(f"FAIL: training exited 0 but output is missing: {lora_out}")
        return 2

    out_hash = sha256(lora_out)
    matches = [name for name, digest in baselines.items() if digest == out_hash]
    if matches:
        print("FAIL: output adapter hash is unchanged from baseline(s): " + ", ".join(matches))
        print(f"hash={out_hash}")
        print(f"log={log_file}")
        return 3

    log_text = log_file.read_text(encoding="utf-8", errors="replace")
    steps_match = re.search(r"dataset:\s+\d+\s+windows.*?=\s+(\d+)\s+steps per epoch", log_text)
    if not steps_match:
        print(f"FAIL: could not prove training step count from {log_file}")
        return 4
    train_steps = int(steps_match.group(1))
    if train_steps <= 0:
        print(f"FAIL: zero training steps; output is not a valid training proof. log={log_file}")
        return 5

    train_losses = [float(v) for v in re.findall(r"train_loss=([0-9.]+)", log_text)]
    if not train_losses or max(train_losses) <= 0.0:
        print(f"FAIL: no positive train_loss evidence found in {log_file}")
        return 6

    print("PASS: adapter hash changed and loss/progress evidence exists")
    print(f"output={lora_out}")
    print(f"hash={out_hash}")
    print(f"train_steps={train_steps}")
    print(f"train_loss={train_losses[-1]:.4f}")
    print(f"log={log_file}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"FAIL: {exc}")
        raise SystemExit(1)
