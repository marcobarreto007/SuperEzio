"""Merge two Qwen3.6 GGUFs via linear interpolation -> Q8_0 intermediate.

Usage:
    python scripts/merge_gguf.py --model1 models/merged.Q4_K_M.gguf \
        --model2 models/aggressive.Q4_K_P.gguf \
        --output models/merged.Q8_0.gguf --ratio 0.6

Then quantize with llama.cpp:
    llama-quantize.exe models/merged.Q8_0.gguf models/merged.Q4_K_M.gguf Q4_K_M
"""

from __future__ import annotations

import argparse
import gc
import time
from pathlib import Path

import numpy as np

import gguf

# Fields managed by GGUFWriter internally — don't copy from source
_SKIP_FIELDS = {
    "GGUF.version",
    "GGUF.tensor_count",
    "GGUF.kv_count",
    "general.architecture",
}


def _extract_value(field: gguf.ReaderField):
    """Extract Python value from a ReaderField based on its GGUFValueType."""
    vtype = field.types[0]
    data = field.parts[-1]

    if vtype == gguf.GGUFValueType.STRING:
        return bytes(data).decode("utf-8", errors="replace")
    if vtype == gguf.GGUFValueType.BOOL:
        return bool(data[0])
    if vtype in (
        gguf.GGUFValueType.INT8,
        gguf.GGUFValueType.INT16,
        gguf.GGUFValueType.INT32,
        gguf.GGUFValueType.INT64,
        gguf.GGUFValueType.UINT8,
        gguf.GGUFValueType.UINT16,
        gguf.GGUFValueType.UINT32,
        gguf.GGUFValueType.UINT64,
    ):
        return int(data[0])
    if vtype in (gguf.GGUFValueType.FLOAT32, gguf.GGUFValueType.FLOAT64):
        return float(data[0])
    if vtype == gguf.GGUFValueType.ARRAY:
        return data.tolist()
    return None


_VALUE_ADD_METHOD = {
    gguf.GGUFValueType.STRING: "add_string",
    gguf.GGUFValueType.BOOL: "add_bool",
    gguf.GGUFValueType.UINT8: "add_uint8",
    gguf.GGUFValueType.UINT16: "add_uint16",
    gguf.GGUFValueType.UINT32: "add_uint32",
    gguf.GGUFValueType.UINT64: "add_uint64",
    gguf.GGUFValueType.INT8: "add_int8",
    gguf.GGUFValueType.INT16: "add_int16",
    gguf.GGUFValueType.INT32: "add_int32",
    gguf.GGUFValueType.INT64: "add_int64",
    gguf.GGUFValueType.FLOAT32: "add_float32",
    gguf.GGUFValueType.FLOAT64: "add_float64",
    gguf.GGUFValueType.ARRAY: "add_array",
}


def merge_gguf(
    path1: Path,
    path2: Path,
    output: Path,
    ratio: float = 0.6,
) -> None:
    """Merge two GGUFs by linear interpolation, writing output as Q8_0."""
    t0 = time.time()

    print(f"Loading {path1.name}...")
    r1 = gguf.GGUFReader(str(path1))
    print(f"Loading {path2.name}...")
    r2 = gguf.GGUFReader(str(path2))

    tensors1 = list(r1.tensors)
    tensors2 = list(r2.tensors)

    if len(tensors1) != len(tensors2):
        raise ValueError(f"Tensor count mismatch: {len(tensors1)} vs {len(tensors2)}")

    # --- Build tensor name -> (t1, t2) mapping ---
    t2_by_name = {t.name: t for t in tensors2}
    pairs: list[tuple[gguf.ReaderTensor, gguf.ReaderTensor]] = []
    for t1 in tensors1:
        t2 = t2_by_name.get(t1.name)
        if t2 is None:
            raise ValueError(f"Tensor {t1.name} not found in model2")
        pairs.append((t1, t2))

    # --- Extract architecture string from model1 ---
    arch_field = r1.fields.get("general.architecture")
    arch = _extract_value(arch_field) if arch_field else "unknown"

    # --- Write merged GGUF ---
    writer = gguf.GGUFWriter(str(output), arch=arch)

    # Copy metadata from model1 (skip internal fields)
    for field in r1.fields.values():
        if field.name in _SKIP_FIELDS:
            continue
        val = _extract_value(field)
        if val is None:
            print(f"  Warning: could not extract value for {field.name}")
            continue
        method_name = _VALUE_ADD_METHOD.get(field.types[0])
        if method_name is None:
            print(f"  Warning: unknown type {field.types[0]} for {field.name}")
            continue
        getattr(writer, method_name)(field.name, val)

    print(f"Copied {len(r1.fields) - len(_SKIP_FIELDS)} metadata fields from model1")

    out_qtype = gguf.GGMLQuantizationType.Q8_0

    n_total = len(pairs)
    print(f"Merging {n_total} tensors (ratio={ratio:.2f}) -> Q8_0...")

    for i, (t1, t2) in enumerate(pairs):
        name = t1.name
        shape = t1.shape

        # Dequantize both
        d1_raw = np.array(t1.data, copy=False)
        d2_raw = np.array(t2.data, copy=False)
        f1 = gguf.dequantize(d1_raw, t1.tensor_type)
        f2 = gguf.dequantize(d2_raw, t2.tensor_type)

        # Merge
        merged = (ratio * f1 + (1.0 - ratio) * f2).astype(np.float32)

        # Quantize to Q8_0
        try:
            q = gguf.quantize(merged, out_qtype)
        except NotImplementedError:
            # Some types may not support quantize; fallback to F16
            fallback = gguf.GGMLQuantizationType.F16
            q = gguf.quantize(merged, fallback)
            if i == 0:
                print(f"  Note: Q8_0 not supported for {name}, using F16")

        # Add tensor to writer
        writer.add_tensor(name, q, raw_shape=shape, raw_dtype=out_qtype)

        # Progress
        if (i + 1) % 50 == 0 or i == n_total - 1:
            pct = (i + 1) / n_total * 100
            elapsed = time.time() - t0
            eta = elapsed / (i + 1) * (n_total - i - 1)
            print(
                f"  [{i + 1:4d}/{n_total}] {pct:.0f}% | "
                f"{elapsed:.0f}s elapsed | {eta:.0f}s remaining | {name}"
            )

        # Free per-tensor memory
        del d1_raw, d2_raw, f1, f2, merged, q
        if i % 10 == 0:
            gc.collect()

    print(f"Writing {output}...")
    writer.close()

    elapsed = time.time() - t0
    size_gb = output.stat().st_size / 1e9
    print(f"Done: {output} ({size_gb:.1f} GB) in {elapsed:.0f}s ({elapsed / 60:.1f} min)")


def main() -> None:
    parser = argparse.ArgumentParser(description="Merge two GGUFs via linear interpolation -> Q8_0")
    parser.add_argument("--model1", required=True, help="Path to first (merged) GGUF")
    parser.add_argument("--model2", required=True, help="Path to second (aggressive) GGUF")
    parser.add_argument("--output", required=True, help="Output GGUF path (Q8_0)")
    parser.add_argument(
        "--ratio",
        type=float,
        default=0.6,
        help="Interpolation ratio for model1 (default: 0.6)",
    )
    args = parser.parse_args()

    merge_gguf(
        path1=Path(args.model1),
        path2=Path(args.model2),
        output=Path(args.output),
        ratio=args.ratio,
    )


if __name__ == "__main__":
    main()
