from huggingface_hub import hf_hub_download
import os

os.makedirs('/home/marco/models/mixtral-new', exist_ok=True)

print("Baixando Mixtral 8x7B Q4_K_M (24GB) para WSL nativo...")
print("Isso vai levar uns 20-30 minutos...")
print()

path = hf_hub_download(
    repo_id="TheBloke/Mixtral-8x7B-Instruct-v0.1-GGUF",
    filename="mixtral-8x7b-instruct-v0.1.Q4_K_M.gguf",
    local_dir="/home/marco/models/mixtral-new",
    token="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",
    local_dir_use_symlinks=False,
)

# Copy to Windows accessible path
import shutil
dest = "/mnt/c/F51_LAB/models/mixtral-new/mixtral-8x7b-instruct-v0.1.Q4_K_M.gguf"
os.makedirs(os.path.dirname(dest), exist_ok=True)
print()
print(f"Baixado! Copiando para {dest}...")
shutil.copy2(path, dest)
print("PRONTO!")
print(f"Arquivo: {dest}")
