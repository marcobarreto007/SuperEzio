"""
Repack old Mixtral GGUF (ffn_gate.0.weight) to new format (ffn_gate_exps.weight).
Merges individual expert tensors into fused _exps tensors.
"""
import struct
import sys
import os
import shutil
from collections import OrderedDict

INPUT = "/mnt/c/F51_LAB/models/mixtral-new/mixtral-8x7b-instruct-v0.1.Q4_K_M.gguf"
OUTPUT = "/mnt/c/F51_LAB/models/mixtral-new/mixtral-8x7b-instruct-v0.1-Q4_K_M-f51.gguf"

print(f"Lendo: {INPUT}")

with open(INPUT, 'rb') as f:
    # Read header
    magic = f.read(4)
    assert magic == b'GGUF', f"Not a GGUF file: {magic}"
    version = struct.unpack('<I', f.read(4))[0]
    n_tensors, n_kv = struct.unpack('<QQ', f.read(16))
    
    print(f"GGUF v{version}, {n_tensors} tensors, {n_kv} keys")

    # Read all KV pairs
    kv_pairs = []
    for i in range(n_kv):
        key_len = struct.unpack('<Q', f.read(8))[0]
        key = f.read(key_len)
        val_type = struct.unpack('<I', f.read(4))[0]
        
        if val_type == 0:  # f32
            val = f.read(4)
        elif val_type == 1:  # f64
            val = f.read(8)
        elif val_type == 2:  # i8
            val = f.read(1)
        elif val_type == 3:  # i16
            val = f.read(2)
        elif val_type == 4:  # i32
            val = f.read(4)
        elif val_type == 5:  # i64
            val = f.read(8)
        elif val_type == 6:  # f64
            val = f.read(8)
        elif val_type == 7:  # bool
            val = f.read(1)
        elif val_type == 8:  # string
            val_len = struct.unpack('<Q', f.read(8))[0]
            val = f.read(val_len)
        elif val_type == 9:  # array
            val_type_inner = struct.unpack('<I', f.read(4))[0]
            n_el = struct.unpack('<Q', f.read(8))[0]
            val = struct.pack('<IQ', val_type_inner, n_el)
            for _ in range(n_el):
                if val_type_inner == 8:
                    el_len = struct.unpack('<Q', f.read(8))[0]
                    val += struct.pack('<Q', el_len)
                    val += f.read(el_len)
                elif val_type_inner in (4,):
                    val += f.read(4)
                elif val_type_inner in (6,):
                    val += f.read(8)
                elif val_type_inner in (0,):
                    val += f.read(4)
        else:
            print(f"Unknown val_type {val_type} for key {key}")
            sys.exit(1)
        
        kv_pairs.append((key, val_type, val))

    # Read tensor infos
    tensor_infos = []
    for i in range(n_tensors):
        name_len = struct.unpack('<Q', f.read(8))[0]
        name_raw = f.read(name_len)
        name = name_raw.decode('utf-8')
        n_dims = struct.unpack('<I', f.read(4))[0]
        dims = []
        for d in range(n_dims):
            dims.append(struct.unpack('<Q', f.read(8))[0])
        tensor_type = struct.unpack('<I', f.read(4))[0]
        tensor_offset = struct.unpack('<Q', f.read(8))[0]
        tensor_infos.append((name, name_raw, n_dims, dims, tensor_type, tensor_offset))

    # Data starts here
    data_start = f.tell()

print(f"Data starts at offset {data_start}")
print(f"Total tensors: {n_tensors}")

# Identify expert tensors to merge
import re
expert_pattern = re.compile(r'blk\.(\d+)\.(ffn_gate|ffn_down|ffn_up)\.(\d+)\.weight')

# Group by layer and type
groups = OrderedDict()
tensors_to_remove = set()
new_tensors = []

for i, (name, name_raw, n_dims, dims, ttype, offset) in enumerate(tensor_infos):
    m = expert_pattern.match(name)
    if m:
        layer = int(m.group(1))
        ffn_type = m.group(2)
        expert_idx = int(m.group(3))
        key = (layer, ffn_type)
        if key not in groups:
            groups[key] = []
        groups[key].append((expert_idx, i, offset, dims, ttype))
        tensors_to_remove.add(i)

print(f"\nGrupos de experts encontrados: {len(groups)}")

# For each group, create a new fused tensor entry
new_tensor_list = []
expert_data_offsets = {}  # (layer, ffn_type) -> [(expert_idx, old_offset, new_offset)]

for (layer, ffn_type), experts in groups.items():
    new_name = f"blk.{layer}.{ffn_type}_exps.weight"
    experts_sorted = sorted(experts, key=lambda x: x[0])
    
    # All experts should have the same dims except n_experts
    first_dims = list(experts_sorted[0][3])
    # New tensor: [n_embd, n_ff, n_expert]
    n_expert = len(experts_sorted)
    if ffn_type == 'ffn_down':
        new_dims = [first_dims[0], first_dims[1], n_expert]
    else:
        new_dims = [first_dims[0], first_dims[1], n_expert]
    
    new_tensor_list.append((new_name, new_dims, experts_sorted))
    print(f"  {new_name}: {len(experts_sorted)} experts -> {new_dims}")

# Build new tensor list (keep non-expert tensors + new fused ones)
final_tensors = []
remove_set = set()
for i, info in enumerate(tensor_infos):
    name = info[0]
    if not expert_pattern.match(name):
        final_tensors.append(('keep', i, info))
    else:
        remove_set.add(i)

# Add new fused tensors after the last original tensor position
for new_name, new_dims, experts_sorted in new_tensor_list:
    # Use the tensor type from the first expert
    ttype = experts_sorted[0][4]
    final_tensors.append(('new', -1, (new_name, new_dims, experts_sorted, ttype)))

print(f"\nTensors finais: {len(final_tensors)} (removidos {len(remove_set)} experts, adicionados {len(new_tensor_list)} fused)")

# Write output
print(f"\nEscrevendo: {OUTPUT}")
with open(OUTPUT, 'wb') as out:
    # Header
    out.write(b'GGUF')
    out.write(struct.pack('<I', version))
    new_n_tensors = len(final_tensors)
    out.write(struct.pack('<QQ', new_n_tensors, n_kv))
    
    # KV pairs (unchanged)
    for key, val_type, val in kv_pairs:
        out.write(struct.pack('<Q', len(key)))
        out.write(key)
        out.write(struct.pack('<I', val_type))
        out.write(val)
    
    # Tensor infos
    # First pass: write names and dims for all tensors
    tensor_data_offsets = []
    current_offset = 0
    
    for status, old_idx, info in final_tensors:
        if status == 'keep':
            name, name_raw, n_dims, dims, ttype, old_offset = info
            size = 1
            for d in dims:
                size *= d
            size *= {0:4, 1:2, 2:2, 3:2, 4:2, 5:2, 6:2, 7:2, 8:4, 9:4, 10:1, 11:4, 12:4, 13:2, 14:1, 15:1, 16:1, 17:1, 18:1, 19:1, 20:1, 21:1, 22:1, 23:1, 24:2, 25:2, 26:1, 27:1}.get(ttype, 2)
            new_offset = current_offset
        else:  # new
            new_name, new_dims, experts_sorted, ttype = info
            name_raw = new_name.encode('utf-8')
            dims = new_dims
            n_dims = len(new_dims)
            size = 1
            for d in dims:
                size *= d
            # Calculate element size for this type
            elem_size = {0:4, 1:2, 2:2, 3:2, 4:2, 5:2, 6:2, 7:2, 8:4, 9:4, 10:1, 11:4, 12:4, 13:2, 14:1, 15:1, 16:1, 17:1, 18:1, 19:1, 20:1, 21:1, 22:1, 23:1, 24:2, 25:2, 26:1, 27:1}.get(ttype, 2)
            size *= elem_size
            new_offset = current_offset
        
        out.write(struct.pack('<Q', len(name_raw)))
        out.write(name_raw)
        out.write(struct.pack('<I', n_dims))
        for d in dims:
            out.write(struct.pack('<Q', d))
        out.write(struct.pack('<I', ttype))
        out.write(struct.pack('<Q', new_offset))
        
        tensor_data_offsets.append((status, old_idx, new_offset, size, info))
        current_offset += size
        # Align to 32 bytes
        while current_offset % 32 != 0:
            current_offset += 1
    
    # Write padding to align data start
    pos = out.tell()
    while pos < data_start:
        out.write(b'\x00')
        pos += 1
    
    # Write tensor data
    with open(INPUT, 'rb') as inf:
        for status, old_idx, new_offset, size, info in tensor_data_offsets:
            if status == 'keep':
                name, name_raw, n_dims, dims, ttype, old_offset = info
                inf.seek(old_offset)
                data = inf.read(size)
                out.write(data)
            else:  # new
                new_name, new_dims, experts_sorted, ttype = info
                elem_size = {0:4, 1:2, 2:2, 3:2, 4:2, 5:2, 6:2, 7:2, 8:4, 9:4, 10:1, 11:4, 12:4, 13:2, 14:1, 15:1, 16:1, 17:1, 18:1, 19:1, 20:1, 21:1, 22:1, 23:1, 24:2, 25:2, 26:1, 27:1}.get(ttype, 2)
                per_expert = size // len(experts_sorted)
                
                for expert_idx, old_tensor_idx, old_off, old_dims, _ in experts_sorted:
                    inf.seek(old_off)
                    data = inf.read(per_expert)
                    out.write(data)
            
            # Align to 32 bytes
            pos = out.tell()
            while pos % 32 != 0:
                out.write(b'\x00')
                pos += 1

print(f"\nPRONTO! {OUTPUT}")
print(f"Tamanho: {os.path.getsize(OUTPUT) / (1024**3):.1f} GB")
