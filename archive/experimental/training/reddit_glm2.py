import urllib.request, json

HEADERS = {"User-Agent": "ClaudeCode/1.0 by Marco_SuperEzio"}

# Fetch GLM-4.7-Flash thread
print("=== GLM-4.7-FLASH THREAD ===")
url = "https://www.reddit.com/r/LocalLLaMA/comments/1qh5wdq/zaiorgglm47flash_hugging_face/.json?limit=6"
req = urllib.request.Request(url, headers=HEADERS)
try:
    data = json.loads(urllib.request.urlopen(req, timeout=15).read())
    post = data[0]["data"]["children"][0]["data"]
    print(f"Title: {post['title']}")
    print(f"Selftext: {post.get('selftext', '')[:3000]}")
    comments = data[1]["data"]["children"]
    print("\n--- TOP COMMENTS ---")
    for c in comments[:12]:
        if c["kind"] == "t1":
            body = c["data"].get("body", "")[:800]
            score = c["data"]["ups"]
            print(f"\n[+{score}] {body}")
except Exception as e:
    print(f"Error: {e}")

# Fetch GLM-4.6-GGUF thread
import time
time.sleep(1)
print("\n\n=== GLM-4.6-GGUF THREAD ===")
url = "https://www.reddit.com/r/LocalLLaMA/comments/1nv53rb/glm46gguf_is_out/.json?limit=4"
req = urllib.request.Request(url, headers=HEADERS)
try:
    data = json.loads(urllib.request.urlopen(req, timeout=15).read())
    post = data[0]["data"]["children"][0]["data"]
    print(f"Title: {post['title']}")
    print(f"Selftext: {post.get('selftext', '')[:3000]}")
    comments = data[1]["data"]["children"]
    print("\n--- TOP COMMENTS ---")
    for c in comments[:10]:
        if c["kind"] == "t1":
            body = c["data"].get("body", "")[:800]
            score = c["data"]["ups"]
            print(f"\n[+{score}] {body}")
except Exception as e:
    print(f"Error: {e}")

# Fetch GLM-5 thread
time.sleep(1)
print("\n\n=== GLM-5 THREAD ===")
url = "https://www.reddit.com/r/LocalLLaMA/comments/1r22hlq/glm5_officially_released/.json?limit=4"
req = urllib.request.Request(url, headers=HEADERS)
try:
    data = json.loads(urllib.request.urlopen(req, timeout=15).read())
    post = data[0]["data"]["children"][0]["data"]
    print(f"Title: {post['title']}")
    print(f"Selftext: {post.get('selftext', '')[:3000]}")
    comments = data[1]["data"]["children"]
    print("\n--- TOP COMMENTS ---")
    for c in comments[:10]:
        if c["kind"] == "t1":
            body = c["data"].get("body", "")[:800]
            score = c["data"]["ups"]
            print(f"\n[+{score}] {body}")
except Exception as e:
    print(f"Error: {e}")
