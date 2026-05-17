import urllib.request
import json

HEADERS = {"User-Agent": "ClaudeCode/1.0"}

# Check the best GGUF repos for GLM-4.7-Flash abliterated
repos = [
    "DavidAU/GLM-4.7-Flash-Uncensored-Heretic-NEO-CODE-Imatrix-MAX-GGUF",
    "mradermacher/Huihui-GLM-4.7-Flash-abliterated-GGUF",
    "unsloth/GLM-4.7-Flash-GGUF",
]

for repo in repos:
    print(f"\n=== {repo} ===")
    url = f"https://huggingface.co/api/models/{repo}"
    req = urllib.request.Request(url, headers=HEADERS)
    try:
        data = json.loads(urllib.request.urlopen(req, timeout=15).read())
        print(f"  Likes: {data.get('likes', 'N/A')}")
        print(f"  Downloads: {data.get('downloads', 'N/A')}")
        print(f"  Last Modified: {data.get('lastModified', 'N/A')}")
        siblings = data.get("siblings", [])
        # Find GGUF files
        ggufs = [s["rfilename"] for s in siblings if s["rfilename"].endswith(".gguf")]
        if ggufs:
            print(f"  GGUF files ({len(ggufs)}):")
            for g in ggufs[:20]:
                size_mb = "?"
                for s in siblings:
                    if s["rfilename"] == g:
                        size_mb = round(s.get("size", 0) / 1024 / 1024, 2)
                print(f"    {g} ({size_mb} MB)")
    except Exception as e:
        print(f"  Error: {e}")
