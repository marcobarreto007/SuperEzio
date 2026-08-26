#!/usr/bin/env python3
"""LoRA training on cloud A100 using PEFT + transformers."""

import json
from dataclasses import dataclass

import torch
from datasets import Dataset
from peft import LoraConfig, TaskType, get_peft_model
from transformers import (
    AutoModelForCausalLM,
    AutoTokenizer,
    Trainer,
    TrainingArguments,
)


@dataclass
class Config:
    model_name: str = "Qwen/Qwen2.5-14B"
    data_path: str = "/root/train_finance_10k.jsonl"
    output_dir: str = "/root/lora_f51_v9"
    rank: int = 16
    alpha: int = 32
    target_modules: list[str] = None
    max_length: int = 512
    per_device_train_batch_size: int = 4
    gradient_accumulation_steps: int = 4
    num_epochs: int = 2
    learning_rate: float = 1e-4
    warmup_steps: int = 100

    def __post_init__(self):
        if self.target_modules is None:
            self.target_modules = [
                "q_proj",
                "v_proj",
                "k_proj",
                "o_proj",
                "gate_proj",
                "up_proj",
                "down_proj",
            ]


def load_jsonl(path: str) -> list[dict]:
    with open(path, "r", encoding="utf-8") as f:
        return [json.loads(line) for line in f]


def format_conversation(example: dict) -> str:
    """Format conversation for Qwen chat format."""
    messages = example["messages"]
    text = ""
    for msg in messages:
        role = msg["role"]
        content = msg["content"]
        if role == "system":
            text += f"<|im_start|>system\n{content}<|im_end|>\n"
        elif role == "user":
            text += f"<|im_start|>user\n{content}<|im_end|>\n"
        elif role == "assistant":
            text += f"<|im_start|>assistant\n{content}<|im_end|>\n"
    return text + "<|im_start|>assistant\n"


def main():
    config = Config()
    print(f"Config: {config}")

    # Load data
    print("Loading dataset...")
    data = load_jsonl(config.data_path)
    texts = [format_conversation(ex) for ex in data]

    # Load tokenizer
    print("Loading tokenizer...")
    tokenizer = AutoTokenizer.from_pretrained(config.model_name, trust_remote_code=True)
    tokenizer.pad_token = tokenizer.eos_token

    # Tokenize
    print("Tokenizing...")
    encodings = tokenizer(
        texts,
        max_length=config.max_length,
        truncation=True,
        padding=True,
        return_tensors="pt",
    )

    # Create dataset
    dataset = Dataset.from_dict(
        {
            "input_ids": encodings["input_ids"],
            "attention_mask": encodings["attention_mask"],
            "labels": encodings["input_ids"].clone(),
        }
    )

    # Load model
    print(f"Loading model {config.model_name}...")
    model = AutoModelForCausalLM.from_pretrained(
        config.model_name,
        torch_dtype=torch.float16,
        device_map="auto",
        trust_remote_code=True,
    )

    # Configure LoRA
    lora_config = LoraConfig(
        r=config.rank,
        lora_alpha=config.alpha,
        target_modules=config.target_modules,
        lora_dropout=0.05,
        bias="none",
        task_type=TaskType.CAUSAL_LM,
    )

    print("Applying LoRA...")
    model = get_peft_model(model, lora_config)
    model.print_trainable_parameters()

    # Training
    training_args = TrainingArguments(
        output_dir=config.output_dir,
        num_train_epochs=config.num_epochs,
        per_device_train_batch_size=config.per_device_train_batch_size,
        gradient_accumulation_steps=config.gradient_accumulation_steps,
        learning_rate=config.learning_rate,
        warmup_steps=config.warmup_steps,
        logging_steps=10,
        save_steps=100,
        save_total_limit=3,
        fp16=True,
        gradient_checkpointing=True,
        optim="adamw_torch",
        ddp_find_unused_parameters=False,
        report_to="none",
    )

    trainer = Trainer(
        model=model,
        args=training_args,
        train_dataset=dataset,
    )

    print("Starting training...")
    trainer.train()

    print(f"Saving LoRA adapter to {config.output_dir}...")
    model.save_pretrained(config.output_dir)
    tokenizer.save_pretrained(config.output_dir)

    print("Training complete!")


if __name__ == "__main__":
    main()
