"""QLoRA 4-bit training loop — fine-tunes CEO model with SFT data.

Target: Qwen3.6-35B (~35B params).
Requires: torch, transformers, peft, bitsandbytes, accelerate.

For large-scale training on cloud GPU (80GB+), use:
    scripts/finetune_qwen_sft.py

This module is for programmatic training from within the pipeline
(recorded trade outcomes → fine-tune CEO).
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# Default CEO model — override via env SUPEREZIO_TRAIN_MODEL
_CEO_MODEL = os.getenv(
    "SUPEREZIO_TRAIN_MODEL",
    "Qwen/Qwen3.6-35B",
)

# Standard Qwen attention + MLP projections
_QWEN_LORA_TARGETS = [
    "q_proj", "k_proj", "v_proj", "o_proj",
    "gate_proj", "up_proj", "down_proj",
]


@dataclass
class TrainingConfig:
    model_name: str = _CEO_MODEL
    lora_r: int = 64
    lora_alpha: int = 128
    lora_dropout: float = 0.05
    lora_targets: list[str] | None = None  # None = auto-detect Qwen targets
    learning_rate: float = 2e-4
    num_epochs: int = 1
    batch_size: int = 1
    gradient_accumulation_steps: int = 16
    max_seq_length: int = 4096
    output_dir: str = "models/lora_ceo"
    use_4bit: bool = True  # 4-bit NF4 quantization
    use_gpu: bool = True
    warmup_ratio: float = 0.03
    weight_decay: float = 0.01
    eval_split: float = 0.05  # 5% held out
    seed: int = 42


@dataclass
class TrainingResult:
    success: bool
    output_dir: str
    final_loss: float = 0.0
    eval_loss: float = 0.0
    epochs_completed: int = 0
    samples_used: int = 0
    trainable_params: int = 0
    pct_trainable: float = 0.0
    error: str = ""


class LoRATrainer:
    """QLoRA 4-bit fine-tuning for the Qwen3.6-35B CEO model.

    For small datasets (<1000 examples), train locally.
    For full 410K dataset, use scripts/finetune_qwen_sft.py on vast.ai.
    """

    def __init__(self, config: TrainingConfig | None = None):
        self.config = config or TrainingConfig()

    def check_dependencies(self) -> list[str]:
        missing = []
        for pkg in ("torch", "transformers", "peft", "accelerate"):
            try:
                __import__(pkg)
            except ImportError:
                missing.append(pkg)
        if self.config.use_4bit:
            try:
                __import__("bitsandbytes")
            except ImportError:
                missing.append("bitsandbytes")
        return missing

    def train_from_jsonl(self, jsonl_path: str) -> TrainingResult:
        missing = self.check_dependencies()
        if missing:
            return TrainingResult(
                success=False, output_dir="",
                error=f"Missing packages: {', '.join(missing)}",
            )
        if not os.path.exists(jsonl_path):
            return TrainingResult(
                success=False, output_dir="",
                error=f"Dataset not found: {jsonl_path}",
            )

        samples = self._load_dataset(jsonl_path)
        if len(samples) == 0:
            return TrainingResult(
                success=False, output_dir="",
                error="No valid samples in dataset",
            )

        try:
            return self._run_training(samples)
        except Exception as exc:
            logger.error("Training failed: %s", exc)
            return TrainingResult(
                success=False,
                output_dir=self.config.output_dir,
                error=str(exc),
            )

    def _load_dataset(self, path: str) -> list[dict]:
        samples = []
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                    if "instruction" in row and "response" in row:
                        samples.append(row)
                except json.JSONDecodeError:
                    continue
        return samples

    def _run_training(self, samples: list[dict]) -> TrainingResult:
        import torch
        from peft import LoraConfig, TaskType, get_peft_model
        from transformers import (
            AutoModelForCausalLM,
            AutoTokenizer,
            BitsAndBytesConfig,
            get_cosine_schedule_with_warmup,
        )

        cfg = self.config
        device = "cuda" if cfg.use_gpu and torch.cuda.is_available() else "cpu"

        # ── 4-bit quantization ─────────────────────────────────────────
        model_kwargs: dict = {}
        if cfg.use_4bit and device == "cuda":
            bnb_config = BitsAndBytesConfig(
                load_in_4bit=True,
                bnb_4bit_compute_dtype=torch.bfloat16,
                bnb_4bit_use_double_quant=True,
                bnb_4bit_quant_type="nf4",
            )
            model_kwargs["quantization_config"] = bnb_config
            model_kwargs["torch_dtype"] = torch.bfloat16
        else:
            model_kwargs["torch_dtype"] = torch.float16 if device == "cuda" else torch.float32

        logger.info("Loading model %s on %s (4bit=%s)", cfg.model_name, device, cfg.use_4bit)
        tokenizer = AutoTokenizer.from_pretrained(cfg.model_name)
        model = AutoModelForCausalLM.from_pretrained(
            cfg.model_name,
            device_map=device,
            trust_remote_code=True,
            **model_kwargs,
        )

        if tokenizer.pad_token is None:
            tokenizer.pad_token = tokenizer.eos_token
            tokenizer.pad_token_id = tokenizer.eos_token_id

        # ── LoRA config ────────────────────────────────────────────────
        targets = cfg.lora_targets or _QWEN_LORA_TARGETS
        lora_config = LoraConfig(
            r=cfg.lora_r,
            lora_alpha=cfg.lora_alpha,
            lora_dropout=cfg.lora_dropout,
            target_modules=targets,
            bias="none",
            task_type=TaskType.CAUSAL_LM,
        )
        model = get_peft_model(model, lora_config)

        total_params = sum(p.numel() for p in model.parameters())
        trainable_params = sum(p.numel() for p in model.parameters() if p.requires_grad)
        pct = trainable_params / total_params * 100 if total_params else 0
        logger.info("Trainable: %s / %s (%.2f%%)", f"{trainable_params:,}", f"{total_params:,}", pct)

        # ── Prepare dataset ────────────────────────────────────────────
        texts = []
        for s in samples:
            text = f"### Instruction:\n{s['instruction']}\n\n"
            if s.get("context"):
                text += f"### Context:\n{s['context']}\n\n"
            text += f"### Response:\n{s['response']}"
            texts.append(text)

        # Split train/eval
        import random
        rng = random.Random(cfg.seed)
        indices = list(range(len(texts)))
        rng.shuffle(indices)
        eval_n = max(1, int(len(texts) * cfg.eval_split))
        train_idx = set(indices[eval_n:])
        eval_idx = set(indices[:eval_n])

        train_texts = [texts[i] for i in sorted(train_idx)]
        eval_texts = [texts[i] for i in sorted(eval_idx)]

        # Tokenize
        train_enc = tokenizer(
            train_texts, truncation=True, max_length=cfg.max_seq_length,
            padding=True, return_tensors="pt",
        )
        eval_enc = tokenizer(
            eval_texts, truncation=True, max_length=cfg.max_seq_length,
            padding=True, return_tensors="pt",
        )

        input_ids = train_enc["input_ids"].to(device)
        attention_mask = train_enc["attention_mask"].to(device)
        eval_ids = eval_enc["input_ids"].to(device)
        eval_mask = eval_enc["attention_mask"].to(device)

        # ── Optimizer & scheduler ──────────────────────────────────────
        optimizer = torch.optim.AdamW(
            model.parameters(),
            lr=cfg.learning_rate,
            weight_decay=cfg.weight_decay,
        )
        steps_per_epoch = max(1, len(train_texts) // (cfg.batch_size * cfg.gradient_accumulation_steps))
        total_steps = steps_per_epoch * cfg.num_epochs
        scheduler = get_cosine_schedule_with_warmup(
            optimizer,
            num_warmup_steps=max(1, int(total_steps * cfg.warmup_ratio)),
            num_training_steps=total_steps,
        )

        # ── Training loop ──────────────────────────────────────────────
        final_loss = 0.0
        eval_loss = 0.0
        global_step = 0

        for epoch in range(cfg.num_epochs):
            model.train()
            total_loss = 0.0
            n_batches = 0
            accum_loss = 0.0

            for i in range(0, len(train_texts), cfg.batch_size):
                batch_ids = input_ids[i : i + cfg.batch_size]
                batch_mask = attention_mask[i : i + cfg.batch_size]

                outputs = model(
                    input_ids=batch_ids,
                    attention_mask=batch_mask,
                    labels=batch_ids,
                )
                loss = outputs.loss / cfg.gradient_accumulation_steps
                accum_loss += loss.item()
                loss.backward()

                if (i // cfg.batch_size + 1) % cfg.gradient_accumulation_steps == 0:
                    torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
                    optimizer.step()
                    scheduler.step()
                    optimizer.zero_grad()
                    total_loss += accum_loss
                    accum_loss = 0.0
                    n_batches += 1
                    global_step += 1

            avg_loss = total_loss / max(n_batches, 1)
            final_loss = avg_loss
            logger.info("Epoch %d/%d — loss: %.4f steps: %d", epoch + 1, cfg.num_epochs, avg_loss, global_step)

            # Eval
            if eval_texts:
                model.eval()
                with torch.no_grad():
                    eval_out = model(input_ids=eval_ids, attention_mask=eval_mask, labels=eval_ids)
                    eval_loss = eval_out.loss.item()
                logger.info("Eval loss: %.4f", eval_loss)

        # ── Save ───────────────────────────────────────────────────────
        os.makedirs(cfg.output_dir, exist_ok=True)
        model.save_pretrained(cfg.output_dir)
        tokenizer.save_pretrained(cfg.output_dir)
        logger.info("Model saved to %s", cfg.output_dir)

        return TrainingResult(
            success=True,
            output_dir=cfg.output_dir,
            final_loss=round(final_loss, 6),
            eval_loss=round(eval_loss, 6),
            epochs_completed=cfg.num_epochs,
            samples_used=len(samples),
            trainable_params=trainable_params,
            pct_trainable=round(pct, 4),
        )
