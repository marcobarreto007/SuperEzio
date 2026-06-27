from huggingface_hub import hf_hub_download
import os, shutil

print("Baixando GLM-4.5-Air IQ4_XS parte 2/2...")

path = hf_hub_download(
    repo_id='unsloth/GLM-4.5-Air-GGUF',
    filename='IQ4_XS/GLM-4.5-Air-IQ4_XS-00002-of-00002.gguf',
    local_dir='/home/marco/models/glm',
    token='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',
    local_dir_use_symlinks=False,
)

# Copy both parts to Windows
dest_dir = '/mnt/c/F51_LAB/models/glm/IQ4_XS'
os.makedirs(dest_dir, exist_ok=True)

for part in ['00001', '00002']:
    src = f'/home/marco/models/glm/IQ4_XS/GLM-4.5-Air-IQ4_XS-{part}-of-00002.gguf'
    dst = f'{dest_dir}/GLM-4.5-Air-IQ4_XS-{part}-of-00002.gguf'
    if os.path.exists(src) and not os.path.exists(dst):
        print(f'Copiando parte {part}...')
        shutil.copy2(src, dst)
        print(f'  OK: {dst}')

print('\nPRONTO!')
print(f'Modelo em: {dest_dir}')
