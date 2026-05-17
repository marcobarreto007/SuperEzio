"""
Phase 1 QLoRA SFT — Numerical Literacy + Forecasting.
Optimized for A100 80GB. Saves checkpoints every ~25% for continuation.

Usage (1x A100):
    python3 finetune_phase1.py --dataset phase1_train.jsonl \
        --eval-dataset phase1_eval.jsonl \
        --output-dir /root/output/phase1-numerical \
        --batch-size 4 --gradient-accumulation 4
"""
from __future__ import annotations

import argparse
import json
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path

import torch
from transformers import (
    AutoModelForCausalLM, AutoTokenizer,
    BitsAndBytesConfig, TrainingArguments, DataCollatorForSeq2Seq,
)
from peft import LoraConfig, get_peft_model, prepare_model_for_kbit_training, TaskType
from datasets import Dataset

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S")
logger = logging.getLogger("phase1-sft")


@dataclass
class TrainConfig:
    model_id: str = "nvidia/NVIDIA-Nemotron-Nano-12B-v2"
    dataset_path: str = ""
    eval_dataset_path: str = ""
    output_dir: str = "/root/output/phase1-numerical"
    max_samples: int = 0
    max_length: int = 1024
    eval_split: float = 0.0
    epochs: int = 1
    batch_size: int = 4
    gradient_accumulation: int = 4
    lr: float = 1e-4
    warmup_steps: int = 30
    save_steps: int = 50
    eval_steps: int = 50
    logging_steps: int = 5
    max_grad_norm: float = 1.0
    lora_r: int = 16
    lora_alpha: int = 32
    lora_dropout: float = 0.05
    target_modules: list[str] = field(default_factory=lambda: [
        "q_proj", "k_proj", "v_proj", "o_proj", "up_proj", "down_proj",
    ])
    quant_type: str = "nf4"
    no_double_quant: bool = False
    lr_scheduler: str = "cosine"
    seed: int = 42
    run_name: str = "phase1-numerical"
    no_eval: bool = False


def load_model_4bit(config: TrainConfig):
    compute_dtype = torch.bfloat16
    bnb_config = BitsAndBytesConfig(
        load_in_4bit=True, bnb_4bit_quant_type=config.quant_type,
        bnb_4bit_compute_dtype=compute_dtype, bnb_4bit_use_double_quant=not config.no_double_quant,
        llm_int8_enable_fp32_cpu_offload=True,
    )
    logger.info("Loading tokenizer: %s", config.model_id)
    tokenizer = AutoTokenizer.from_pretrained(config.model_id)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token
    logger.info("Loading model in 4-bit: %s", config.model_id)
    model = AutoModelForCausalLM.from_pretrained(
        config.model_id, quantization_config=bnb_config,
        device_map="auto", torch_dtype=compute_dtype,
    )
    params = sum(p.numel() for p in model.parameters()) / 1e9
    vram = torch.cuda.memory_allocated() / 1e9
    total = torch.cuda.get_device_properties(0).total_memory / 1e9
    logger.info("Model: %.2fB params | VRAM: %.1f GB / %.1f GB", params, vram, total)
    return model, tokenizer


def apply_lora(model, config: TrainConfig):
    model = prepare_model_for_kbit_training(model)
    lora_config = LoraConfig(
        r=config.lora_r, lora_alpha=config.lora_alpha,
        lora_dropout=config.lora_dropout, bias="none",
        task_type=TaskType.CAUSAL_LM, target_modules=config.target_modules,
    )
    model = get_peft_model(model, lora_config)
    trainable = sum(p.numel() for p in model.parameters() if p.requires_grad)
    total = sum(p.numel() for p in model.parameters())
    logger.info("LoRA: %.2fM trainable / %.2fB total (%.2f%%)",
                trainable / 1e6, total / 1e9, 100 * trainable / total)
    return model


def load_sft_dataset(path: str, tokenizer, max_samples: int, max_length: int):
    logger.info("Loading dataset: %s", path)
    raw_data = []
    with open(path, encoding="utf-8") as f:
        for i, line in enumerate(f):
            if max_samples > 0 and i >= max_samples:
                break
            line = line.strip()
            if line:
                raw_data.append(json.loads(line))
    logger.info("Loaded %d examples", len(raw_data))

    texts = []
    for entry in raw_data:
        messages = entry.get("messages", [])
        text_parts = []
        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            if role == "system":
                text_parts.append(f"<|system|>\n{content}")
            elif role == "user":
                text_parts.append(f"<|user|>\n{content}")
            elif role == "assistant":
                text_parts.append(f"<|assistant|>\n{content}")
        texts.append("\n".join(text_parts))

    tokenized = tokenizer(texts, truncation=True, max_length=max_length, padding=False)
    dataset = Dataset.from_dict({
        "input_ids": tokenized["input_ids"],
        "attention_mask": tokenized["attention_mask"],
        "labels": [ids.copy() for ids in tokenized["input_ids"]],
    })
    logger.info("Tokenized: %d examples", len(dataset))
    return dataset


def train(config: TrainConfig):
    torch.manual_seed(config.seed)

    model, tokenizer = load_model_4bit(config)
    model = apply_lora(model, config)

    train_ds = load_sft_dataset(config.dataset_path, tokenizer, config.max_samples, config.max_length)
    eval_ds = None
    if config.eval_dataset_path and not config.no_eval:
        eval_ds = load_sft_dataset(config.eval_dataset_path, tokenizer, 0, config.max_length)

    effective_batch = config.batch_size * config.gradient_accumulation
    output_dir = Path(config.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    training_args = TrainingArguments(
        output_dir=str(output_dir),
        per_device_train_batch_size=config.batch_size,
        per_device_eval_batch_size=config.batch_size,
        gradient_accumulation_steps=config.gradient_accumulation,
        num_train_epochs=config.epochs,
        learning_rate=config.lr,
        lr_scheduler_type=config.lr_scheduler,
        warmup_steps=config.warmup_steps,
        logging_steps=config.logging_steps,
        save_steps=config.save_steps,
        eval_steps=config.eval_steps if eval_ds else None,
        eval_strategy="steps" if eval_ds else "no",
        save_strategy="steps",
        max_grad_norm=config.max_grad_norm,
        bf16=True, fp16=False,
        optim="paged_adamw_8bit",
        seed=config.seed,
        report_to="none",
        run_name=config.run_name,
        save_total_limit=5,
        load_best_model_at_end=False,
        ddp_find_unused_parameters=False,
        dataloader_num_workers=2,
        remove_unused_columns=False,
    )
    training_args.report_to = []

    logger.info("Training: epochs=%d batch=%d grad_acc=%d effective=%d",
                config.epochs, config.batch_size, config.gradient_accumulation, effective_batch)
    logger.info("  LR=%.2e LoRA(r=%d,a=%d) max_length=%d", config.lr, config.lora_r, config.lora_alpha, config.max_length)

    from transformers import Trainer
    model.gradient_checkpointing_enable()

    data_collator = DataCollatorForSeq2Seq(tokenizer=tokenizer, model=model, padding=True)

    trainer = Trainer(
        model=model, args=training_args,
        train_dataset=train_ds, eval_dataset=eval_ds,
        processing_class=tokenizer, data_collator=data_collator,
    )

    logger.info("Starting Phase 1 training...")
    start = time.time()
    trainer.train()
    elapsed = time.time() - start
    logger.info("Training completed in %.1f min (%.1f h)", elapsed / 60, elapsed / 3600)

    final_dir = output_dir / "final"
    trainer.save_model(str(final_dir))
    tokenizer.save_pretrained(str(final_dir))
    logger.info("Final adapter: %s", final_dir)

    return str(final_dir)


def main():
    parser = argparse.ArgumentParser(description="Phase 1: Numerical Literacy QLoRA SFT")
    parser.add_argument("--dataset", required=True)
    parser.add_argument("--eval-dataset", default="")
    parser.add_argument("--output-dir", default="/root/output/phase1-numerical")
    parser.add_argument("--max-samples", type=int, default=0)
    parser.add_argument("--max-length", type=int, default=1024)
    parser.add_argument("--epochs", type=int, default=1)
    parser.add_argument("--batch-size", type=int, default=4)
    parser.add_argument("--gradient-accumulation", type=int, default=4)
    parser.add_argument("--lr", type=float, default=1e-4)
    parser.add_argument("--warmup-steps", type=int, default=30)
    parser.add_argument("--save-steps", type=int, default=50)
    parser.add_argument("--logging-steps", type=int, default=5)
    parser.add_argument("--lora-r", type=int, default=16)
    parser.add_argument("--lora-alpha", type=int, default=32)
    parser.add_argument("--lora-dropout", type=float, default=0.05)
    parser.add_argument("--lr-scheduler", default="cosine")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--no-eval", action="store_true")
    parser.add_argument("--no-double-quant", action="store_true")

    args = parser.parse_args()
    cfg = TrainConfig(
        dataset_path=args.dataset,
        eval_dataset_path=args.eval_dataset,
        output_dir=args.output_dir,
        max_samples=args.max_samples,
        max_length=args.max_length,
        epochs=args.epochs,
        batch_size=args.batch_size,
        gradient_accumulation=args.gradient_accumulation,
        lr=args.lr,
        warmup_steps=args.warmup_steps,
        save_steps=args.save_steps,
        logging_steps=args.logging_steps,
        lora_r=args.lora_r,
        lora_alpha=args.lora_alpha,
        lora_dropout=args.lora_dropout,
        lr_scheduler=args.lr_scheduler,
        seed=args.seed,
        no_eval=args.no_eval,
        no_double_quant=args.no_double_quant,
    )
    output = train(cfg)
    print(f"\nDone! Adapter saved to: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
