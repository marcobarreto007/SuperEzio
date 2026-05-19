"""
Merge LoRA adapters into Qwen3.6-35B-A3B base model (bf16), then save
merged weights for GGUF conversion.

Supports multiple --adapter args for stacking LoRAs (e.g., CEO + intent).

Requires 98GB+ VRAM (fits RTX PRO 6000 S).

Usage:
    # Single adapter
    python scripts/merge_qwen36_lora.py \
        --base Qwen/Qwen3.6-35B-A3B \
        --adapter checkpoint-2600 \
        --output merged-model \
        --dtype fp16

    # Multiple adapters (stacked: CEO LoRA + intent LoRA)
    python scripts/merge_qwen36_lora.py \
        --base Qwen/Qwen3.6-35B-A3B \
        --adapter output/qwen36-sft/checkpoint-2600 \
        --adapter output/qwen36-intent/checkpoint-80 \
        --output final-merged \
        --dtype fp16
"""

from __future__ import annotations

import argparse
import logging
import os
import time

import torch

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S"
)
logger = logging.getLogger("merge")


def merge(args):
    from transformers import AutoModelForCausalLM, AutoTokenizer
    from peft import PeftModel

    logger.info("Loading base model in bf16 (no quantization)...")
    t0 = time.time()

    if args.dtype == "fp16":
        load_dtype = torch.float16
    elif args.dtype == "bf16":
        load_dtype = torch.bfloat16
    else:
        load_dtype = torch.float16

    model = AutoModelForCausalLM.from_pretrained(
        args.base,
        device_map="auto",
        torch_dtype=load_dtype,
    )
    tokenizer = AutoTokenizer.from_pretrained(args.base)
    logger.info("Base model loaded in %.1fs", time.time() - t0)
    logger.info("GPU memory: %.1f GB allocated", torch.cuda.memory_allocated() / 1e9)

    for i, adapter_path in enumerate(args.adapter, 1):
        logger.info("[%d/%d] Loading LoRA adapter: %s", i, len(args.adapter), adapter_path)
        model = PeftModel.from_pretrained(model, adapter_path)
        logger.info("[%d/%d] Merging...", i, len(args.adapter))
        t1 = time.time()
        model = model.merge_and_unload()
        logger.info(
            "[%d/%d] Merged in %.1fs (%.1f GB allocated)",
            i,
            len(args.adapter),
            time.time() - t1,
            torch.cuda.memory_allocated() / 1e9,
        )

    logger.info(
        "GPU memory after all merges: %.1f GB allocated", torch.cuda.memory_allocated() / 1e9
    )

    logger.info("Converting to %s and saving to %s...", args.dtype, args.output)
    os.makedirs(args.output, exist_ok=True)

    if args.dtype == "fp16":
        model = model.half()
    elif args.dtype == "bf16":
        model = model.bfloat16()

    model.save_pretrained(args.output, safe_serialization=True, max_shard_size="5GB")
    tokenizer.save_pretrained(args.output)

    logger.info("Merged model saved. Done.")


if __name__ == "__main__":
    os.environ["TOKENIZERS_PARALLELISM"] = "false"

    p = argparse.ArgumentParser()
    p.add_argument("--base", default="Qwen/Qwen3.6-35B-A3B")
    p.add_argument(
        "--adapter",
        action="append",
        required=True,
        help="LoRA adapter path (repeat for multiple: --adapter ckpt1 --adapter ckpt2)",
    )
    p.add_argument("--output", required=True)
    p.add_argument("--dtype", default="fp16", choices=["fp16", "bf16"])
    args = p.parse_args()
    merge(args)
