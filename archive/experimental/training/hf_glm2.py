import urllib.request, json, time

HEADERS = {"User-Agent": "ClaudeCode/1.0"}

# Get model card/readme for GLM-4.7-Flash
print("=== GLM-4.7-Flash README ===")
url = "https://huggingface.co/api/models/zai-org/GLM-4.7-Flash"
req = urllib.request.Request(url, headers=HEADERS)
try:
    data = json.loads(urllib.request.urlopen(req, timeout=15).read())
    # Get the README content
    readme_url = f"https://huggingface.co/zai-org/GLM-4.7-Flash/raw/main/README.md"
    req2 = urllib.request.Request(readme_url, headers=HEADERS)
    readme = urllib.request.urlopen(req2, timeout=15).read().decode('utf-8')
    print(readme[:4000])
except Exception as e:
    print(f"Error: {e}")

time.sleep(1)

# Get config.json for model architecture details
print("\n\n=== GLM-4.7-Flash CONFIG ===")
url = "https://huggingface.co/zai-org/GLM-4.7-Flash/raw/main/config.json"
req = urllib.request.Request(url, headers=HEADERS)
try:
    config = json.loads(urllib.request.urlopen(req, timeout=15).read())
    for k in ['hidden_size', 'num_hidden_layers', 'num_attention_heads', 'num_key_value_heads',
              'intermediate_size', 'max_position_embeddings', 'torch_dtype', 'vocab_size',
              'architectures', 'rope_theta', 'model_type', 'num_experts', 'num_experts_per_tok',
              'moe_intermediate_size', 'first_k_dense_replace', 'n_layer', 'n_head']:
        if k in config:
            print(f"  {k}: {config[k]}")
except Exception as e:
    print(f"Error: {e}")

time.sleep(1)

# Search for GLM Flash tool use / function calling discussions
print("\n\n=== GLM TOOL USE / FUNCTION CALLING SEARCH ===")
searches = ["GLM function calling", "GLM Flash agent", "GLM 4.7 tool use", "GLM Flash MCP"]
for s in searches:
    url = f"https://huggingface.co/api/models?search={s}&sort=likes&direction=-1&limit=5"
    req = urllib.request.Request(url, headers=HEADERS)
    try:
        data = json.loads(urllib.request.urlopen(req, timeout=15).read())
        print(f"\n--- HF Search: {s} ---")
        for m in data[:4]:
            print(f"  {m['id']} | {m.get('likes',0)} likes")
    except Exception as e:
        print(f"  Error: {e}")
    time.sleep(0.5)
