#!/usr/bin/env python3
"""Repack old Mixtral GGUF to new _exps format using gguf library."""
import sys, os, struct
import numpy as np
from gguf import GGUFReader, GGUFWriter
from gguf.constants import GGMLQuantizationType, Keys
from tqdm import tqdm

INPUT = "/mnt/c/F51_LAB/models/mixtral-new/mixtral-8x7b-instruct-v0.1.Q4_K_M.gguf"
OUTPUT = "/mnt/c/F51_LAB/models/mixtral-new/mixtral-8x7b-instruct-v0.1-Q4_K_M-f51.gguf"

print(f"Lendo {INPUT}...")
reader = GGUFReader(INPUT)

# Collect expert tensors per layer
import re
expert_re = re.compile(r'blk\.(\d+)\.(ffn_gate|ffn_down|ffn_up)\.(\d+)\.weight')

expert_groups = {}  # (layer, ffn_type) -> [(expert_idx, tensor)]
other_tensors = []

for tensor in reader.tensors:
    m = expert_re.match(tensor.name)
    if m:
        layer = int(m.group(1))
        ffn_type = m.group(2)
        expert_idx = int(m.group(3))
        key = (layer, ffn_type)
        if key not in expert_groups:
            expert_groups[key] = {}
        expert_groups[key][expert_idx] = tensor
    else:
        other_tensors.append(tensor)

print(f"Encontrados {len(expert_groups)} grupos de experts, {len(other_tensors)} outros tensores")

# Write new GGUF
print(f"Escrevendo {OUTPUT}...")
writer = GGUFWriter(OUTPUT, reader.arch)

# Copy all metadata
for key in reader.fields:
    val = reader.fields[key]
    writer.add_key(key)
    # Copy value based on type
    writer.fout.write(val.parts[val.offset - val.data[0]:])

# We need a different approach... let me use the lower-level API

print("Fechando writer...")
writer.close()

print("PRONTO!")
