# SuperEzio — Model Configuration
# CEO: QwenLong 30B A3B Q4_K (49/49 layers GPU, 17.3 GB)
# LoRA: Bob F51 Nitro v7 (finance specialist)

$ModelPath = "C:\llama.cpp\models\qwenlong-30b-a3b-q4_k.gguf"
$ModelsDir = "C:\llama.cpp\models"
$LoraPath = "$PSScriptRoot\models\bob_lora_qwenlong_30b_f51\lora_f51_v7.gguf"

# llama-server binary (CUDA build)
$LlamaServerPath = "C:\llama.cpp\build\bin\llama-server.exe"
