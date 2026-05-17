import urllib.request
import urllib.parse
import json
import time

HEADERS = {"User-Agent": "ClaudeCode/1.0 by Marco_SuperEzio"}

queries = [
    "GLM Flash LLM",
    "GLM Flash 2025 2026 local",
    "GLM 4 Flash abliterated",
    "GLM Flash agent tool use function calling",
    "huihui GLM Flash abliterated",
    "GLM Flash vs Qwen agentic",
]

for query in queries:
    encoded = urllib.parse.quote(query)
    url = f"https://www.reddit.com/r/LocalLLaMA/search.json?q={encoded}&sort=top&restrict_sr=on&t=year&limit=8"
    req = urllib.request.Request(url, headers=HEADERS)
    try:
        data = json.loads(urllib.request.urlopen(req, timeout=15).read())
        print(f"\n=== Search: {query} ===")
        if not data["data"]["children"]:
            print("  (no results)")
        for post in data["data"]["children"]:
            title = post["data"]["title"]
            score = post["data"]["score"]
            comments = post["data"]["num_comments"]
            permalink = post["data"]["permalink"]
            print(f"[+{score}, {comments}c] {title}")
            print(f"  https://reddit.com{permalink}")
    except Exception as e:
        print(f"\n=== Search '{query}' FAILED: {e} ===")
    time.sleep(1)
