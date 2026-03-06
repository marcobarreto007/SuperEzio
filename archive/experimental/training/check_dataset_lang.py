"""Check language distribution in f51_final_sft.jsonl."""
import json

PT_WORDS = [
    "voce", "nao", "para", "como", "uma", "mais", "anos", "mes",
    "tambem", "sera", "esta", "muito", "isso", "esse", "essa",
    "pra", "ne", "daqui", "porque", "ainda", "acao", "acoes",
    "mercado", "analise", "dados", "entao", "sobre", "pode",
    "fazer", "qual", "sao", "esta", "entre",
]

pt_user = 0
en_user = 0
total = 0
en_samples = []

with open("/root/f51_final_sft.jsonl") as f:
    for line in f:
        total += 1
        if total > 10000:
            break
        try:
            entry = json.loads(line)
            msgs = entry.get("messages", [])
            for m in msgs:
                if m.get("role") == "user":
                    content = m.get("content", "").lower()
                    has_pt = sum(1 for w in PT_WORDS if w in content)
                    if has_pt >= 2:
                        pt_user += 1
                    else:
                        en_user += 1
                        if len(en_samples) < 5:
                            en_samples.append(content[:200])
                    break
        except Exception:
            pass

print(f"Total sampled: {total}")
print(f"English user messages: {en_user} ({100*en_user/total:.1f}%)")
print(f"Portuguese user messages: {pt_user} ({100*pt_user/total:.1f}%)")
print()
print("--- Sample English user msgs ---")
for i, s in enumerate(en_samples):
    print(f"[{i}] {s}")
print()
print("--- Sample Portuguese user msgs ---")
pt_samples = []
with open("/root/f51_final_sft.jsonl") as f:
    for line in f:
        try:
            entry = json.loads(line)
            msgs = entry.get("messages", [])
            for m in msgs:
                if m.get("role") == "user":
                    content = m.get("content", "")
                    has_pt = sum(1 for w in PT_WORDS if w in content.lower())
                    if has_pt >= 2 and len(pt_samples) < 5:
                        pt_samples.append(content[:200])
                    break
        except Exception:
            pass
for i, s in enumerate(pt_samples):
    print(f"[{i}] {s}")

# Check full message language distribution
print()
print("--- Full message check (first 20 entries) ---")
with open("/root/f51_final_sft.jsonl") as f:
    for i, line in enumerate(f):
        if i >= 20:
            break
        try:
            entry = json.loads(line)
            msgs = entry.get("messages", [])
            for m in msgs:
                role = m.get("role", "?")
                content = m.get("content", "")
                has_pt = sum(1 for w in PT_WORDS if w in content.lower())
                lang = "PT" if has_pt >= 2 else "EN"
                print(f"  [{i}] {role}: {lang} | {content[:120]}...")
        except Exception:
            pass
