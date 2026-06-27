#!/bin/bash
export HF_TOKEN="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"

rm -f /mnt/c/F51_LAB/models/mixtral-new/*.gguf

python3 -c "
from huggingface_hub import hf_hub_download
print('>>> Baixando Mixtral 8x7B Q4_K_M - 24GB do TheBloke...')
path = hf_hub_download(
    repo_id='TheBloke/Mixtral-8x7B-Instruct-v0.1-GGUF',
    filename='mixtral-8x7b-instruct-v0.1.Q4_K_M.gguf',
    local_dir='/mnt/c/F51_LAB/models/mixtral-new',
    token='$HF_TOKEN'
)
print(f'>>> CONCLUIDO: {path}')
" 2>&1

echo ""
ls -lh /mnt/c/F51_LAB/models/mixtral-new/
