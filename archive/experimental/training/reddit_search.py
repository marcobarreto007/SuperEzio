import urllib.request, urllib.parse, json, sys

# Search 1: Abliterated models for tool use
queries = [
    "abliterated tool orchestration agent",
    "best small model function calling agent 2026",
    "small local model tool use agent",
]

for q in queries:
    encoded = urllib.parse.quote(q)
    url = f"https://www.reddit.com/r/LocalLLaMA/search.json?q={encoded}&sort=top&restrict_sr=on&t=year&limit=10"
    req = urllib.request.Request(url, headers={"User-Agent": "ClaudeCode/1.0"})
    try:
        data = json.loads(urllib.request.urlopen(req, timeout=15).read())
        print(f"\n=== SEARCH: {q} ===")
        for post in data["data"]["children"]:
            title = post["data"]["title"]
            score = post["data"]["score"]
            num_comments = post["data"]["num_comments"]
            print(f"[{score} pts, {num_comments} comments] {title}")
            print(f"  https://reddit.com{post['data']['permalink']}")
    except Exception as e:
        print(f"\n=== SEARCH FAILED: {q} ===")
        print(f"Error: {e}", file=sys.stderr)
