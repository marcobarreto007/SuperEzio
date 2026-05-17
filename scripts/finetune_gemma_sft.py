"""
QLoRA 4-bit SFT fine-tuning for Gemma-4-26B-A4B-abliterated.

Target: Gemma-4-26B dense (~26B params) on 80GB GPU (A100/H100/2xL40S).
Uses bitsandbytes NF4 4-bit quantization + PEFT LoRA.

Dataset: F51_Datasets/sft_output/f51_final_sft.jsonl — 410K entries
in messages array format (system/user/assistant roles).

Setup (vast.ai cloud GPU):
    pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu124
    pip install transformers>=4.51.0 accelerate>=1.0.0 peft>=0.14.0 bitsandbytes>=0.45.0
    pip install datasets>=3.0.0

Usage:
    # Full training on 80GB GPU
    python scripts/finetune_gemma_sft.py \
        --model google/gemma-4-26b \
        --dataset F51_Datasets/sft_output/f51_final_sft.jsonl \
        --output-dir output/gemma-sft \
        --epochs 1 --batch-size 1 --gradient-accumulation 16

    # Quick test with small subset
    python scripts/finetune_gemma_sft.py \
        --model google/gemma-4-26b \
        --dataset F51_Datasets/sft_output/f51_final_sft.jsonl \
        --output-dir output/gemma-sft-test \
        --max-samples 500 --epochs 1 --batch-size 1

    # Multi-GPU (accelerate)
    accelerate launch --num_processes 2 scripts/finetune_gemma_sft.py ...

    # Resume from checkpoint
    python scripts/finetune_gemma_sft.py --resume output/gemma-sft/checkpoint-1000
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
logger = logging.getLogger("finetune_gemma")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DATASET = PROJECT_ROOT / "F51_Datasets" / "sft_output" / "f51_final_sft.jsonl"
DEFAULT_OUTPUT = PROJECT_ROOT / "output" / "gemma-sft"
DEFAULT_MODEL = os.getenv("SUPEREZIO_TRAIN_MODEL", "google/gemma-4-26b")


# ── Helpers ──────────────────────────────────────────────────────────────


def gemma_lora_targets(model: nn.Module) -> list[str]:
    """Select LoRA target modules for Gemma architecture.

    Gemma uses standard attention: q_proj, k_proj, v_proj, o_proj
    plus MLP: gate_proj, up_proj, down_proj.
    """
    standard_targets = [
        "q_proj", "k_proj", "v_proj", "o_proj",
        "gate_proj", "up_proj", "down_proj",
    ]
    all_linears = set()
    for name, module in model.named_modules():
        if isinstance(module, nn.Linear):
            all_linears.add(name.split(".")[-1])

    targets = [t for t in standard_targets if t in all_linears]
    if not targets:
        targets = sorted(all_linears)
        logger.warning("Standard targets not found, using all: %s", targets)
    return targets


def count_trainable_params(model: nn.Module) -> tuple[int, int, float]:
    total = sum(p.numel() for p in model.parameters())
    trainable = sum(p.numel() for p in model.parameters() if p.requires_grad)
    return trainable, total, (trainable / total * 100 if total else 0)


# ── Dataset ──────────────────────────────────────────────────────────────


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
                        max_length=self.max_length,
                        truncation=True,
                    )
                except Exception:
                    continue

                buffer.append({
                    "input_ids": tokenized,
                    "labels": tokenized.copy(),
                })

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


# ── Training Loop ────────────────────────────────────────────────────────


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
    max_samples: int | None = None
    save_steps: int = 500
    eval_steps: int = 1000
    warmup_ratio: float = 0.03
    weight_decay: float = 0.01
    resume: str = ""
    seed: int = 42


def parse_args() -> TrainingArgs:
    p = argparse.ArgumentParser(description="QLoRA SFT for Gemma-4-26B")
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
        max_seq_length=ns.max_seq_length,
        max_samples=ns.max_samples,
        save_steps=ns.save_steps,
        eval_steps=ns.eval_steps,
        warmup_ratio=ns.warmup_ratio,
        weight_decay=ns.weight_decay,
        resume=ns.resume,
        seed=ns.seed,
    )


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
        logger.info("QLoRA SFT — Gemma-4-26B")
        logger.info("Model: %s", args.model_name)
        logger.info("Dataset: %s", args.dataset_path)
        logger.info("Output: %s", args.output_dir)
        logger.info("LoRA: r=%d alpha=%d dropout=%.2f", args.lora_r, args.lora_alpha, args.lora_dropout)
        logger.info("Training: epochs=%d batch=%d grad_accum=%d effective_batch=%d",
                    args.epochs, args.batch_size, args.gradient_accumulation,
                    args.batch_size * args.gradient_accumulation)
        logger.info("=" * 60)

    # ── Quantization config (4-bit NF4) ─────────────────────────────────
    bnb_config = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_compute_dtype=torch.bfloat16,
        bnb_4bit_use_double_quant=True,
        bnb_4bit_quant_type="nf4",
    )

    # ── Load model ──────────────────────────────────────────────────────
    logger.info("Loading base model in 4-bit...")
    t0 = time.time()
    model = AutoModelForCausalLM.from_pretrained(
        args.model_name,
        quantization_config=bnb_config,
        device_map="auto",
        torch_dtype=torch.bfloat16,
        trust_remote_code=True,
        attn_implementation="flash_attention_2",
    )
    tokenizer = AutoTokenizer.from_pretrained(args.model_name, trust_remote_code=True)

    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token
        tokenizer.pad_token_id = tokenizer.eos_token_id

    logger.info("Model loaded in %.1fs", time.time() - t0)

    # ── LoRA config ─────────────────────────────────────────────────────
    target_modules = gemma_lora_targets(model)
    logger.info("LoRA targets: %s", target_modules)

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

    # ── Dataset ─────────────────────────────────────────────────────────
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

    # ── Optimizer & scheduler ───────────────────────────────────────────
    optimizer = torch.optim.AdamW(
        model.parameters(),
        lr=args.learning_rate,
        weight_decay=args.weight_decay,
    )

    total_steps = len(list(train_dataset)) // args.batch_size if args.max_samples else 10000
    total_steps = total_steps * args.epochs // args.gradient_accumulation

    scheduler = get_cosine_schedule_with_warmup(
        optimizer,
        num_warmup_steps=int(total_steps * args.warmup_ratio),
        num_training_steps=total_steps,
    )

    # ── Accelerate prepare ──────────────────────────────────────────────
    model, optimizer, dataloader, scheduler = accelerator.prepare(
        model, optimizer, dataloader, scheduler
    )

    # ── Training loop ───────────────────────────────────────────────────
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
                    global_step, loss.item(), avg_loss, lr,
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
                epoch + 1, args.epochs, avg_epoch_loss, epoch_time,
            )

            if avg_epoch_loss < best_loss:
                best_loss = avg_epoch_loss
                unwrapped = accelerator.unwrap_model(model)
                unwrapped.save_pretrained(os.path.join(args.output_dir, "best"))
                tokenizer.save_pretrained(os.path.join(args.output_dir, "best"))
                logger.info("Best model saved (loss=%.4f)", best_loss)

    # ── Final save ──────────────────────────────────────────────────────
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
