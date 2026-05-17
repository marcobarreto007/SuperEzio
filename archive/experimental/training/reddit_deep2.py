import urllib.request
import urllib.parse
import json
import time

HEADERS = {"User-Agent": "ClaudeCode/1.0 by Marco_SuperEzio"}

# Fetch the world's strongest agentic model thread
print("=== WORLD'S STRONGEST AGENTIC MODEL THREAD ===")
url = "https://www.reddit.com/r/LocalLLaMA/comments/1oqebr3/worlds_strongest_agentic_model_is_now_open_source/.json?limit=3"
req = urllib.request.Request(url, headers=HEADERS)
try:
    data = json.loads(urllib.request.urlopen(req, timeout=15).read())
    post_data = data[0]["data"]["children"][0]["data"]
    print(f"Title: {post_data['title']}")
    print(f"Selftext: {post_data.get('selftext', '')[:3000]}")
    print(f"URL: {post_data.get('url', '')}")
    # Get top comments
    comments = data[1]["data"]["children"]
    for c in comments[:15]:
        if c["kind"] == "t1":
            body = c["data"].get("body", "")[:600]
            score = c["data"]["ups"]
            print(f"\n[+{score}] {body}")
except Exception as e:
    print(f"Error: {e}")

time.sleep(1)

# Search for abliterated models specifically
print("\n\n=== ABLITERATED MODELS SEARCH ===")
for query in ["abliterated 2026", "uncensored model tool use", "abliterated qwen", "huihui-ai abliterated"]:
    encoded = urllib.parse.quote(query)
    url = f"https://www.reddit.com/r/LocalLLaMA/search.json?q={encoded}&sort=top&restrict_sr=on&t=year&limit=8"
    req = urllib.request.Request(url, headers=HEADERS)
    try:
        data = json.loads(urllib.request.urlopen(req, timeout=15).read())
        print(f"\n--- Search: {query} ---")
        for post in data["data"]["children"]:
            title = post["data"]["title"]
            score = post["data"]["score"]
            comments = post["data"]["num_comments"]
            permalink = post["data"]["permalink"]
            print(f"[+{score}, {comments}c] {title}")
            print(f"  https://reddit.com{permalink}")
    except Exception as e:
        print(f"Error for '{query}': {e}")
    time.sleep(1)
