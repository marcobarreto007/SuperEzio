"""
QLoRA 4-bit SFT fine-tuning for NVIDIA Qwen 3.6.

Architecture: QwenForCausalLM — hybrid Transformer + Mamba/SSM + MoE
(8 routed + 1 shared expert), ~6.8B active params.

Usage:
    python3 finetune_qwen36.py --dataset /root/f51_final_sft.jsonl \
        --output-dir /root/output/qwen36-sft \
        --max-samples 500 --epochs 1 --batch-size 2
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
    AutoModelForCausalLM,
    AutoTokenizer,
    BitsAndBytesConfig,
    TrainingArguments,
    DataCollatorForSeq2Seq,
)
from peft import LoraConfig, get_peft_model, prepare_model_for_kbit_training, TaskType
from datasets import Dataset

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("qwen36-sft")


# ---------- config ----------

@dataclass
class TrainConfig:
    model_id: str = "nvidia/Qwen/Qwen3.6-27B"
    dataset_path: str = ""
    output_dir: str = "/root/output/qwen36-sft"
    max_samples: int = 0  # 0 = all
    max_length: int = 2048
    streaming: bool = False
    eval_split: float = 0.02
    epochs: int = 1
    batch_size: int = 2
    gradient_accumulation: int = 4
    lr: float = 2e-4
    warmup_steps: int = 100
    save_steps: int = 500
    eval_steps: int = 500
    logging_steps: int = 10
    max_grad_norm: float = 1.0
    lora_r: int = 16
    lora_alpha: int = 32
    lora_dropout: float = 0.05
    target_modules: list[str] = field(default_factory=lambda: [
        "q_proj", "k_proj", "v_proj", "o_proj",
        "up_proj", "down_proj",
    ])
    quant_type: str = "nf4"
    no_double_quant: bool = False
    lr_scheduler: str = "cosine"
    seed: int = 42
    report_to: str = "none"
    run_name: str = "qwen36-sft"
    merge: bool = False
    no_eval: bool = False
    bf16: bool = True


# ---------- model loading ----------

def load_model_4bit(config: TrainConfig):
    """Load model and tokenizer in 4-bit with BitsAndBytes."""
    compute_dtype = torch.bfloat16 if config.bf16 else torch.float16

    bnb_config = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_quant_type=config.quant_type,
        bnb_4bit_compute_dtype=compute_dtype,
        bnb_4bit_use_double_quant=not config.no_double_quant,
        llm_int8_enable_fp32_cpu_offload=True,
    )

    logger.info("Loading tokenizer: %s", config.model_id)
    tokenizer = AutoTokenizer.from_pretrained(config.model_id)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token
        logger.info("Set pad_token = eos_token")

    logger.info("Loading model in 4-bit: %s", config.model_id)
    model = AutoModelForCausalLM.from_pretrained(
        config.model_id,
        quantization_config=bnb_config,
        device_map="auto",
        torch_dtype=compute_dtype,
    )

    logger.info("Model loaded: %.2fB params", sum(p.numel() for p in model.parameters()) / 1e9)
    allocated = torch.cuda.memory_allocated() / 1024**3
    total = torch.cuda.get_device_properties(0).total_memory / 1024**3
    logger.info("VRAM: %.1f GB / %.1f GB", allocated, total)

    return model, tokenizer


def apply_lora(model, config: TrainConfig):
    """Apply QLoRA to the model."""
    logger.info("Preparing model for k-bit training...")
    model = prepare_model_for_kbit_training(model)

    lora_config = LoraConfig(
        r=config.lora_r,
        lora_alpha=config.lora_alpha,
        lora_dropout=config.lora_dropout,
        bias="none",
        task_type=TaskType.CAUSAL_LM,
        target_modules=config.target_modules,
    )

    logger.info("Applying LoRA with targets: %s", config.target_modules)
    model = get_peft_model(model, lora_config)

    trainable = sum(p.numel() for p in model.parameters() if p.requires_grad)
    total = sum(p.numel() for p in model.parameters())
    logger.info("Trainable: %.2fM / %.2fB (%.2f%%)",
                trainable / 1e6, total / 1e9, 100 * trainable / total)

    return model


# ---------- data ----------

def load_dataset_sft(config: TrainConfig, tokenizer):
    """Load and tokenize the SFT dataset from JSONL with varied schema."""
    logger.info("Loading dataset: %s", config.dataset_path)

    # Load JSONL manually (avoids datasets schema inference issues with varied fields)
    raw_data = []
    with open(config.dataset_path, encoding="utf-8") as f:
        for i, line in enumerate(f):
            if config.max_samples > 0 and i >= config.max_samples:
                break
            line = line.strip()
            if line:
                raw_data.append(json.loads(line))

    logger.info("Loaded %d examples from JSONL", len(raw_data))

    # Extract messages and build text
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

    logger.info("Tokenizing %d texts (max_length=%d)...", len(texts), config.max_length)
    tokenized = tokenizer(
        texts,
        truncation=True,
        max_length=config.max_length,
        padding=False,  # Use dynamic padding via data collator
    )

    # Build HuggingFace Dataset from tokenized dict
    dataset_dict = {
        "input_ids": tokenized["input_ids"],
        "attention_mask": tokenized["attention_mask"],
        "labels": [ids.copy() for ids in tokenized["input_ids"]],
    }
    dataset = Dataset.from_dict(dataset_dict)

    logger.info("Tokenized dataset: %d examples", len(dataset))

    if config.eval_split > 0:
        split = dataset.train_test_split(
            test_size=config.eval_split, seed=config.seed
        )
        return split["train"], split["test"]
    return dataset, None


# ---------- training ----------

def train(config: TrainConfig):
    """Main training routine."""
    torch.manual_seed(config.seed)

    # 1. Load model + tokenizer
    model, tokenizer = load_model_4bit(config)

    # 2. Apply LoRA
    model = apply_lora(model, config)

    # 3. Load dataset
    train_ds, eval_ds = load_dataset_sft(config, tokenizer)

    # 4. Training args
    effective_batch = config.batch_size * config.gradient_accumulation
    total_steps = (len(train_ds) * config.epochs) // effective_batch

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
        bf16=config.bf16,
        fp16=not config.bf16,
        optim="paged_adamw_8bit",
        seed=config.seed,
        report_to=config.report_to if config.report_to != "none" else "none",
        run_name=config.run_name,
        save_total_limit=3,
        load_best_model_at_end=bool(eval_ds),
        metric_for_best_model="eval_loss" if eval_ds else None,
        ddp_find_unused_parameters=False,
        dataloader_num_workers=2,
        remove_unused_columns=False,
    )

    if config.report_to == "none":
        training_args.report_to = []

    logger.info("Training config:")
    logger.info("  Epochs: %d  Batch: %d  GradAcc: %d  Effective: %d",
                config.epochs, config.batch_size, config.gradient_accumulation, effective_batch)
    logger.info("  LR: %.2e  LoRA r: %d  alpha: %d",
                config.lr, config.lora_r, config.lora_alpha)
    logger.info("  Total steps (est): %d  Warmup: %d", total_steps, config.warmup_steps)

    # 5. Train
    from transformers import Trainer

    # Enable gradient checkpointing to save memory
    model.gradient_checkpointing_enable()

    # Data collator for dynamic padding
    data_collator = DataCollatorForSeq2Seq(
        tokenizer=tokenizer,
        model=model,
        padding=True,
    )

    trainer = Trainer(
        model=model,
        args=training_args,
        train_dataset=train_ds,
        eval_dataset=eval_ds,
        processing_class=tokenizer,
        data_collator=data_collator,
    )

    logger.info("Starting training...")
    start = time.time()
    trainer.train()
    elapsed = time.time() - start
    logger.info("Training completed in %.1f min (%.1f h)", elapsed / 60, elapsed / 3600)

    # 6. Save final
    final_dir = output_dir / "final"
    trainer.save_model(str(final_dir))
    tokenizer.save_pretrained(str(final_dir))
    logger.info("Final adapter saved to %s", final_dir)

    # 7. Optional: merge
    if config.merge:
        logger.info("Merging LoRA weights...")
        merged = model.merge_and_unload()
        merged_dir = output_dir / "merged"
        merged.save_pretrained(str(merged_dir))
        tokenizer.save_pretrained(str(merged_dir))
        logger.info("Merged model saved to %s", merged_dir)

    return str(final_dir)


# ---------- CLI ----------

def main():
    parser = argparse.ArgumentParser(description="Qwen 3.6 QLoRA SFT")
    parser.add_argument("--model", default="nvidia/Qwen/Qwen3.6-27B")
    parser.add_argument("--dataset", required=True)
    parser.add_argument("--output-dir", default="/root/output/qwen36-sft")
    parser.add_argument("--max-samples", type=int, default=0)
    parser.add_argument("--max-length", type=int, default=2048)
    parser.add_argument("--streaming", action="store_true")
    parser.add_argument("--eval-split", type=float, default=0.02)
    parser.add_argument("--epochs", type=int, default=1)
    parser.add_argument("--batch-size", type=int, default=2)
    parser.add_argument("--gradient-accumulation", type=int, default=4)
    parser.add_argument("--lr", type=float, default=2e-4)
    parser.add_argument("--warmup-steps", type=int, default=100)
    parser.add_argument("--save-steps", type=int, default=500)
    parser.add_argument("--eval-steps", type=int, default=500)
    parser.add_argument("--logging-steps", type=int, default=10)
    parser.add_argument("--max-grad-norm", type=float, default=1.0)
    parser.add_argument("--lora-r", type=int, default=16)
    parser.add_argument("--lora-alpha", type=int, default=32)
    parser.add_argument("--lora-dropout", type=float, default=0.05)
    parser.add_argument("--target-modules", nargs="*", default=[
        "q_proj", "k_proj", "v_proj", "o_proj", "up_proj", "down_proj",
    ])
    parser.add_argument("--lr-scheduler", default="cosine")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--report-to", default="none")
    parser.add_argument("--run-name", default="qwen36-sft")
    parser.add_argument("--merge", action="store_true")
    parser.add_argument("--no-eval", action="store_true")
    parser.add_argument("--quant-type", default="nf4")
    parser.add_argument("--no-double-quant", action="store_true")
    parser.add_argument("--no-bf16", action="store_true")

    args = parser.parse_args()

    cfg = TrainConfig(
        model_id=args.model,
        dataset_path=args.dataset,
        output_dir=args.output_dir,
        max_samples=args.max_samples,
        max_length=args.max_length,
        streaming=args.streaming,
        eval_split=0.0 if args.no_eval else args.eval_split,
        epochs=args.epochs,
        batch_size=args.batch_size,
        gradient_accumulation=args.gradient_accumulation,
        lr=args.lr,
        warmup_steps=args.warmup_steps,
        save_steps=args.save_steps,
        eval_steps=args.eval_steps,
        logging_steps=args.logging_steps,
        max_grad_norm=args.max_grad_norm,
        lora_r=args.lora_r,
        lora_alpha=args.lora_alpha,
        lora_dropout=args.lora_dropout,
        target_modules=args.target_modules,
        quant_type=args.quant_type,
        no_double_quant=args.no_double_quant,
        lr_scheduler=args.lr_scheduler,
        seed=args.seed,
        report_to=args.report_to,
        run_name=args.run_name,
        merge=args.merge,
        no_eval=args.no_eval,
        bf16=not args.no_bf16,
    )

    output = train(cfg)
    print(f"\nDone! Adapter saved to: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
