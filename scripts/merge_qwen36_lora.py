"""
Merge LoRA adapter into Qwen3.6-35B-A3B base model (bf16), then save
merged weights for GGUF conversion.

Requires 98GB+ VRAM (fits RTX PRO 6000 S).

Usage:
    python scripts/merge_qwen36_lora.py \
        --base Qwen/Qwen3.6-35B-A3B \
        --adapter checkpoint-2600 \
        --output merged-model \
        --dtype fp16
"""

from __future__ import annotations

import argparse
import logging
import time

import torch

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S")
logger = logging.getLogger("merge")


def merge(args):
    from transformers import AutoModelForCausalLM, AutoTokenizer
    from peft import PeftModel

    logger.info("Loading base model in bf16 (no quantization)...")
    t0 = time.time()

    model = AutoModelForCausalLM.from_pretrained(
        args.base,
        device_map="auto",
        torch_dtype=torch.bfloat16,
    )
    tokenizer = AutoTokenizer.from_pretrained(args.base)
    logger.info("Base model loaded in %.1fs", time.time() - t0)

    logger.info("GPU memory: %.1f GB allocated", torch.cuda.memory_allocated() / 1e9)

    logger.info("Loading LoRA adapter: %s", args.adapter)
    model = PeftModel.from_pretrained(model, args.adapter)
    logger.info("Adapter loaded. Merging...")

    t1 = time.time()
    merged = model.merge_and_unload()
    logger.info("Merged in %.1fs", time.time() - t1)

    logger.info("GPU memory after merge: %.1f GB allocated", torch.cuda.memory_allocated() / 1e9)

    logger.info("Converting to %s and saving to %s...", args.dtype, args.output)
    os.makedirs(args.output, exist_ok=True)

    if args.dtype == "fp16":
        merged = merged.half()
    elif args.dtype == "bf16":
        merged = merged.bfloat16()

    merged.save_pretrained(args.output, safe_serialization=True, max_shard_size="5GB")
    tokenizer.save_pretrained(args.output)

    logger.info("Merged model saved. Done.")


if __name__ == "__main__":
    import os
    os.environ["TOKENIZERS_PARALLELISM"] = "false"

    p = argparse.ArgumentParser()
    p.add_argument("--base", default="Qwen/Qwen3.6-35B-A3B")
    p.add_argument("--adapter", required=True)
    p.add_argument("--output", required=True)
    p.add_argument("--dtype", default="fp16", choices=["fp16", "bf16"])
    args = p.parse_args()
    merge(args)
