from huggingface_hub import hf_hub_download
import os

print("Baixando GLM-4.5-Air IQ4_XS do unsloth...")
print("Este modelo tem tensores _exps e funciona com F51!")
print()

# List files first
from huggingface_hub import list_repo_files
files = list_repo_files('unsloth/GLM-4.5-Air-GGUF')
print(f"Arquivos disponiveis ({len(files)}):")
for f in files:
    if 'IQ4_XS' in f or 'IQ4' in f:
        print(f"  {f}")

# Download IQ4_XS version (smaller)
target = None
for f in files:
    if 'IQ4_XS' in f and f.endswith('.gguf'):
        target = f
        break

if not target:
    for f in files:
        if 'Q4_K_M' in f and f.endswith('.gguf'):
            target = f
            break

if not target:
    print("Nenhum .gguf IQ4 encontrado, listando todos:")
    for f in files:
        print(f"  {f}")
    exit(1)

print(f"\nBaixando: {target}")
print("Destino: /mnt/c/F51_LAB/models/glm/")
os.makedirs('/mnt/c/F51_LAB/models/glm', exist_ok=True)

path = hf_hub_download(
    repo_id='unsloth/GLM-4.5-Air-GGUF',
    filename=target,
    local_dir='/home/marco/models/glm',
    token='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',
    local_dir_use_symlinks=False,
)

# Copy to Windows accessible path
import shutil
dest = f"/mnt/c/F51_LAB/models/glm/{target}"
print(f"\nCopiando para {dest}...")
shutil.copy2(path, dest)
print("PRONTO!")
print(f"Modelo: {dest}")
