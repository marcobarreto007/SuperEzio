# SuperEzio — Model Configuration
# ZERO-CLOUD (2026-08-18): CEO/experts = shared local llama-server (perfil cc).
# GPU: RTX 3060 12GB + RTX 2070 8GB, tensor split 12,8, context 8192.

$ModelPath = "C:\Users\marco\models\qwen3.8-27b\Qwen3.8-27B-Q4_K_M.gguf"
$ModelsDir = "C:\Users\marco\models\qwen3.8-27b"
$LoraPath = $null

# llama-server binary (CUDA build that actually runs on 3060+2070).
# llama.cpp-src MSVC build crashes: "no kernel image" in ggml_cuda_kernel_can_use_pdl.
$LlamaServerPath = "C:\Users\marco\tools\llama.cpp\llama-server.exe"
