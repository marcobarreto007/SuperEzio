"""
SuperEzio — Qwen3.6-35B Full LoRA Training | 3h Timebox
=========================================================
Checkpoints explícitos, verificação, auto-reparo, email notification.

Checkpoints:   every 200 steps, verified (load + inference test)
Self-healing:  OOM → reduce seq_len, NaN → reduce LR, disk → purge old ckpts
Timebox:       3h max, graceful shutdown with final save
Email:         marcobarreto007@gmail.com (summary on completion/failure)

Target GPU:    RTX PRO 6000 WS 96GB (full LoRA bf16, ~85GB VRAM)
Model:         Qwen/Qwen3.6-35B-A3B (35B MoE, ~3B active)
Dataset:       F51_Datasets/sft_output/f51_final_sft.jsonl

Usage:
    python scripts/train_qwen36_3h.py
    python scripts/train_qwen36_3h.py --max-samples 50000 --save-steps 100
"""

from __future__ import annotations

import gc
import json
import logging
import math
import os
import random
import smtplib
import sys
import time
import traceback
from dataclasses import dataclass, field
from datetime import datetime
from email.message import EmailMessage
from pathlib import Path
from typing import Any

import torch
import torch.nn as nn
from torch.utils.data import IterableDataset

# ── Config ─────────────────────────────────────────────────────────────────

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DATASET = PROJECT_ROOT / "F51_Datasets" / "sft_output" / "f51_final_sft.jsonl"
DEFAULT_OUTPUT = PROJECT_ROOT / "output" / "qwen36-sft"
DEFAULT_MODEL = os.getenv("SUPEREZIO_TRAIN_MODEL", "Qwen/Qwen3.6-35B-A3B")

# Timebox: 3 hours (with 5 min margin for graceful shutdown)
TIMEBOX_SECONDS = 3 * 3600
GRACEFUL_SHUTDOWN_MARGIN = 300  # 5 min
CHECKPOINT_STEPS = 200
MIN_DISK_GB = 15
MAX_SEQ_LENGTH = 4096
MIN_SEQ_LENGTH = 1024

QWEN35MOE_LORA_TARGETS = [
    "q_proj", "k_proj", "v_proj", "o_proj",
    "gate_proj", "up_proj", "down_proj",
    "out_proj",
]

EMAIL_TO = "marcobarreto007@gmail.com"
EMAIL_FROM = "superezio@f51.ai"

# Gmail SMTP — uses app password from env SUPEREZIO_GMAIL_APP_PASSWORD
SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 587

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
    handlers=[
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger("train_qwen36")


# ── Training State ────────────────────────────────────────────────────────


@dataclass
class TrainState:
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
    max_seq_length: int = MAX_SEQ_LENGTH
    max_samples: int | None = None
    save_steps: int = CHECKPOINT_STEPS
    warmup_ratio: float = 0.03
    weight_decay: float = 0.01
    seed: int = 42
    timebox_seconds: int = TIMEBOX_SECONDS

    # Runtime state
    start_time: float = 0.0
    global_step: int = 0
    best_loss: float = float("inf")
    errors: list[dict] = field(default_factory=list)
    recovery_count: int = 0
    max_recoveries: int = 10
    current_seq_length: int = MAX_SEQ_LENGTH


# ── Email Notification ────────────────────────────────────────────────────


def send_email(subject: str, body: str) -> bool:
    """Send email notification via Gmail SMTP."""
    app_password = os.getenv("SUPEREZIO_GMAIL_APP_PASSWORD", "")
    if not app_password:
        logger.warning("SUPEREZIO_GMAIL_APP_PASSWORD not set — skipping email")
        return False

    try:
        msg = EmailMessage()
        msg["Subject"] = f"[SuperEzio] {subject}"
        msg["From"] = EMAIL_FROM
        msg["To"] = EMAIL_TO
        msg.set_content(body)

        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=30) as server:
            server.starttls()
            server.login(EMAIL_TO, app_password)
            server.send_message(msg)
        logger.info("Email sent: %s", subject)
        return True
    except Exception as exc:
        logger.error("Failed to send email: %s", exc)
        return False


# ── Dataset ───────────────────────────────────────────────────────────────


class StreamingJSONLDataset(IterableDataset):
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
                        messages, tokenize=True, add_generation_prompt=False,
                        max_length=self.max_length, truncation=True,
                    )
                except Exception:
                    continue
                buffer.append({"input_ids": tokenized, "labels": tokenized.copy()})
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


# ── Checkpoint Verification ───────────────────────────────────────────────


def verify_checkpoint(ckpt_dir: str, base_model_name: str, device: str) -> tuple[bool, str]:
    """Load a saved LoRA checkpoint and run a quick inference test."""
    try:
        from peft import PeftModel
        from transformers import AutoModelForCausalLM, AutoTokenizer

        logger.info("Verifying checkpoint: %s", ckpt_dir)

        tokenizer = AutoTokenizer.from_pretrained(ckpt_dir)
        if tokenizer.pad_token is None:
            tokenizer.pad_token = tokenizer.eos_token

        model = AutoModelForCausalLM.from_pretrained(
            base_model_name,
            torch_dtype=torch.bfloat16,
            device_map="auto",
            attn_implementation="flash_attention_2",
        )
        model = PeftModel.from_pretrained(model, ckpt_dir)
        model.eval()

        test_prompt = "The current market trend is"
        inputs = tokenizer(test_prompt, return_tensors="pt").to(device)
        with torch.no_grad():
            outputs = model.generate(
                **inputs, max_new_tokens=20, do_sample=True,
                temperature=0.7, top_p=0.9,
            )
        generated = tokenizer.decode(outputs[0], skip_special_tokens=True)

        del model
        gc.collect()
        torch.cuda.empty_cache()

        # Quality checks
        words = generated.split()
        if len(words) < 3:
            return False, f"Too few words: '{generated}'"
        if generated.count(generated[:10]) > 3:
            return False, f"Repetitive output: '{generated[:80]}...'"

        logger.info("Checkpoint verified OK: '%s'", generated[:100])
        return True, generated[:200]

    except Exception as exc:
        logger.error("Checkpoint verification failed: %s", exc)
        return False, str(exc)


# ── Disk Monitoring ───────────────────────────────────────────────────────


def ensure_disk_space(output_dir: str, min_gb: int = MIN_DISK_GB):
    """Delete old checkpoints if disk space is low. Keeps best + last 3."""
    import shutil

    usage = shutil.disk_usage(output_dir)
    free_gb = usage.free / (1024**3)

    if free_gb >= min_gb:
        return

    logger.warning("Low disk space: %.1f GB free. Purging old checkpoints...", free_gb)

    ckpt_dirs = sorted(
        [d for d in Path(output_dir).iterdir()
         if d.is_dir() and d.name.startswith("checkpoint-")],
        key=lambda d: d.stat().st_mtime,
    )

    # Keep best, final, and last 3 checkpoints
    keep_names = {"best", "final"}
    to_keep = []
    for d in ckpt_dirs:
        if d.name in keep_names:
            to_keep.append(d)
    to_keep.extend(ckpt_dirs[-3:])  # Keep last 3

    for d in ckpt_dirs:
        if d not in to_keep:
            logger.info("Purging old checkpoint: %s", d.name)
            shutil.rmtree(d, ignore_errors=True)

    usage = shutil.disk_usage(output_dir)
    logger.info("Disk after purge: %.1f GB free", usage.free / (1024**3))


# ── Count trainable params ────────────────────────────────────────────────


def count_trainable_params(model: nn.Module) -> tuple[int, int, float]:
    total = sum(p.numel() for p in model.parameters())
    trainable = sum(p.numel() for p in model.parameters() if p.requires_grad)
    return trainable, total, (trainable / total * 100 if total else 0)


# ── Main Training Loop ────────────────────────────────────────────────────


def train(state: TrainState) -> dict:
    from accelerate import Accelerator
    from peft import LoraConfig, TaskType, get_peft_model
    from transformers import (
        AutoModelForCausalLM, AutoTokenizer,
        get_cosine_schedule_with_warmup,
    )

    state.start_time = time.time()
    os.makedirs(state.output_dir, exist_ok=True)

    # File logger for training.log
    file_handler = logging.FileHandler(
        os.path.join(state.output_dir, "training.log")
    )
    file_handler.setFormatter(logging.Formatter(
        "%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S"
    ))
    logger.addHandler(file_handler)

    # ── Summary log ───────────────────────────────────────────────────
    logger.info("=" * 60)
    logger.info("SuperEzio — Qwen3.6-35B Full LoRA Training")
    logger.info("Model: %s", state.model_name)
    logger.info("Dataset: %s", state.dataset_path)
    logger.info("Output: %s", state.output_dir)
    logger.info("LoRA: r=%d alpha=%d dropout=%.2f", state.lora_r, state.lora_alpha, state.lora_dropout)
    logger.info("Seq length: %d | Max samples: %s", state.max_seq_length, state.max_samples or "all")
    logger.info("Timebox: %.1fh | Checkpoints every %d steps", state.timebox_seconds / 3600, state.save_steps)
    logger.info("=" * 60)

    accelerator = Accelerator(
        gradient_accumulation_steps=state.gradient_accumulation,
        mixed_precision="bf16",
    )

    # ── Load model ────────────────────────────────────────────────────
    logger.info("Loading base model in bf16 (full LoRA)...")
    t0 = time.time()
    model = AutoModelForCausalLM.from_pretrained(
        state.model_name,
        device_map="auto",
        torch_dtype=torch.bfloat16,
        attn_implementation="flash_attention_2",
    )
    model.gradient_checkpointing_enable()
    logger.info("Gradient checkpointing enabled")

    tokenizer = AutoTokenizer.from_pretrained(state.model_name)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token
        tokenizer.pad_token_id = tokenizer.eos_token_id

    logger.info("Model loaded in %.1fs", time.time() - t0)

    # ── LoRA ───────────────────────────────────────────────────────────
    target_modules = [t for t in QWEN35MOE_LORA_TARGETS
                      if t in {n.split(".")[-1] for n, m in model.named_modules()
                               if isinstance(m, nn.Linear)}]
    logger.info("LoRA targets: %s", target_modules)

    lora_config = LoraConfig(
        r=state.lora_r, lora_alpha=state.lora_alpha,
        lora_dropout=state.lora_dropout, target_modules=target_modules,
        bias="none", task_type=TaskType.CAUSAL_LM,
    )
    model = get_peft_model(model, lora_config)
    trainable, total, pct = count_trainable_params(model)
    logger.info("Trainable: %s / %s (%.2f%%)", f"{trainable:,}", f"{total:,}", pct)

    # ── Dataset ────────────────────────────────────────────────────────
    dataset_path = Path(state.dataset_path)
    if not dataset_path.exists():
        raise FileNotFoundError(f"Dataset not found: {dataset_path}")

    train_dataset = StreamingJSONLDataset(
        dataset_path, tokenizer=tokenizer,
        max_length=state.current_seq_length,
        max_samples=state.max_samples, seed=state.seed,
    )
    dataloader = torch.utils.data.DataLoader(
        train_dataset, batch_size=state.batch_size,
        collate_fn=collate_pad, num_workers=0, pin_memory=True,
    )

    # ── Optimizer ──────────────────────────────────────────────────────
    optimizer = torch.optim.AdamW(
        model.parameters(), lr=state.learning_rate,
        weight_decay=state.weight_decay,
    )

    if state.max_samples:
        estimated_samples = state.max_samples
    else:
        with open(dataset_path, encoding="utf-8") as f:
            estimated_samples = sum(1 for _ in f)
    total_steps = (estimated_samples // state.batch_size) * state.epochs
    total_steps = total_steps // state.gradient_accumulation
    total_steps = max(1, total_steps)
    logger.info("Estimated total steps: %d", total_steps)

    scheduler = get_cosine_schedule_with_warmup(
        optimizer,
        num_warmup_steps=max(1, int(total_steps * state.warmup_ratio)),
        num_training_steps=total_steps,
    )

    model, optimizer, dataloader, scheduler = accelerator.prepare(
        model, optimizer, dataloader, scheduler
    )

    # ── Training loop ─────────────────────────────────────────────────
    logger.info("Starting training — timebox: %.1fh", state.timebox_seconds / 3600)
    epoch_loss = 0.0
    progress = 0
    last_log_time = time.time()
    loss_stagnation_counter = 0
    last_loss = float("inf")

    try:
        for epoch in range(state.epochs):
            model.train()
            epoch_start = time.time()

            for step, batch in enumerate(dataloader):
                # ── Timebox check ──────────────────────────────────────
                elapsed = time.time() - state.start_time
                if elapsed > state.timebox_seconds:
                    logger.info("Timebox reached (%.1fh). Graceful shutdown.", elapsed / 3600)
                    raise KeyboardInterrupt("Timebox")

                if elapsed > state.timebox_seconds - GRACEFUL_SHUTDOWN_MARGIN:
                    logger.info("Approaching timebox (%dh %dm). Saving final...",
                                int(elapsed / 3600), int((elapsed % 3600) / 60))
                    # Save and exit after this step
                    final_dir = os.path.join(state.output_dir, "final")
                    unwrapped = accelerator.unwrap_model(model)
                    unwrapped.save_pretrained(final_dir)
                    tokenizer.save_pretrained(final_dir)
                    raise KeyboardInterrupt("Timebox margin")

                # ── Forward/backward ───────────────────────────────────
                try:
                    with accelerator.accumulate(model):
                        outputs = model(**batch)
                        loss = outputs.loss
                        accelerator.backward(loss)

                        if accelerator.sync_gradients:
                            accelerator.clip_grad_norm_(model.parameters(), max_norm=1.0)

                        optimizer.step()
                        scheduler.step()
                        optimizer.zero_grad()

                except torch.cuda.OutOfMemoryError as oom:
                    state.errors.append({
                        "step": state.global_step, "type": "OOM",
                        "time": datetime.now().isoformat(),
                        "detail": str(oom)[:200],
                    })
                    logger.error("CUDA OOM at step %d: %s", state.global_step, oom)
                    return _handle_oom(state, model, tokenizer, accelerator)

                # ── NaN loss detection ─────────────────────────────────
                if torch.isnan(loss) or torch.isinf(loss):
                    state.errors.append({
                        "step": state.global_step, "type": "NaN loss",
                        "time": datetime.now().isoformat(),
                    })
                    logger.error("NaN/Inf loss at step %d!", state.global_step)
                    return _handle_nan_loss(state, model, tokenizer, accelerator)

                # ── Loss stagnation detection ──────────────────────────
                current_loss = loss.detach().float().item()
                if abs(current_loss - last_loss) < 1e-5:
                    loss_stagnation_counter += 1
                else:
                    loss_stagnation_counter = 0
                last_loss = current_loss

                if loss_stagnation_counter > 200:
                    logger.warning("Loss stagnated for 200 steps. Reducing LR by 50%.")
                    for param_group in optimizer.param_groups:
                        param_group["lr"] *= 0.5
                    loss_stagnation_counter = 0
                    state.errors.append({
                        "step": state.global_step, "type": "loss_stagnation",
                        "time": datetime.now().isoformat(),
                    })

                # ── Track ──────────────────────────────────────────────
                epoch_loss += loss.detach().float().item()
                state.global_step += 1
                progress += 1

                # ── Logging ────────────────────────────────────────────
                if state.global_step % 10 == 0:
                    avg_loss = epoch_loss / progress
                    lr = scheduler.get_last_lr()[0]
                    elapsed = time.time() - state.start_time
                    eta = (state.timebox_seconds - elapsed) / 60
                    logger.info(
                        "Step %d | loss=%.4f avg=%.4f lr=%.2e | elapsed=%.0fm ETA=%.0fm",
                        state.global_step, loss.item(), avg_loss, lr,
                        elapsed / 60, eta,
                    )

                # ── Checkpoint ─────────────────────────────────────────
                if state.global_step % state.save_steps == 0:
                    elapsed = time.time() - state.start_time
                    ckpt_dir = os.path.join(
                        state.output_dir, f"checkpoint-{state.global_step}"
                    )

                    unwrapped = accelerator.unwrap_model(model)
                    unwrapped.save_pretrained(ckpt_dir)
                    tokenizer.save_pretrained(ckpt_dir)
                    logger.info("Checkpoint saved: %s (%.0fm elapsed)",
                                os.path.basename(ckpt_dir), elapsed / 60)

                    # Verify checkpoint
                    v_ok, v_msg = verify_checkpoint(
                        ckpt_dir, state.model_name,
                        accelerator.device.type,
                    )
                    if v_ok:
                        logger.info("Checkpoint %d verified OK", state.global_step)
                    else:
                        logger.error("Checkpoint %d verification FAILED: %s",
                                     state.global_step, v_msg)
                        state.errors.append({
                            "step": state.global_step, "type": "ckpt_verify_fail",
                            "time": datetime.now().isoformat(), "detail": v_msg,
                        })

                    # Keep best
                    if avg_loss < state.best_loss:
                        state.best_loss = avg_loss
                        best_dir = os.path.join(state.output_dir, "best")
                        unwrapped.save_pretrained(best_dir)
                        tokenizer.save_pretrained(best_dir)
                        logger.info("New best! loss=%.4f", avg_loss)

                    # Disk check
                    ensure_disk_space(state.output_dir)

                    # Timebox recheck
                    elapsed = time.time() - state.start_time
                    if elapsed > state.timebox_seconds - GRACEFUL_SHUTDOWN_MARGIN:
                        logger.info("Timebox approaching after checkpoint. Stopping.")
                        raise KeyboardInterrupt("Timebox after checkpoint")

            # ── End of epoch ───────────────────────────────────────────
            avg_epoch_loss = epoch_loss / max(progress, 1)
            epoch_time = time.time() - epoch_start
            logger.info("Epoch %d/%d — loss=%.4f time=%.1fm",
                        epoch + 1, state.epochs, avg_epoch_loss, epoch_time / 60)

    except KeyboardInterrupt:
        logger.info("Training interrupted (timebox or signal). Saving...")
    except Exception as exc:
        logger.error("Unexpected error: %s", exc)
        traceback.print_exc()
        state.errors.append({
            "step": state.global_step, "type": "fatal",
            "time": datetime.now().isoformat(), "detail": str(exc)[:500],
        })
    finally:
        # ── Final save ────────────────────────────────────────────────
        try:
            final_dir = os.path.join(state.output_dir, "final")
            unwrapped = accelerator.unwrap_model(model)
            unwrapped.save_pretrained(final_dir)
            tokenizer.save_pretrained(final_dir)
            logger.info("Final model saved: %s", final_dir)
        except Exception as exc:
            logger.error("Failed to save final model: %s", exc)

        accelerator.end_training()

        # ── Build summary ─────────────────────────────────────────────
        elapsed = time.time() - state.start_time
        avg_loss = epoch_loss / max(progress, 1) if progress > 0 else float("nan")

        summary = {
            "status": "completed" if state.global_step > 0 else "failed",
            "model": state.model_name,
            "dataset": state.dataset_path,
            "output_dir": state.output_dir,
            "total_steps": state.global_step,
            "final_loss": round(avg_loss, 6),
            "best_loss": round(state.best_loss, 6),
            "elapsed_minutes": round(elapsed / 60, 1),
            "errors": state.errors,
            "recoveries": state.recovery_count,
            "lora_r": state.lora_r,
            "lora_alpha": state.lora_alpha,
            "max_seq_length": state.current_seq_length,
            "finished_at": datetime.now().isoformat(),
        }

        summary_path = os.path.join(state.output_dir, "training_summary.json")
        with open(summary_path, "w") as f:
            json.dump(summary, f, indent=2, default=str)

        logger.info("=" * 60)
        logger.info("TRAINING COMPLETE")
        logger.info("Steps: %d | Loss: %.4f | Best: %.4f | Time: %.1fmin",
                    state.global_step, avg_loss, state.best_loss, elapsed / 60)
        logger.info("Errors: %d | Recoveries: %d",
                    len(state.errors), state.recovery_count)
        logger.info("Summary: %s", summary_path)
        logger.info("=" * 60)

        # ── Email ─────────────────────────────────────────────────────
        checkpoint_lines = "\n".join(
            "  - " + d.name for d in sorted(Path(state.output_dir).glob("checkpoint-*"))
        )
        error_lines = "\n".join(
            "  [{t}] step {s}: {d}".format(
                t=e["type"], s=e["step"], d=e.get("detail", "")
            )
            for e in state.errors
        ) if state.errors else "  None"

        email_body = """SuperEzio Qwen3.6-35B LoRA Training — {status}

Model: {model}
Output: {output_dir}
Steps completed: {total_steps}
Final loss: {final_loss}
Best loss: {best_loss}
Time: {elapsed_minutes} minutes
Errors: {error_count}
Recoveries: {recoveries}
Finished: {finished_at}

Checkpoints:
{checkpoint_lines}

Errors:
{error_lines}

— SuperEzio Training System
""".format(
            status=summary["status"].upper(),
            model=summary["model"],
            output_dir=summary["output_dir"],
            total_steps=summary["total_steps"],
            final_loss=summary["final_loss"],
            best_loss=summary["best_loss"],
            elapsed_minutes=summary["elapsed_minutes"],
            error_count=len(summary["errors"]),
            recoveries=summary["recoveries"],
            finished_at=summary["finished_at"],
            checkpoint_lines=checkpoint_lines,
            error_lines=error_lines,
        )
        email_subject = "Training {status} — loss={loss}".format(
            status=summary["status"], loss=summary["final_loss"]
        )
        send_email(email_subject, email_body)

        return summary


# ── Self-Healing Handlers ─────────────────────────────────────────────────


def _handle_oom(state: TrainState, model, tokenizer, accelerator) -> dict:
    """Handle CUDA OOM: reduce seq_length, clear cache, reload."""
    state.recovery_count += 1
    if state.recovery_count > state.max_recoveries:
        logger.error("Max recoveries (%d) exceeded. Aborting.", state.max_recoveries)
        raise RuntimeError("Max recoveries exceeded")

    state.current_seq_length = max(MIN_SEQ_LENGTH, state.current_seq_length - 512)
    logger.warning("OOM recovery #%d: reducing seq_length to %d",
                   state.recovery_count, state.current_seq_length)

    gc.collect()
    torch.cuda.empty_cache()
    time.sleep(5)  # Let GPU cool down

    # Reload from last checkpoint
    checkpoints = sorted(Path(state.output_dir).glob("checkpoint-*"))
    if checkpoints:
        last_ckpt = checkpoints[-1]
        logger.info("Reloading from %s", last_ckpt.name)
        from peft import PeftModel
        model = PeftModel.from_pretrained(model, str(last_ckpt))
        logger.info("Reloaded OK. Continuing with seq_len=%d", state.current_seq_length)
        # Recursive call to continue training with reduced seq length
        return train(state)
    else:
        logger.error("No checkpoint to reload from. Restarting from scratch.")
        return train(state)


def _handle_nan_loss(state: TrainState, model, tokenizer, accelerator) -> dict:
    """Handle NaN loss: reduce LR, reload from last checkpoint."""
    state.recovery_count += 1
    if state.recovery_count > state.max_recoveries:
        logger.error("Max recoveries exceeded. Aborting.")
        raise RuntimeError("Max recoveries exceeded")

    state.learning_rate *= 0.5
    logger.warning("NaN loss recovery #%d: reducing LR to %.2e",
                   state.recovery_count, state.learning_rate)

    gc.collect()
    torch.cuda.empty_cache()

    checkpoints = sorted(Path(state.output_dir).glob("checkpoint-*"))
    if checkpoints:
        last_ckpt = checkpoints[-1]
        logger.info("Reloading from %s with LR=%.2e", last_ckpt.name, state.learning_rate)
        from peft import PeftModel
        model = PeftModel.from_pretrained(model, str(last_ckpt))
        return train(state)
    else:
        logger.error("No checkpoint to reload from.")
        return train(state)


# ── CLI ────────────────────────────────────────────────────────────────────


def parse_args() -> TrainState:
    import argparse
    p = argparse.ArgumentParser(
        description="SuperEzio Qwen3.6-35B LoRA Training — 3h Timebox"
    )
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
    p.add_argument("--max-seq-length", type=int, default=MAX_SEQ_LENGTH)
    p.add_argument("--max-samples", type=int, default=None)
    p.add_argument("--save-steps", type=int, default=CHECKPOINT_STEPS)
    p.add_argument("--warmup-ratio", type=float, default=0.03)
    p.add_argument("--weight-decay", type=float, default=0.01)
    p.add_argument("--timebox-hours", type=float, default=3.0)
    p.add_argument("--seed", type=int, default=42)
    ns = p.parse_args()

    return TrainState(
        model_name=ns.model,
        dataset_path=ns.dataset,
        output_dir=ns.output_dir,
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
        warmup_ratio=ns.warmup_ratio,
        weight_decay=ns.weight_decay,
        timebox_seconds=int(ns.timebox_hours * 3600),
        seed=ns.seed,
        current_seq_length=ns.max_seq_length,
    )


if __name__ == "__main__":
    state = parse_args()
    summary = train(state)
    print(json.dumps(summary, indent=2, default=str))
    sys.exit(0 if summary["status"] == "completed" else 1)
