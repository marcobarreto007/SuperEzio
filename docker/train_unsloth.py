"""F51 Training Script — Unsloth + Qwen 2.5 1.5B → LoRA → GGUF."""

import os

from datasets import load_dataset
from transformers import TrainingArguments
from trl import SFTTrainer
from unsloth import FastLanguageModel

MODEL_NAME = "unsloth/Qwen2.5-1.5B-Instruct"
DATA_PATH = os.getenv("F51_DATA", "/workspace/datasets/f51_train.jsonl")
OUTPUT_DIR = "/workspace/outputs/f51-lora"
GGUF_DIR = "/workspace/outputs/f51-gguf"
max_seq_length = 2048

print(f"[F51] Loading model: {MODEL_NAME}")
model, tokenizer = FastLanguageModel.from_pretrained(
    model_name=MODEL_NAME,
    max_seq_length=max_seq_length,
    load_in_4bit=True,
)

model = FastLanguageModel.get_peft_model(
    model,
    r=16,
    lora_alpha=16,
    lora_dropout=0,
    bias="none",
    use_gradient_checkpointing="unsloth",
    random_state=51,
)

print(f"[F51] Loading dataset: {DATA_PATH}")
dataset = load_dataset("json", data_files=DATA_PATH, split="train")


def format_example(example):
    instruction = example.get("instruction", "")
    input_text = example.get("input", "")
    output = example.get("output", "")
    if input_text:
        prompt = f"### Instruction:\n{instruction}\n\n### Input:\n{input_text}\n\n### Response:\n{output}"
    else:
        prompt = f"### Instruction:\n{instruction}\n\n### Response:\n{output}"
    return {"text": prompt}


dataset = dataset.map(format_example)
print(f"[F51] Dataset: {len(dataset)} examples")

trainer = SFTTrainer(
    model=model,
    tokenizer=tokenizer,
    train_dataset=dataset,
    dataset_text_field="text",
    max_seq_length=max_seq_length,
    args=TrainingArguments(
        per_device_train_batch_size=2,
        gradient_accumulation_steps=4,
        warmup_steps=10,
        max_steps=100,
        learning_rate=2e-4,
        fp16=True,
        logging_steps=5,
        output_dir=OUTPUT_DIR,
        save_steps=50,
        save_total_limit=2,
        optim="adamw_8bit",
        report_to="none",
    ),
)

print("[F51] Training...")
trainer.train()

print("[F51] Saving LoRA...")
model.save_pretrained(OUTPUT_DIR)
tokenizer.save_pretrained(OUTPUT_DIR)

print("[F51] Merging 16bit...")
model.save_pretrained_merged("/workspace/outputs/f51-merged", tokenizer, save_method="merged_16bit")

print("[F51] Exporting GGUF (Q4_K_M)...")
model.save_pretrained_gguf(GGUF_DIR, tokenizer, quantization_method="q4_k_m")

print("[F51] DONE — check /workspace/outputs/f51-gguf/")
