from huggingface_hub import hf_hub_download
print("Baixando Mixtral 8x7B Q4_K_M - 24GB...")
path = hf_hub_download(
    repo_id="TheBloke/Mixtral-8x7B-Instruct-v0.1-GGUF",
    filename="mixtral-8x7b-instruct-v0.1.Q4_K_M.gguf",
    local_dir="/mnt/c/F51_LAB/models/mixtral-new",
    token="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"
)
print("CONCLUIDO:", path)
