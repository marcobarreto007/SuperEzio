"""
LoRA / QLoRA SFT fine-tuning for Qwen3.6-35B-A3B (qwen35moe).

Target: Qwen3.6-35B-A3B MoE (35B total, ~3B active, 256 experts, 8 active)
Architecture: qwen3_5_moe — hybrid attention + GatedDeltaNet SSM + MoE FFN

Default: Full LoRA (bf16, no quantization) — requires 96GB+ VRAM (RTX PRO 6000)
Optional: --use-4bit enables QLoRA (NF4 4-bit) — fits 40-48GB GPUs

LoRA targets:
    - Attention (full_attention layers): q_proj, k_proj, v_proj, o_proj
    - Shared expert MLP: gate_proj, up_proj, down_proj
    - SSM (linear_attention layers): out_proj
    - Expert fused params (gate_up_proj, down_proj) are NOT targeted
      (fused across all experts, not individual Linear modules)

VRAM estimate:
    Full LoRA (bf16): 70GB model + 15GB overhead = ~85GB (RTX PRO 6000 96GB)
    QLoRA (4-bit): 20GB model + 10GB overhead = ~30GB (A100 40GB+)

Dataset: F51_Datasets/sft_output/f51_final_sft.jsonl — 410K entries

Setup (vast.ai cloud GPU):
    pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu124
    pip install transformers>=4.51.0 accelerate>=1.0.0 peft>=0.14.0
    pip install datasets>=3.0.0
    pip install bitsandbytes>=0.45.0  # only if using --use-4bit

Usage:
    # Full LoRA on 96GB GPU (recommended)
    python scripts/finetune_qwen36_sft.py \\
        --model Qwen/Qwen3.6-35B-A3B \\
        --dataset F51_Datasets/sft_output/f51_final_sft.jsonl \\
        --output-dir output/qwen36-sft \\
        --epochs 1 --batch-size 1 --gradient-accumulation 16

    # QLoRA on smaller GPU
    python scripts/finetune_qwen36_sft.py \\
        --model Qwen/Qwen3.6-35B-A3B --use-4bit \\
        --dataset F51_Datasets/sft_output/f51_final_sft.jsonl \\
        --output-dir output/qwen36-sft \\
        --epochs 1 --batch-size 1 --gradient-accumulation 16

    # Quick test with small subset
    python scripts/finetune_qwen36_sft.py \\
        --model Qwen/Qwen3.6-35B-A3B \\
        --dataset F51_Datasets/sft_output/f51_final_sft.jsonl \\
        --output-dir output/qwen36-sft-test \\
        --max-samples 500 --epochs 1 --batch-size 1

    # Multi-GPU (accelerate)
    accelerate launch --num_processes 2 scripts/finetune_qwen36_sft.py ...

    # Resume from checkpoint
    python scripts/finetune_qwen36_sft.py --resume output/qwen36-sft/checkpoint-1000
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import random
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import torch
import torch.nn as nn
from torch.utils.data import IterableDataset

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("finetune_qwen36")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DATASET = PROJECT_ROOT / "F51_Datasets" / "sft_output" / "f51_final_sft.jsonl"
DEFAULT_OUTPUT = PROJECT_ROOT / "output" / "qwen36-sft"
DEFAULT_MODEL = os.getenv("SUPEREZIO_TRAIN_MODEL", "Qwen/Qwen3.6-35B-A3B")


# ── LoRA target selection ──────────────────────────────────────────────────

QWEN35MOE_LORA_TARGETS = [
    # Attention (full_attention layers)
    "q_proj",
    "k_proj",
    "v_proj",
    "o_proj",
    # Shared expert MLP (standard MLP, individual Linears)
    "gate_proj",
    "up_proj",
    "down_proj",
    # SSM output projection (linear_attention layers)
    "out_proj",
]


def qwen35moe_lora_targets(model: nn.Module) -> list[str]:
    """Find available LoRA target modules in the Qwen3.5 MoE model.

    Checks which of the standard targets are present as nn.Linear modules.
    Expert fused params (gate_up_proj, down_proj as nn.Parameter)
    are NOT targeted — they're not individual Linear modules.
    """
    linear_names: set[str] = set()
    for name, module in model.named_modules():
        if isinstance(module, nn.Linear):
            linear_names.add(name.split(".")[-1])

    targets = [t for t in QWEN35MOE_LORA_TARGETS if t in linear_names]

    if not targets:
        targets = sorted(linear_names)
        logger.warning("No standard targets found, using all Linear modules: %s", targets)
    else:
        missing = [t for t in QWEN35MOE_LORA_TARGETS if t not in linear_names]
        if missing:
            logger.info("LoRA targets not found in model: %s (skipped)", missing)

    logger.info("LoRA targets: %s", targets)
    return targets


def count_trainable_params(model: nn.Module) -> tuple[int, int, float]:
    total = sum(p.numel() for p in model.parameters())
    trainable = sum(p.numel() for p in model.parameters() if p.requires_grad)
    return trainable, total, (trainable / total * 100 if total else 0)


# ── Dataset ────────────────────────────────────────────────────────────────


class StreamingJSONLDataset(IterableDataset):
    """Stream JSONL file line-by-line to avoid loading 1GB into RAM."""

    def __init__(
        self,
        path: Path,
        tokenizer: Any,
        max_length: int = 4096,
        max_samples: int | None = None,
        shuffle_buffer_size: int = 10000,
        seed: int = 42,
    ):
        self.path = Path(path)
        self.tokenizer = tokenizer
        self.max_length = max_length
        self.max_samples = max_samples
        self.shuffle_buffer_size = shuffle_buffer_size
        self.seed = seed

    def __iter__(self):
        return self._stream()

    def _stream(self):
        rng = random.Random(self.seed)
        buffer: list[dict[str, Any]] = []
        count = 0

        with open(self.path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue

                messages = row.get("messages")
                if not messages:
                    continue

                try:
                    tokenized = self.tokenizer.apply_chat_template(
                        messages,
                        tokenize=True,
                        add_generation_prompt=False,
                    )
                    # transformers 5.x: apply_chat_template returns
                    # BatchEncoding, extract input_ids list
                    if hasattr(tokenized, "input_ids"):
                        tokenized = tokenized["input_ids"]
                    if isinstance(tokenized, str):
                        tokenized = self.tokenizer.encode(
                            tokenized,
                            max_length=self.max_length,
                            truncation=True,
                        )
                    if len(tokenized) > self.max_length:
                        tokenized = tokenized[: self.max_length]
                except Exception:
                    continue

                buffer.append(
                    {
                        "input_ids": tokenized,
                        "labels": tokenized.copy(),
                    }
                )

                if len(buffer) >= self.shuffle_buffer_size:
                    rng.shuffle(buffer)
                    for item in buffer:
                        yield item
                        count += 1
                        if self.max_samples and count >= self.max_samples:
                            return
                    buffer.clear()

        if buffer:
            rng.shuffle(buffer)
            for item in buffer:
                yield item
                count += 1
                if self.max_samples and count >= self.max_samples:
                    return


def collate_pad(batch: list[dict]) -> dict[str, torch.Tensor]:
    max_len = max(len(b["input_ids"]) for b in batch)
    input_ids = torch.full((len(batch), max_len), 0, dtype=torch.long)
    labels = torch.full((len(batch), max_len), -100, dtype=torch.long)

    for i, b in enumerate(batch):
        seq_len = len(b["input_ids"])
        input_ids[i, :seq_len] = torch.tensor(b["input_ids"], dtype=torch.long)
        labels[i, :seq_len] = torch.tensor(b["labels"], dtype=torch.long)

    attention_mask = (input_ids != 0).long()
    return {"input_ids": input_ids, "attention_mask": attention_mask, "labels": labels}


# ── Training Args ──────────────────────────────────────────────────────────


@dataclass
class TrainingArgs:
    model_name: str = DEFAULT_MODEL
    dataset_path: str = ""
    output_dir: str = ""
    epochs: int = 1
    batch_size: int = 1
    gradient_accumulation: int = 16
    learning_rate: float = 2e-4
    lora_r: int = 64
    lora_alpha: int = 128
    lora_dropout: float = 0.05
    max_seq_length: int = 4096
    use_4bit: bool = False  # False = full LoRA (bf16), True = QLoRA (NF4)
    use_gradient_checkpointing: bool = True
    max_samples: int | None = None
    save_steps: int = 500
    eval_steps: int = 1000
    warmup_ratio: float = 0.03
    weight_decay: float = 0.01
    resume: str = ""
    seed: int = 42


def parse_args() -> TrainingArgs:
    p = argparse.ArgumentParser(description="QLoRA SFT for Qwen3.6-35B-A3B")
    p.add_argument("--model", default=DEFAULT_MODEL)
    p.add_argument("--dataset", default=str(DEFAULT_DATASET))
    p.add_argument("--output-dir", default=str(DEFAULT_OUTPUT))
    p.add_argument("--epochs", type=int, default=1)
    p.add_argument("--batch-size", type=int, default=1)
    p.add_argument("--gradient-accumulation", type=int, default=16)
    p.add_argument("--learning-rate", type=float, default=2e-4)
    p.add_argument("--lora-r", type=int, default=64)
    p.add_argument("--lora-alpha", type=int, default=128)
    p.add_argument("--lora-dropout", type=float, default=0.05)
    p.add_argument(
        "--use-4bit",
        action="store_true",
        help="Use QLoRA 4-bit NF4 quantization (default: full LoRA bf16)",
    )
    p.add_argument(
        "--no-grad-checkpoint",
        action="store_true",
        help="Disable gradient checkpointing (uses more VRAM)",
    )
    p.add_argument("--max-seq-length", type=int, default=4096)
    p.add_argument("--max-samples", type=int, default=None)
    p.add_argument("--save-steps", type=int, default=500)
    p.add_argument("--eval-steps", type=int, default=1000)
    p.add_argument("--warmup-ratio", type=float, default=0.03)
    p.add_argument("--weight-decay", type=float, default=0.01)
    p.add_argument("--resume", default="")
    p.add_argument("--seed", type=int, default=42)
    ns = p.parse_args()
    return TrainingArgs(
        model_name=ns.model,
        dataset_path=ns.dataset,
        output_dir=ns.output,
        epochs=ns.epochs,
        batch_size=ns.batch_size,
        gradient_accumulation=ns.gradient_accumulation,
        learning_rate=ns.learning_rate,
        lora_r=ns.lora_r,
        lora_alpha=ns.lora_alpha,
        lora_dropout=ns.lora_dropout,
        use_4bit=ns.use_4bit,
        use_gradient_checkpointing=not ns.no_grad_checkpoint,
        max_seq_length=ns.max_seq_length,
        max_samples=ns.max_samples,
        save_steps=ns.save_steps,
        eval_steps=ns.eval_steps,
        warmup_ratio=ns.warmup_ratio,
        weight_decay=ns.weight_decay,
        resume=ns.resume,
        seed=ns.seed,
    )


# ── Training Loop ──────────────────────────────────────────────────────────


def train(args: TrainingArgs) -> None:
    from accelerate import Accelerator
    from peft import LoraConfig, TaskType, get_peft_model
    from transformers import (
        AutoModelForCausalLM,
        AutoTokenizer,
        BitsAndBytesConfig,
        get_cosine_schedule_with_warmup,
    )

    accelerator = Accelerator(
        gradient_accumulation_steps=args.gradient_accumulation,
        mixed_precision="bf16",
    )

    if accelerator.is_main_process:
        logger.info("=" * 60)
        logger.info(
            "%s — Qwen3.6-35B-A3B MoE",
            "Full LoRA (bf16)" if not args.use_4bit else "QLoRA (4-bit NF4)",
        )
        logger.info("Model: %s", args.model_name)
        logger.info("Dataset: %s", args.dataset_path)
        logger.info("Output: %s", args.output_dir)
        logger.info(
            "LoRA: r=%d alpha=%d dropout=%.2f", args.lora_r, args.lora_alpha, args.lora_dropout
        )
        logger.info(
            "Training: epochs=%d batch=%d grad_accum=%d effective_batch=%d",
            args.epochs,
            args.batch_size,
            args.gradient_accumulation,
            args.batch_size * args.gradient_accumulation,
        )
        logger.info(
            "4-bit: %s | Grad checkpoint: %s", args.use_4bit, args.use_gradient_checkpointing
        )
        logger.info("=" * 60)

    # ── Load model ────────────────────────────────────────────────────────
    model_kwargs: dict = dict(
        device_map="auto",
        torch_dtype=torch.bfloat16,
        attn_implementation="flash_attention_2",
    )

    if args.use_4bit:
        logger.info("Loading base model in 4-bit NF4...")
        model_kwargs["quantization_config"] = BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_compute_dtype=torch.bfloat16,
            bnb_4bit_use_double_quant=True,
            bnb_4bit_quant_type="nf4",
        )
    else:
        logger.info("Loading base model in bf16 (full LoRA, no quantization)...")

    t0 = time.time()
    model = AutoModelForCausalLM.from_pretrained(
        args.model_name,
        **model_kwargs,
    )

    if args.use_gradient_checkpointing:
        model.gradient_checkpointing_enable()
        logger.info("Gradient checkpointing enabled")

    tokenizer = AutoTokenizer.from_pretrained(args.model_name)

    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token
        tokenizer.pad_token_id = tokenizer.eos_token_id

    logger.info("Model loaded in %.1fs", time.time() - t0)

    # ── LoRA config ───────────────────────────────────────────────────────
    target_modules = qwen35moe_lora_targets(model)
    lora_config = LoraConfig(
        r=args.lora_r,
        lora_alpha=args.lora_alpha,
        lora_dropout=args.lora_dropout,
        target_modules=target_modules,
        bias="none",
        task_type=TaskType.CAUSAL_LM,
    )

    model = get_peft_model(model, lora_config)
    trainable, total, pct = count_trainable_params(model)
    logger.info("Trainable: %s / %s (%.2f%%)", f"{trainable:,}", f"{total:,}", pct)

    # ── Dataset ───────────────────────────────────────────────────────────
    dataset_path = Path(args.dataset_path)
    if not dataset_path.exists():
        raise FileNotFoundError(f"Dataset not found: {dataset_path}")

    train_dataset = StreamingJSONLDataset(
        dataset_path,
        tokenizer=tokenizer,
        max_length=args.max_seq_length,
        max_samples=args.max_samples,
        seed=args.seed,
    )

    dataloader = torch.utils.data.DataLoader(
        train_dataset,
        batch_size=args.batch_size,
        collate_fn=collate_pad,
        num_workers=0,
        pin_memory=True,
    )

    # ── Optimizer & scheduler ─────────────────────────────────────────────
    optimizer = torch.optim.AdamW(
        model.parameters(),
        lr=args.learning_rate,
        weight_decay=args.weight_decay,
    )

    # Estimate total steps for scheduler
    if args.max_samples:
        estimated_samples = args.max_samples
    else:
        # Quick count of dataset entries (first pass only counts lines)
        with open(dataset_path, encoding="utf-8") as f:
            estimated_samples = sum(1 for _ in f)
    total_steps = (estimated_samples // args.batch_size) * args.epochs
    total_steps = total_steps // args.gradient_accumulation
    total_steps = max(1, total_steps)

    scheduler = get_cosine_schedule_with_warmup(
        optimizer,
        num_warmup_steps=max(1, int(total_steps * args.warmup_ratio)),
        num_training_steps=total_steps,
    )

    # ── Accelerate prepare ────────────────────────────────────────────────
    model, optimizer, dataloader, scheduler = accelerator.prepare(
        model, optimizer, dataloader, scheduler
    )

    # ── Training loop ─────────────────────────────────────────────────────
    os.makedirs(args.output_dir, exist_ok=True)
    global_step = 0
    best_loss = float("inf")

    for epoch in range(args.epochs):
        model.train()
        epoch_loss = 0.0
        epoch_start = time.time()
        progress = 0

        for step, batch in enumerate(dataloader):
            with accelerator.accumulate(model):
                outputs = model(**batch)
                loss = outputs.loss
                accelerator.backward(loss)

                if accelerator.sync_gradients:
                    accelerator.clip_grad_norm_(model.parameters(), max_norm=1.0)

                optimizer.step()
                scheduler.step()
                optimizer.zero_grad()

            epoch_loss += loss.detach().float().item()
            global_step += 1
            progress += 1

            if global_step % 10 == 0 and accelerator.is_main_process:
                avg_loss = epoch_loss / max(progress, 1)
                lr = scheduler.get_last_lr()[0]
                logger.info(
                    "Step %d | loss=%.4f avg=%.4f lr=%.2e",
                    global_step,
                    loss.item(),
                    avg_loss,
                    lr,
                )

            if global_step % args.save_steps == 0 and accelerator.is_main_process:
                ckpt_dir = os.path.join(args.output_dir, f"checkpoint-{global_step}")
                unwrapped = accelerator.unwrap_model(model)
                unwrapped.save_pretrained(ckpt_dir)
                tokenizer.save_pretrained(ckpt_dir)
                logger.info("Checkpoint saved: %s", ckpt_dir)

        avg_epoch_loss = epoch_loss / max(progress, 1)
        epoch_time = time.time() - epoch_start

        if accelerator.is_main_process:
            logger.info(
                "Epoch %d/%d — loss=%.4f time=%.1fs",
                epoch + 1,
                args.epochs,
                avg_epoch_loss,
                epoch_time,
            )

            if avg_epoch_loss < best_loss:
                best_loss = avg_epoch_loss
                unwrapped = accelerator.unwrap_model(model)
                unwrapped.save_pretrained(os.path.join(args.output_dir, "best"))
                tokenizer.save_pretrained(os.path.join(args.output_dir, "best"))
                logger.info("Best model saved (loss=%.4f)", best_loss)

    # ── Final save ────────────────────────────────────────────────────────
    if accelerator.is_main_process:
        final_dir = os.path.join(args.output_dir, "final")
        unwrapped = accelerator.unwrap_model(model)
        unwrapped.save_pretrained(final_dir)
        tokenizer.save_pretrained(final_dir)
        logger.info("Final model saved: %s", final_dir)

    accelerator.end_training()


if __name__ == "__main__":
    args = parse_args()
    train(args)
