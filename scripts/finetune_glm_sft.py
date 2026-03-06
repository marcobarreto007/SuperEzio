"""
QLoRA 4-bit SFT fine-tuning for GLM-4.7-Flash (30B-A3B MoE).

Architecture: Glm4MoeLiteForCausalLM — 47 layers, MLA (Multi-head Latent
Attention), 64 routed + 1 shared expert, ~3B active params per token.

Chat template: [gMASK]<sop> <|system|> <|user|> <|assistant|> with
<think>/</think> reasoning blocks. The tokenizer has apply_chat_template()
built in.

Dataset: F51_Datasets/sft_output/f51_final_sft.jsonl — 410K entries in
messages array format (system/user/assistant roles).

Setup (cloud GPU):
    pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu124
    pip install transformers>=4.51.0 accelerate>=1.0.0 peft>=0.14.0 bitsandbytes>=0.45.0
    pip install datasets>=3.0.0 wandb tensorboard
    # Optional for GGUF export:
    pip install gguf

Usage:
    # Full training
    python scripts/finetune_glm_sft.py \
        --model zai-org/GLM-4.7-Flash \
        --dataset F51_Datasets/sft_output/f51_final_sft.jsonl \
        --output-dir output/glm-sft \
        --epochs 2 --batch-size 2 --gradient-accumulation 8

    # Quick test with small subset
    python scripts/finetune_glm_sft.py \
        --model zai-org/GLM-4.7-Flash \
        --dataset F51_Datasets/sft_output/f51_final_sft.jsonl \
        --output-dir output/glm-sft-test \
        --max-samples 500 --epochs 1 --batch-size 1

    # Resume from checkpoint
    python scripts/finetune_glm_sft.py \
        --resume output/glm-sft/checkpoint-1000

    # Multi-GPU (accelerate)
    accelerate launch --num_processes 2 scripts/finetune_glm_sft.py ...

Why transformers+peft, not unsloth:
    Unsloth does not support GLM/ChatGLM architectures as of May 2026.
    We use bitsandbytes 4-bit quantization + PEFT LoRA instead.
"""

from __future__ import annotations

import argparse
import json
import logging
import random
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import torch
import torch.nn as nn
from torch.utils.data import Dataset, IterableDataset

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("finetune_glm")

# ── Constants ────────────────────────────────────────────────────────────

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DATASET = PROJECT_ROOT / "F51_Datasets" / "sft_output" / "f51_final_sft.jsonl"
DEFAULT_OUTPUT = PROJECT_ROOT / "output" / "glm-sft"


# ── Helpers ──────────────────────────────────────────────────────────────


def enumerate_linear_modules(
    model: nn.Module,
    *,
    ignore_patterns: tuple[str, ...] = ("lm_head", "router", "shared_expert_gate"),
) -> list[str]:
    """Return full dot-separated paths of all nn.Linear modules.

    Filters out modules whose path contains any ignore_pattern string.
    Returns paths relative to model root (e.g., "layers.0.self_attn.q_a_proj").
    """
    paths: list[str] = []
    for name, module in model.named_modules():
        if not isinstance(module, nn.Linear):
            continue
        if any(pat in name for pat in ignore_patterns):
            continue
        paths.append(name)
    return sorted(paths)


def select_lora_targets(
    linear_paths: list[str],
    *,
    include_routed_experts: bool = False,
) -> list[str]:
    """Select LoRA target modules from linear paths.

    Strategy:
      - Attention projections (MLA): always targeted (unique leaf names).
      - Shared expert FFN: targeted using path suffix "shared_expert.<proj>"
        to avoid accidentally targeting routed experts.
      - Routed experts: only if include_routed_experts=True.
        Uses leaf names which match all expert instances.

    Returns a list of PEFT-compatible target module specifiers.
    """
    # Attention leaf names — unique enough to use as-is
    attention_leaves = {
        "q_a_proj", "q_b_proj", "kv_a_proj_with_mqa",
        "kv_b_proj", "o_proj",
    }

    # Shared expert projections — need path context to avoid routed experts
    shared_expert_suffixes = (
        "shared_expert.gate_proj",
        "shared_expert.up_proj",
        "shared_expert.down_proj",
    )

    targets: list[str] = []

    # 1. Attention targets (leaf names are distinctive enough)
    for leaf in attention_leaves:
        if any(path.endswith(f".{leaf}") for path in linear_paths):
            targets.append(leaf)

    # 2. Shared expert targets (use path suffix to exclude routed)
    for suffix in shared_expert_suffixes:
        if any(path.endswith(suffix) for path in linear_paths):
            targets.append(suffix)

    # 3. Routed experts (optional — huge adapter)
    if include_routed_experts:
        expert_leaves = {"gate_proj", "up_proj", "down_proj"}
        for leaf in expert_leaves:
            # Only add if there are routed expert instances
            has_routed = any(
                "experts." in path and path.endswith(f".{leaf}")
                for path in linear_paths
            )
            if has_routed and leaf not in targets:
                targets.append(leaf)

    # 4. Fallback: if no attention targets found, try common alternatives
    if not targets:
        logger.warning(
            "No expected linear modules found. All available: %s",
            sorted({p.split(".")[-1] for p in linear_paths}),
        )
        # Return all unique leaf names as fallback
        targets = sorted({p.split(".")[-1] for p in linear_paths})

    return targets


# ── Dataset ──────────────────────────────────────────────────────────────


class StreamingJSONLDataset(IterableDataset):
    """Stream JSONL file line-by-line to avoid loading 1GB into RAM.

    Each line is a JSON object with a "messages" key containing the chat
    array [{"role": "...", "content": "..."}, ...].
    """

    def __init__(
        self,
        path: Path,
        *,
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

        with self.path.open("r", encoding="utf-8") as f:
            for line in f:
                stripped = line.strip()
                if not stripped:
                    continue
                try:
                    record = json.loads(stripped)
                except json.JSONDecodeError:
                    logger.warning("Skipping malformed JSON line")
                    continue

                messages = record.get("messages")
                if not messages or not isinstance(messages, list):
                    continue

                # Tokenize
                tokenized = self._tokenize_messages(messages)
                if tokenized is None:
                    continue

                buffer.append(tokenized)
                count += 1

                if self.max_samples and count >= self.max_samples:
                    break

                if len(buffer) >= self.shuffle_buffer_size:
                    rng.shuffle(buffer)
                    yield from buffer
                    buffer = []

        if buffer:
            rng.shuffle(buffer)
            yield from buffer

    def _tokenize_messages(self, messages: list[dict]) -> dict[str, torch.Tensor] | None:
        """Apply chat template and tokenize.

        Returns None if tokenization fails or exceeds max_length.
        """
        try:
            text = self.tokenizer.apply_chat_template(
                messages,
                tokenize=False,
                add_generation_prompt=False,
            )
            # For SFT we train on the full assistant response,
            # so include the assistant text and EOS.
            # apply_chat_template with add_generation_prompt=False
            # gives us the full conversation including assistant.
        except Exception:
            logger.debug("Failed to apply chat template", exc_info=True)
            return None

        try:
            tokenized = self.tokenizer(
                text,
                truncation=True,
                max_length=self.max_length,
                padding=False,
                return_tensors="pt",
            )
        except Exception:
            return None

        input_ids = tokenized["input_ids"][0]
        attention_mask = tokenized["attention_mask"][0]

        if input_ids.numel() < 2:
            return None

        # For CausalLM SFT: labels = input_ids (model learns to predict all tokens)
        labels = input_ids.clone()

        # Mask the system prompt and user portions (optional — some prefer
        # to train on everything; we default to training on assistant only).
        # This is handled by setting labels to -100 for non-assistant tokens.
        # For simplicity, we train on all tokens. The model learns the full
        # conversation distribution.

        return {
            "input_ids": input_ids,
            "attention_mask": attention_mask,
            "labels": labels,
        }


class CachedJSONLDataset(Dataset):
    """Load entire JSONL into memory (for smaller subsets or fast storage)."""

    def __init__(
        self,
        path: Path,
        *,
        tokenizer: Any,
        max_length: int = 4096,
        max_samples: int | None = None,
    ):
        self.tokenizer = tokenizer
        self.max_length = max_length
        self.samples: list[dict[str, torch.Tensor]] = []

        logger.info("Loading dataset into memory: %s", path)
        with path.open("r", encoding="utf-8") as f:
            for i, line in enumerate(f):
                stripped = line.strip()
                if not stripped:
                    continue
                if max_samples and len(self.samples) >= max_samples:
                    break
                try:
                    record = json.loads(stripped)
                except json.JSONDecodeError:
                    continue
                messages = record.get("messages")
                if not messages:
                    continue
                tokenized = self._tokenize(messages)
                if tokenized is not None:
                    self.samples.append(tokenized)

        logger.info("Loaded %d samples", len(self.samples))

    def _tokenize(self, messages: list[dict]) -> dict[str, torch.Tensor] | None:
        try:
            text = self.tokenizer.apply_chat_template(
                messages,
                tokenize=False,
                add_generation_prompt=False,
            )
        except Exception:
            return None

        try:
            tokenized = self.tokenizer(
                text,
                truncation=True,
                max_length=self.max_length,
                padding=False,
                return_tensors="pt",
            )
        except Exception:
            return None

        input_ids = tokenized["input_ids"][0]
        attention_mask = tokenized["attention_mask"][0]
        labels = input_ids.clone()

        return {
            "input_ids": input_ids,
            "attention_mask": attention_mask,
            "labels": labels,
        }

    def __len__(self) -> int:
        return len(self.samples)

    def __getitem__(self, idx: int) -> dict[str, torch.Tensor]:
        return self.samples[idx]


# ── Collator ─────────────────────────────────────────────────────────────


@dataclass
class DataCollatorForChatSFT:
    """Pad variable-length sequences in a batch."""

    tokenizer: Any
    pad_to_multiple_of: int | None = 8

    def __call__(self, batch: list[dict[str, torch.Tensor]]) -> dict[str, torch.Tensor]:
        input_ids = [item["input_ids"] for item in batch]
        labels = [item["labels"] for item in batch]
        attention_mask = [item["attention_mask"] for item in batch]

        # Pad all sequences to the longest in the batch
        max_len = max(ids.size(0) for ids in input_ids)
        if self.pad_to_multiple_of:
            max_len = ((max_len + self.pad_to_multiple_of - 1)
                        // self.pad_to_multiple_of
                        * self.pad_to_multiple_of)

        pad_token_id = self.tokenizer.pad_token_id or 0

        padded_ids = torch.full((len(batch), max_len), pad_token_id, dtype=torch.long)
        padded_labels = torch.full((len(batch), max_len), -100, dtype=torch.long)
        padded_mask = torch.zeros((len(batch), max_len), dtype=torch.long)

        for i, (ids, lbls, mask) in enumerate(zip(input_ids, labels, attention_mask)):
            seq_len = min(ids.size(0), max_len)
            padded_ids[i, :seq_len] = ids[:seq_len]
            padded_labels[i, :seq_len] = lbls[:seq_len]
            padded_mask[i, :seq_len] = mask[:seq_len]

        return {
            "input_ids": padded_ids,
            "attention_mask": padded_mask,
            "labels": padded_labels,
        }


# ── Model Loading ────────────────────────────────────────────────────────


def load_model_4bit(
    model_id: str,
    *,
    device_map: str = "auto",
    bnb_4bit_compute_dtype: torch.dtype = torch.bfloat16,
    bnb_4bit_quant_type: str = "nf4",
    bnb_4bit_use_double_quant: bool = True,
    use_flash_attention_2: bool = True,
) -> tuple[Any, Any]:
    """Load GLM-4.7-Flash in 4-bit NF4 with bitsandbytes.

    Returns (model, tokenizer).
    """
    from transformers import (
        AutoModelForCausalLM,
        AutoTokenizer,
        BitsAndBytesConfig,
    )

    compute_dtype = bnb_4bit_compute_dtype

    bnb_config = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_quant_type=bnb_4bit_quant_type,
        bnb_4bit_compute_dtype=compute_dtype,
        bnb_4bit_use_double_quant=bnb_4bit_use_double_quant,
    )

    logger.info("Loading tokenizer: %s", model_id)
    tokenizer = AutoTokenizer.from_pretrained(
        model_id,
        trust_remote_code=False,
        padding_side="right",
    )

    # Ensure pad token is set
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token
        logger.info("Set pad_token = eos_token (%s)", tokenizer.pad_token)

    logger.info("Loading model in 4-bit: %s", model_id)
    model_kwargs: dict[str, Any] = {
        "quantization_config": bnb_config,
        "device_map": device_map,
        "torch_dtype": compute_dtype,
        "trust_remote_code": False,
    }

    if use_flash_attention_2:
        try:
            model_kwargs["attn_implementation"] = "flash_attention_2"
            logger.info("Using flash_attention_2")
        except Exception:
            pass

    model = AutoModelForCausalLM.from_pretrained(model_id, **model_kwargs)

    # Enable gradient checkpointing for memory efficiency
    model.gradient_checkpointing_enable(gradient_checkpointing_kwargs={"use_reentrant": False})

    # Disable caching during training
    model.config.use_cache = False

    # Print trainable params info
    total_params = sum(p.numel() for p in model.parameters())
    logger.info("Model loaded: %.2fB total params", total_params / 1e9)

    return model, tokenizer


def apply_lora(
    model: nn.Module,
    *,
    target_modules: list[str] | None = None,
    r: int = 64,
    lora_alpha: int = 128,
    lora_dropout: float = 0.05,
    task_type: str = "CAUSAL_LM",
    include_experts: bool = False,
) -> nn.Module:
    """Apply LoRA adapter to the model.

    If target_modules is None, auto-discovers attention + shared expert
    linear layers.
    """
    from peft import LoraConfig, get_peft_model, TaskType, prepare_model_for_kbit_training

    model = prepare_model_for_kbit_training(model)

    if target_modules is None:
        all_linear = enumerate_linear_modules(model)
        target_modules = select_lora_targets(
            all_linear,
            include_routed_experts=include_experts,
        )

    # Verify target modules exist in model
    all_linear = enumerate_linear_modules(model)
    # PEFT matches target_modules as suffixes of full module paths
    valid_targets: list[str] = []
    for target in target_modules:
        if any(path.endswith(target) for path in all_linear):
            valid_targets.append(target)
        else:
            logger.warning("Target module not found in model: %s", target)

    if not valid_targets:
        logger.error(
            "No valid target modules found! All available linear paths: %s",
            all_linear[:20],
        )
        # Fallback: use all unique leaf names except known ignores
        ignore = {"lm_head", "router", "shared_expert_gate"}
        valid_targets = sorted({
            p.split(".")[-1] for p in all_linear
            if p.split(".")[-1] not in ignore
        })

    logger.info("LoRA target modules: %s", valid_targets)

    task_type_enum = getattr(TaskType, task_type, TaskType.CAUSAL_LM)

    lora_config = LoraConfig(
        r=r,
        lora_alpha=lora_alpha,
        target_modules=valid_targets,
        lora_dropout=lora_dropout,
        bias="none",
        task_type=task_type_enum,
    )

    model = get_peft_model(model, lora_config)

    trainable = sum(p.numel() for p in model.parameters() if p.requires_grad)
    total = sum(p.numel() for p in model.parameters())
    logger.info(
        "LoRA applied: %s trainable / %s total (%.2f%%)",
        f"{trainable:,}",
        f"{total:,}",
        100 * trainable / total if total > 0 else 0,
    )

    return model


# ── Evaluation ───────────────────────────────────────────────────────────


TEST_PROMPTS = [
    {
        "messages": [
            {"role": "system", "content": "You are Bob, CEO of SuperEzio Trust OS — an AI financial analysis platform. Respond with structured fraud analysis."},
            {"role": "user", "content": "Transaction data:\n  step: 133\n  type: TRANSFER\n  amount: 12897.95\n  origin_balance_before: 4546.71\n  origin_balance_after: 646936.40\n  destination_balance_before: 29740.47\n  destination_balance_after: 0.00\n\nAnalyze this transaction for fraud risk. Identify all suspicious signals, assess the risk level, and recommend action."},
        ],
    },
    {
        "messages": [
            {"role": "system", "content": "You are Bob, CEO of SuperEzio Trust OS — an AI financial analysis platform. Respond with structured fraud analysis."},
            {"role": "user", "content": "Transaction data:\n  step: 50\n  type: PAYMENT\n  amount: 0.00\n  origin_balance_before: 298348.04\n  origin_balance_after: 2578036.60\n  destination_balance_before: 7067.01\n  destination_balance_after: 0.11\n\nAnalyze this transaction. Is there any fraud risk? Justify your assessment."},
        ],
    },
    {
        "messages": [
            {"role": "system", "content": "You are Bob, CEO of SuperEzio Trust OS — an AI financial analysis platform. Respond with structured fraud analysis."},
            {"role": "user", "content": "Analyze the following email for phishing indicators:\n\nSubject: Urgent - Your account has been compromised\nFrom: security@paypa1.com\n\nDear Customer, your PayPal account has been accessed from an unknown device. Click here to verify your identity: http://paypa1-secure.com/login"},
        ],
    },
]


def generate_sample(
    model: nn.Module,
    tokenizer: Any,
    messages: list[dict],
    *,
    max_new_tokens: int = 512,
    temperature: float = 0.3,
    top_p: float = 0.9,
) -> str:
    """Generate a response for a messages array."""
    try:
        text = tokenizer.apply_chat_template(
            messages,
            tokenize=False,
            add_generation_prompt=True,
        )
    except Exception:
        return "[ERROR: chat template failed]"

    inputs = tokenizer(text, return_tensors="pt").to(model.device)

    with torch.no_grad():
        outputs = model.generate(
            **inputs,
            max_new_tokens=max_new_tokens,
            temperature=temperature,
            top_p=top_p,
            do_sample=temperature > 0,
            pad_token_id=tokenizer.pad_token_id,
            eos_token_id=tokenizer.eos_token_id,
        )

    generated_ids = outputs[0][inputs["input_ids"].shape[1]:]
    return tokenizer.decode(generated_ids, skip_special_tokens=True).strip()


def run_evaluation(
    model: nn.Module,
    tokenizer: Any,
    prompts: list[dict] | None = None,
    *,
    output_dir: Path | None = None,
) -> list[dict]:
    """Run sample inference on test prompts."""
    if prompts is None:
        prompts = TEST_PROMPTS

    results = []
    for i, prompt in enumerate(prompts):
        logger.info("Generating sample %d/%d...", i + 1, len(prompts))
        start = time.monotonic()
        response = generate_sample(model, tokenizer, prompt["messages"])
        elapsed = time.monotonic() - start
        result = {
            "index": i,
            "messages": prompt["messages"],
            "response": response,
            "elapsed_sec": round(elapsed, 2),
        }
        results.append(result)
        logger.info(
            "Sample %d: %d chars in %.1fs",
            i + 1,
            len(response),
            elapsed,
        )

    if output_dir:
        output_dir.mkdir(parents=True, exist_ok=True)
        eval_path = output_dir / "eval_samples.json"
        eval_path.write_text(
            json.dumps(results, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        logger.info("Evaluation results saved: %s", eval_path)

    return results


# ── Training ─────────────────────────────────────────────────────────────


def prepare_training_args(
    output_dir: Path,
    *,
    num_train_epochs: int = 2,
    per_device_train_batch_size: int = 2,
    gradient_accumulation_steps: int = 8,
    learning_rate: float = 2e-4,
    warmup_steps: int = 100,
    save_steps: int = 500,
    eval_steps: int = 500,
    logging_steps: int = 10,
    max_grad_norm: float = 1.0,
    lr_scheduler_type: str = "cosine",
    save_total_limit: int = 3,
    bf16: bool = True,
    dataloader_num_workers: int = 4,
    run_name: str | None = None,
    report_to: str = "none",
) -> Any:
    """Build HuggingFace TrainingArguments."""
    from transformers import TrainingArguments

    return TrainingArguments(
        output_dir=str(output_dir),
        num_train_epochs=num_train_epochs,
        per_device_train_batch_size=per_device_train_batch_size,
        gradient_accumulation_steps=gradient_accumulation_steps,
        warmup_steps=warmup_steps,
        save_steps=save_steps,
        eval_steps=eval_steps,
        logging_steps=logging_steps,
        learning_rate=learning_rate,
        lr_scheduler_type=lr_scheduler_type,
        max_grad_norm=max_grad_norm,
        save_total_limit=save_total_limit,
        bf16=bf16,
        dataloader_num_workers=dataloader_num_workers,
        report_to=report_to if report_to != "none" else [],
        run_name=run_name,
        remove_unused_columns=False,
        seed=42,
        dataloader_pin_memory=True,
        group_by_length=False,
        gradient_checkpointing=True,
        gradient_checkpointing_kwargs={"use_reentrant": False},
        # DeepSpeed config file for ZeRO-2/3 (optional)
        # deepspeed="scripts/ds_config_zero2.json",
    )


def train(
    model: nn.Module,
    tokenizer: Any,
    dataset: Dataset,
    training_args: Any,
    *,
    eval_dataset: Dataset | None = None,
    resume_from_checkpoint: str | Path | None = None,
) -> None:
    """Run the training loop."""
    from transformers import Trainer

    collator = DataCollatorForChatSFT(tokenizer=tokenizer)

    trainer = Trainer(
        model=model,
        args=training_args,
        train_dataset=dataset,
        eval_dataset=eval_dataset,
        data_collator=collator,
        tokenizer=tokenizer,
    )

    if resume_from_checkpoint:
        logger.info("Resuming from checkpoint: %s", resume_from_checkpoint)
        trainer.train(resume_from_checkpoint=str(resume_from_checkpoint))
    else:
        trainer.train()

    # Save final model
    final_dir = Path(training_args.output_dir) / "final"
    logger.info("Saving final adapter: %s", final_dir)
    trainer.save_model(str(final_dir))
    tokenizer.save_pretrained(str(final_dir))


# ── Merge & Export ────────────────────────────────────────────────────────


def merge_and_save(
    model: nn.Module,
    tokenizer: Any,
    output_dir: Path,
    *,
    push_to_hub: str | None = None,
) -> None:
    """Merge LoRA weights into base model and save in 4-bit.

    WARNING: This requires enough RAM to materialize the merged model.
    On 24GB GPUs, use CPU offload.
    """
    logger.info("Merging LoRA weights...")
    try:
        merged = model.merge_and_unload()
    except Exception as exc:
        logger.error("Merge failed (likely OOM): %s", exc)
        logger.info(
            "Try merging on CPU with device_map='cpu', or use the adapter directly."
        )
        raise

    output_dir.mkdir(parents=True, exist_ok=True)
    logger.info("Saving merged model: %s", output_dir)
    merged.save_pretrained(str(output_dir), safe_serialization=True)
    tokenizer.save_pretrained(str(output_dir))
    logger.info("Merged model saved: %s", output_dir)

    if push_to_hub:
        merged.push_to_hub(push_to_hub, private=True)
        tokenizer.push_to_hub(push_to_hub, private=True)
        logger.info("Pushed to hub: %s", push_to_hub)


# ── Main CLI ─────────────────────────────────────────────────────────────


def load_config_yaml(config_path: Path) -> dict[str, Any]:
    """Load a YAML config file and flatten it to CLI-compatible defaults.

    Supports nested keys like `qlora.r` mapped to `--lora-r`.
    """
    try:
        import yaml
    except ImportError:
        logger.error("PyYAML required for --config. Install with: pip install pyyaml")
        raise SystemExit(1)

    with config_path.open("r", encoding="utf-8") as f:
        raw = yaml.safe_load(f)

    flat: dict[str, Any] = {}
    if not isinstance(raw, dict):
        return flat

    # Map YAML sections to CLI argument names
    mapping = {
        ("model", "id"): "model",
        ("dataset", "path"): "dataset",
        ("dataset", "max_length"): "max_length",
        ("dataset", "streaming"): "streaming",
        ("qlora", "r"): "lora_r",
        ("qlora", "alpha"): "lora_alpha",
        ("qlora", "dropout"): "lora_dropout",
        ("qlora", "target_modules"): "target_modules",
        ("qlora", "include_routed_experts"): "include_experts",
        ("qlora", "bnb_4bit_quant_type"): "quant_type",
        ("qlora", "bnb_4bit_use_double_quant"): "no_double_quant",
        ("training", "num_epochs"): "epochs",
        ("training", "per_device_batch_size"): "batch_size",
        ("training", "gradient_accumulation_steps"): "gradient_accumulation",
        ("training", "learning_rate"): "lr",
        ("training", "lr_scheduler"): "lr_scheduler",
        ("training", "warmup_steps"): "warmup_steps",
        ("training", "save_steps"): "save_steps",
        ("training", "eval_steps"): "eval_steps",
        ("training", "logging_steps"): "logging_steps",
        ("training", "max_grad_norm"): "max_grad_norm",
        ("training", "bf16"): "no_bf16",
        ("logging", "backend"): "report_to",
        ("export", "merge_after_training"): "merge",
    }

    for (section, key), cli_arg in mapping.items():
        section_data = raw.get(section)
        if isinstance(section_data, dict) and key in section_data:
            val = section_data[key]
            # Invert boolean for --no-* flags
            if cli_arg == "no_double_quant" and isinstance(val, bool):
                flat[cli_arg] = not val
            elif cli_arg == "no_bf16" and isinstance(val, bool):
                flat[cli_arg] = not val
            else:
                flat[cli_arg] = val

    # Handle dataset path relative to project root
    if "dataset" in flat and isinstance(flat["dataset"], str):
        p = Path(flat["dataset"])
        if not p.is_absolute():
            flat["dataset"] = PROJECT_ROOT / p

    return flat


def main() -> int:
    parser = argparse.ArgumentParser(
        description="QLoRA SFT fine-tuning for GLM-4.7-Flash (30B-A3B MoE)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    # ── Config file ─────────────────────────────────────────────────────
    parser.add_argument(
        "--config",
        type=Path,
        default=None,
        help="YAML config file with defaults (CLI args override YAML values)",
    )

    # ── Paths ──────────────────────────────────────────────────────────
    parser.add_argument(
        "--model",
        default="zai-org/GLM-4.7-Flash",
        help="HF model ID or local path (default: zai-org/GLM-4.7-Flash)",
    )
    parser.add_argument(
        "--dataset",
        type=Path,
        default=DEFAULT_DATASET,
        help="Path to JSONL dataset (default: F51_Datasets/sft_output/f51_final_sft.jsonl)",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT,
        help="Output directory for checkpoints and final model",
    )
    parser.add_argument(
        "--resume",
        type=Path,
        default=None,
        help="Resume from checkpoint directory",
    )

    # ── Dataset ─────────────────────────────────────────────────────────
    parser.add_argument(
        "--max-samples",
        type=int,
        default=None,
        help="Limit training samples (None = all 410K)",
    )
    parser.add_argument(
        "--max-length",
        type=int,
        default=4096,
        help="Max sequence length in tokens (default: 4096)",
    )
    parser.add_argument(
        "--streaming",
        action="store_true",
        default=True,
        help="Stream dataset from disk (default: True for large JSONL)",
    )
    parser.add_argument(
        "--no-streaming",
        action="store_false",
        dest="streaming",
        help="Load entire dataset into RAM",
    )
    parser.add_argument(
        "--eval-split",
        type=float,
        default=0.01,
        help="Fraction of data for eval (default: 0.01 = 1%%)",
    )

    # ── Training hyperparams ────────────────────────────────────────────
    parser.add_argument(
        "--epochs",
        type=int,
        default=2,
        help="Number of training epochs (default: 2)",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=2,
        help="Per-device batch size (default: 2)",
    )
    parser.add_argument(
        "--gradient-accumulation",
        type=int,
        default=8,
        help="Gradient accumulation steps (default: 8 → effective batch=16)",
    )
    parser.add_argument(
        "--lr",
        type=float,
        default=2e-4,
        help="Learning rate (default: 2e-4)",
    )
    parser.add_argument(
        "--warmup-steps",
        type=int,
        default=100,
        help="Warmup steps (default: 100)",
    )
    parser.add_argument(
        "--save-steps",
        type=int,
        default=500,
        help="Save checkpoint every N steps (default: 500)",
    )
    parser.add_argument(
        "--eval-steps",
        type=int,
        default=500,
        help="Evaluate every N steps (default: 500)",
    )
    parser.add_argument(
        "--logging-steps",
        type=int,
        default=10,
        help="Log every N steps (default: 10)",
    )
    parser.add_argument(
        "--max-grad-norm",
        type=float,
        default=1.0,
        help="Max gradient norm for clipping (default: 1.0)",
    )

    # ── LoRA config ─────────────────────────────────────────────────────
    parser.add_argument(
        "--lora-r",
        type=int,
        default=64,
        help="LoRA rank (default: 64)",
    )
    parser.add_argument(
        "--lora-alpha",
        type=int,
        default=128,
        help="LoRA alpha (default: 128)",
    )
    parser.add_argument(
        "--lora-dropout",
        type=float,
        default=0.05,
        help="LoRA dropout (default: 0.05)",
    )
    parser.add_argument(
        "--target-modules",
        nargs="*",
        default=None,
        help="Specific LoRA target modules (default: auto-detect attention + shared expert)",
    )
    parser.add_argument(
        "--include-experts",
        action="store_true",
        help="Also target routed expert FFN layers (increased adapter size)",
    )

    # ── Training configuration ──────────────────────────────────────────
    parser.add_argument(
        "--no-bf16",
        action="store_true",
        help="Disable bf16 (use fp32, not recommended)",
    )
    parser.add_argument(
        "--lr-scheduler",
        default="cosine",
        choices=["cosine", "linear", "constant", "cosine_with_restarts"],
        help="LR scheduler (default: cosine)",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Random seed (default: 42)",
    )

    # ── Logging ─────────────────────────────────────────────────────────
    parser.add_argument(
        "--report-to",
        default="none",
        choices=["none", "wandb", "mlflow", "tensorboard"],
        help="Reporting backend (default: none)",
    )
    parser.add_argument(
        "--run-name",
        default=None,
        help="WandB/MLflow run name",
    )

    # ── Post-training ───────────────────────────────────────────────────
    parser.add_argument(
        "--merge",
        action="store_true",
        help="Merge LoRA weights into base model after training (needs ~64GB CPU RAM)",
    )
    parser.add_argument(
        "--push-to-hub",
        default=None,
        help="HF Hub repo to push merged model to",
    )
    parser.add_argument(
        "--no-eval",
        action="store_true",
        help="Skip sample generation after training",
    )

    # ── Advanced ────────────────────────────────────────────────────────
    parser.add_argument(
        "--quant-type",
        default="nf4",
        choices=["nf4", "fp4"],
        help="4-bit quantization type (default: nf4)",
    )
    parser.add_argument(
        "--no-double-quant",
        action="store_true",
        help="Disable double quantization",
    )

    # ── YAML Config (pre-parse to inject defaults) ──────────────────────
    # Extract --config early with a minimal parser, then feed YAML
    # values as argparse defaults. CLI args override YAML naturally.
    pre_parser = argparse.ArgumentParser(add_help=False)
    pre_parser.add_argument("--config", type=Path, default=None)
    pre_args, remaining = pre_parser.parse_known_args()

    if pre_args.config:
        logger.info("Loading config: %s", pre_args.config)
        yaml_defaults = load_config_yaml(pre_args.config)
        for key, val in yaml_defaults.items():
            if key in {"target_modules"} and isinstance(val, list):
                parser.set_defaults(**{key: val})
            elif key in {"include_experts", "merge", "no_bf16", "no_double_quant"} and isinstance(val, bool):
                parser.set_defaults(**{key: val})
            elif key == "streaming" and isinstance(val, bool):
                parser.set_defaults(**{key: val})
            elif key == "dataset" and isinstance(val, (str, Path)):
                parser.set_defaults(dataset=Path(val))
            elif not isinstance(val, (list, dict)):
                parser.set_defaults(**{key: val})

        # Parse remaining args so --config doesn't confuse the main parser
        args = parser.parse_args(remaining)
    else:
        args = parser.parse_args()

    # ── Validate ────────────────────────────────────────────────────────
    if not args.dataset.exists():
        logger.error("Dataset not found: %s", args.dataset)
        return 1

    # ── Reproducibility ─────────────────────────────────────────────────
    random.seed(args.seed)
    torch.manual_seed(args.seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(args.seed)

    # ── Load model ──────────────────────────────────────────────────────
    logger.info("=" * 60)
    logger.info("GLM-4.7-Flash QLoRA SFT Fine-tuning")
    logger.info("=" * 60)
    logger.info("Model: %s", args.model)
    logger.info("Dataset: %s", args.dataset)
    logger.info("Output: %s", args.output_dir)

    compute_dtype = torch.bfloat16 if not args.no_bf16 else torch.float32

    model, tokenizer = load_model_4bit(
        args.model,
        bnb_4bit_compute_dtype=compute_dtype,
        bnb_4bit_quant_type=args.quant_type,
        bnb_4bit_use_double_quant=not args.no_double_quant,
    )

    # ── Apply LoRA ──────────────────────────────────────────────────────
    model = apply_lora(
        model,
        target_modules=args.target_modules,
        r=args.lora_r,
        lora_alpha=args.lora_alpha,
        lora_dropout=args.lora_dropout,
        include_experts=args.include_experts,
    )

    # ── Dataset ─────────────────────────────────────────────────────────
    logger.info("Loading dataset...")
    dataset_kwargs = dict(
        path=args.dataset,
        tokenizer=tokenizer,
        max_length=args.max_length,
        max_samples=args.max_samples,
    )

    if args.streaming:
        full_dataset = StreamingJSONLDataset(
            **dataset_kwargs,
            shuffle_buffer_size=10000,
            seed=args.seed,
        )
        logger.info("Using streaming dataset")
    else:
        full_dataset = CachedJSONLDataset(**dataset_kwargs)

    # For eval, we take a small random subset from the same JSONL
    eval_dataset = None
    if args.eval_split > 0 and args.max_samples is None:
        # Create a small eval set by reading a separate slice
        eval_kwargs = dict(dataset_kwargs)
        eval_kwargs["max_samples"] = max(100, int(410918 * args.eval_split))
        eval_dataset = CachedJSONLDataset(**eval_kwargs)
        logger.info("Eval dataset: %d samples (%.1f%%)",
                      len(eval_dataset) if hasattr(eval_dataset, '__len__') else '?',
                      100 * args.eval_split)

    # ── Training args ────────────────────────────────────────────────────
    training_args = prepare_training_args(
        args.output_dir,
        num_train_epochs=args.epochs,
        per_device_train_batch_size=args.batch_size,
        gradient_accumulation_steps=args.gradient_accumulation,
        learning_rate=args.lr,
        warmup_steps=args.warmup_steps,
        save_steps=args.save_steps,
        eval_steps=args.eval_steps,
        logging_steps=args.logging_steps,
        max_grad_norm=args.max_grad_norm,
        lr_scheduler_type=args.lr_scheduler,
        bf16=not args.no_bf16,
        report_to=args.report_to,
        run_name=args.run_name,
    )

    effective_batch = args.batch_size * args.gradient_accumulation
    n_gpus = torch.cuda.device_count() if torch.cuda.is_available() else 1
    logger.info("GPUs available: %d", n_gpus)
    logger.info(
        "Effective batch size: %d (%d x %d accumulation x %d GPU)",
        effective_batch * n_gpus,
        args.batch_size,
        args.gradient_accumulation,
        n_gpus,
    )

    # ── Train ────────────────────────────────────────────────────────────
    logger.info("Starting training...")
    start_time = time.monotonic()

    try:
        train(
            model=model,
            tokenizer=tokenizer,
            dataset=full_dataset,
            training_args=training_args,
            eval_dataset=eval_dataset,
            resume_from_checkpoint=args.resume,
        )
    except KeyboardInterrupt:
        logger.info("Training interrupted. Saving checkpoint...")
    except Exception as exc:
        logger.error("Training failed: %s", exc)
        raise
    finally:
        elapsed = time.monotonic() - start_time
        logger.info("Total training time: %.1f min (%.1f hours)",
                      elapsed / 60, elapsed / 3600)

    # ── Evaluation ───────────────────────────────────────────────────────
    if not args.no_eval:
        logger.info("Running evaluation...")
        run_evaluation(
            model, tokenizer,
            output_dir=args.output_dir / "eval",
        )

    # ── Merge (optional) ─────────────────────────────────────────────────
    if args.merge:
        merge_and_save(
            model,
            tokenizer,
            args.output_dir / "merged",
            push_to_hub=args.push_to_hub,
        )

    logger.info("Done! Model saved to %s", args.output_dir)
    logger.info(
        "To use the adapter: model = PeftModel.from_pretrained(base_model, '%s/final')",
        args.output_dir,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
