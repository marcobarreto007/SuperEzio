"""Quick inference test for merged SuperEzio model."""
import torch
from transformers import AutoModelForCausalLM, AutoTokenizer

MODEL_PATH = r"C:\Users\marco\Desktop\SuperEzio\.f51\tmp\superezio-merged"

print("Loading merged SuperEzio model...")
model = AutoModelForCausalLM.from_pretrained(
    MODEL_PATH, torch_dtype=torch.bfloat16, device_map="auto",
)
tokenizer = AutoTokenizer.from_pretrained(MODEL_PATH)
tokenizer.pad_token = tokenizer.eos_token

tests = [
    ("Fraud/Phishing Detection (Phase 0)",
     "<|user|>\nClassifique este texto como phishing ou legitimo:\n\n"
     "\"URGENTE: Sua conta foi bloqueada. Clique aqui para recuperar: http://banco-falso.com/recuperar\"\n\n"
     "Classificacao:"),
    ("Numerical Reasoning (Phase 1)",
     "<|user|>\nIf a stock is at $150 and drops 12%, what is the new price? Show your calculation."),
    ("Combined Financial Analysis",
     "<|user|>\nAnalyze this situation: Company XYZ reported a 15% increase in revenue but their stock "
     "dropped 8%. The CEO recently sold 40% of their shares. Is this suspicious? Rate fraud risk 1-10 "
     "and explain your reasoning."),
]

for name, prompt in tests:
    print(f"\n{'='*60}")
    print(f"[TEST] {name}")
    print(f"{'='*60}")
    inputs = tokenizer(prompt, return_tensors="pt").to(model.device)
    with torch.no_grad():
        out = model.generate(**inputs, max_new_tokens=120, temperature=0.2, do_sample=True)
    response = tokenizer.decode(out[0], skip_special_tokens=True)
    # Show just the generated part (after the prompt)
    generated = response[len(prompt):]
    print(generated[:500])

print("\n\nAll tests complete.")
