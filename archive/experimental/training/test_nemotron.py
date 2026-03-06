import torch
from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig

model_id = "nvidia/NVIDIA-Nemotron-Nano-12B-v2"

print("Loading tokenizer...")
tokenizer = AutoTokenizer.from_pretrained(model_id)
tokenizer.pad_token = tokenizer.eos_token
print(f"Tokenizer loaded. Vocab size: {tokenizer.vocab_size}")

bnb_config = BitsAndBytesConfig(
    load_in_4bit=True,
    bnb_4bit_quant_type="nf4",
    bnb_4bit_compute_dtype=torch.bfloat16,
    bnb_4bit_use_double_quant=True,
    llm_int8_enable_fp32_cpu_offload=True,
)

print("Loading model in 4-bit...")
model = AutoModelForCausalLM.from_pretrained(
    model_id,
    quantization_config=bnb_config,
    device_map="auto",
    torch_dtype=torch.bfloat16,
)
print("Model loaded!")
allocated = torch.cuda.memory_allocated() / 1024**3
total = torch.cuda.get_device_properties(0).total_memory / 1024**3
print(f"VRAM: {allocated:.1f} GB / {total:.1f} GB")
params = sum(p.numel() for p in model.parameters()) / 1e9
print(f"Params: {params:.2f}B")
print("SUCCESS")
