"""Fail-fast QLoRA smoke for the Bob 30B GGUF adapter.

This is intentionally small. Its job is not to produce the production adapter;
its job is to prove that llama-finetune-qlora is actually changing LoRA weights
before we spend hours on the 10k/116k datasets.
"""

from __future__ import annotations

import hashlib
import json
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


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def write_jsonl(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as f:
        for row in SMOKE_DATASET:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def require(path: Path, label: str) -> None:
    if not path.exists():
        raise FileNotFoundError(f"{label} missing: {path}")


def main() -> int:
    require(FINETUNE_EXE, "finetune binary")
    require(GGUF_MODEL, "GGUF model")
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    train_file = DATA_DIR / "train_finance_v9_smoke.jsonl"
    lora_out = OUT_DIR / f"lora_f51_v9_smoke_{stamp}.gguf"
    log_file = LOG_DIR / f"train_v9_smoke_{stamp}.log"
    write_jsonl(train_file)

    baselines = {p.name: sha256(p) for p in BASELINE_ADAPTERS if p.exists()}
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
        "16",
        "--lora-alpha",
        "32",
        "--lora-targets",
        "attn_q,attn_output,ffn_gate,ffn_up,ffn_down",
        "--learning-rate",
        "1e-4",
        "--epochs",
        "1",
        "--ctx-size",
        "512",
        "--batch-size",
        "512",
        "--ubatch-size",
        "128",
        "--val-split",
        "0.0",
        "--grad-checkpoint",
        "48",
        "--shuffle-dataset",
        "--save-every",
        "0",
        "--seed",
        "42",
    ]

    print("F51 v9 smoke starting")
    print(f"dataset={train_file}")
    print(f"output={lora_out}")
    print(f"log={log_file}")
    print("cmd=" + " ".join(cmd))

    with log_file.open("w", encoding="utf-8", newline="\n") as log:
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
