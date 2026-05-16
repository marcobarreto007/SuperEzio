"""LoRA training loop — fine-tunes CEO model with SFT data."""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class TrainingConfig:
    model_name: str = "Qwen/Qwen2.5-1.5B-Instruct"
    lora_r: int = 16
    lora_alpha: int = 32
    lora_dropout: float = 0.05
    learning_rate: float = 2e-4
    num_epochs: int = 3
    batch_size: int = 4
    max_seq_length: int = 512
    output_dir: str = "models/lora_ceo"
    use_gpu: bool = True


@dataclass
class TrainingResult:
    success: bool
    output_dir: str
    final_loss: float = 0.0
    epochs_completed: int = 0
    samples_used: int = 0
    error: str = ""


class LoRATrainer:
    """LoRA fine-tuning for the CEO decision model.

    Requires: torch, transformers, peft, trl (all installed in this environment).
    """

    def __init__(self, config: TrainingConfig | None = None):
        self.config = config or TrainingConfig()

    def check_dependencies(self) -> list[str]:
        missing = []
        for pkg in ("torch", "transformers", "peft", "trl"):
            try:
                __import__(pkg)
            except ImportError:
                missing.append(pkg)
        return missing

    def train_from_jsonl(self, jsonl_path: str) -> TrainingResult:
        missing = self.check_dependencies()
        if missing:
            return TrainingResult(
                success=False,
                output_dir="",
                error=f"Missing packages: {', '.join(missing)}",
            )

        if not os.path.exists(jsonl_path):
            return TrainingResult(
                success=False,
                output_dir="",
                error=f"Dataset not found: {jsonl_path}",
            )

        samples = self._load_dataset(jsonl_path)
        if len(samples) == 0:
            return TrainingResult(
                success=False,
                output_dir="",
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
        from peft import LoraConfig, get_peft_model
        from transformers import AutoModelForCausalLM, AutoTokenizer

        cfg = self.config
        device = "cuda" if cfg.use_gpu and torch.cuda.is_available() else "cpu"

        logger.info("Loading model %s on %s", cfg.model_name, device)
        tokenizer = AutoTokenizer.from_pretrained(cfg.model_name)
        model = AutoModelForCausalLM.from_pretrained(
            cfg.model_name,
            torch_dtype=torch.float16 if device == "cuda" else torch.float32,
            device_map=device,
        )

        lora_config = LoraConfig(
            r=cfg.lora_r,
            lora_alpha=cfg.lora_alpha,
            lora_dropout=cfg.lora_dropout,
            bias="none",
            task_type="CAUSAL_LM",
        )
        model = get_peft_model(model, lora_config)
        model.print_trainable_parameters()

        # Prepare dataset
        texts = []
        for s in samples:
            text = f"### Instruction:\n{s['instruction']}\n\n"
            if s.get("context"):
                text += f"### Context:\n{s['context']}\n\n"
            text += f"### Response:\n{s['response']}"
            texts.append(text)

        encodings = tokenizer(
            texts,
            truncation=True,
            max_length=cfg.max_seq_length,
            padding=True,
            return_tensors="pt",
        )

        # Simple training loop
        optimizer = torch.optim.AdamW(model.parameters(), lr=cfg.learning_rate)
        input_ids = encodings["input_ids"].to(device)
        attention_mask = encodings["attention_mask"].to(device)

        final_loss = 0.0
        for epoch in range(cfg.num_epochs):
            model.train()
            total_loss = 0.0
            n_batches = 0

            for i in range(0, len(texts), cfg.batch_size):
                batch_ids = input_ids[i : i + cfg.batch_size]
                batch_mask = attention_mask[i : i + cfg.batch_size]

                outputs = model(
                    input_ids=batch_ids,
                    attention_mask=batch_mask,
                    labels=batch_ids,
                )
                loss = outputs.loss
                loss.backward()
                optimizer.step()
                optimizer.zero_grad()

                total_loss += loss.item()
                n_batches += 1

            avg_loss = total_loss / max(n_batches, 1)
            final_loss = avg_loss
            logger.info(
                "Epoch %d/%d — loss: %.4f", epoch + 1, cfg.num_epochs, avg_loss
            )

        os.makedirs(cfg.output_dir, exist_ok=True)
        model.save_pretrained(cfg.output_dir)
        tokenizer.save_pretrained(cfg.output_dir)

        logger.info("Model saved to %s", cfg.output_dir)
        return TrainingResult(
            success=True,
            output_dir=cfg.output_dir,
            final_loss=round(final_loss, 6),
            epochs_completed=cfg.num_epochs,
            samples_used=len(samples),
        )
