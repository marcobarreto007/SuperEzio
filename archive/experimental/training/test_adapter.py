"""
Test Qwen 3.6 + LoRA adapter before integration.
Loads 4-bit base model, applies trained adapter, runs inference.
"""
import torch
import time
from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig
from peft import PeftModel

ADAPTER_PATH = r"C:\Users\marco\Desktop\qwen36-adapter"
BASE_MODEL = "nvidia/Qwen/Qwen3.6-27B"

SYSTEM_PROMPT = """You are Bob, CEO of SuperEzio Trust OS — an AI financial analysis platform.
Your mission is evidence-based analysis of Canadian (TSX, TSX-V) and US (NYSE, NASDAQ, OTC) markets.
You never trade, never give buy/sell orders, and never invent financial data, prices, or metrics.
Separate FACT from INFERENCE. Always provide EXPLAINABILITY for every assessment.
Output in JSON with fields: analysis_type, confidence (0-1), facts (list), inferences (list), risk_flags (list), explainability (str)."""

TESTS = [
    {
        "name": "Fraud analysis",
        "prompt": "Analyze this transaction pattern: Company X received 3 wire transfers of $9,900 each from different shell companies in the Cayman Islands on the same day. The company's stated business is a pizza shop in Montreal with annual revenue of $120,000. What fraud indicators do you see?",
    },
    {
        "name": "Market risk",
        "prompt": "Assess the risk of a TSX-V mining junior with $2M cash, $18M debt due in 6 months, zero revenue, and exploration permits under regulatory review. The stock is up 340% this month on social media promotion.",
    },
    {
        "name": "Phishing detection",
        "prompt": "Classify this email: 'URGENT: Your RBC Royal Bank account has been compromised. Click here to verify your identity: http://rbc-secure-verify.tk/login. Failure to respond within 24 hours will result in account suspension.'",
    },
]

def load():
    print("=" * 60)
    print("Loading Qwen 3.6 + SuperEzio LoRA adapter")
    print("=" * 60)

    bnb = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_compute_dtype=torch.bfloat16,
        bnb_4bit_use_double_quant=True,
        llm_int8_enable_fp32_cpu_offload=True,
    )

    print("\n[1/3] Loading tokenizer...")
    tokenizer = AutoTokenizer.from_pretrained(BASE_MODEL)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    print("[2/3] Loading base model in 4-bit...")
    t0 = time.time()
    model = AutoModelForCausalLM.from_pretrained(
        BASE_MODEL,
        quantization_config=bnb,
        device_map="auto",
        torch_dtype=torch.bfloat16,
    )
    print(f"  Base model loaded in {time.time() - t0:.1f}s")

    vram = torch.cuda.memory_allocated() / 1e9
    total = torch.cuda.get_device_properties(0).total_memory / 1e9
    print(f"  VRAM: {vram:.1f} GB / {total:.1f} GB")

    print("[3/3] Loading LoRA adapter...")
    t0 = time.time()
    model = PeftModel.from_pretrained(model, ADAPTER_PATH)
    print(f"  Adapter loaded in {time.time() - t0:.1f}s")

    trainable = sum(p.numel() for p in model.parameters() if p.requires_grad)
    print(f"  Trainable params: {trainable/1e6:.1f}M")

    model.eval()
    return model, tokenizer


def run_test(model, tokenizer, test, idx):
    print(f"\n{'─' * 60}")
    print(f"TEST #{idx+1}: {test['name']}")
    print(f"{'─' * 60}")
    print(f"Prompt: {test['prompt'][:120]}...")

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": test["prompt"]},
    ]

    # Format with Qwen36 chat template
    text = tokenizer.apply_chat_template(
        messages,
        tokenize=False,
        add_generation_prompt=True,
    )

    inputs = tokenizer(text, return_tensors="pt").to(model.device)
    print(f"  Input tokens: {inputs['input_ids'].shape[1]}")

    t0 = time.time()
    with torch.no_grad():
        outputs = model.generate(
            **inputs,
            max_new_tokens=256,
            temperature=0.3,
            do_sample=True,
            top_p=0.9,
            pad_token_id=tokenizer.eos_token_id,
        )
    elapsed = time.time() - t0
    gen_tokens = outputs.shape[1] - inputs["input_ids"].shape[1]
    print(f"  Generated {gen_tokens} tokens in {elapsed:.1f}s ({gen_tokens/elapsed:.1f} tok/s)")

    response = tokenizer.decode(outputs[0][inputs["input_ids"].shape[1]:], skip_special_tokens=True)
    print(f"\n  Response:\n  {response[:500]}")

    return response


def main():
    model, tokenizer = load()

    results = []
    for i, test in enumerate(TESTS):
        try:
            resp = run_test(model, tokenizer, test, i)
            results.append({"test": test["name"], "status": "ok", "response": resp[:200]})
        except Exception as e:
            print(f"\n  [FAIL] {e}")
            results.append({"test": test["name"], "status": "error", "error": str(e)})

    print(f"\n{'=' * 60}")
    print("SUMMARY")
    print(f"{'=' * 60}")
    passed = sum(1 for r in results if r["status"] == "ok")
    print(f"  Passed: {passed}/{len(results)}")
    for r in results:
        status = "[OK]" if r["status"] == "ok" else "[FAIL]"
        print(f"  {status} {r['test']}")

    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
