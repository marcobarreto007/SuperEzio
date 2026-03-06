import urllib.request, urllib.parse, json, sys, time

HEADERS = {"User-Agent": "ClaudeCode/1.0 by Marco_SuperEzio"}

def fetch_reddit_thread(permalink):
    """Fetch a Reddit thread via JSON API and extract top-level info."""
    url = f"https://www.reddit.com{permalink}.json?limit=1"
    req = urllib.request.Request(url, headers=HEADERS)
    try:
        data = json.loads(urllib.request.urlopen(req, timeout=15).read())
        post_data = data[0]["data"]["children"][0]["data"]
        return {
            "title": post_data["title"],
            "selftext": post_data.get("selftext", "")[:3000],
            "score": post_data["score"],
            "num_comments": post_data["num_comments"],
            "url": post_data.get("url", ""),
        }
    except Exception as e:
        return {"error": str(e)}

threads = [
    "/r/LocalLLaMA/comments/1lbrnod/jannano_a_4b_model_that_can_outperform_671b_on_mcp/",
    "/r/LocalLLaMA/comments/1oqebr3/worlds_strongest_agentic_model_is_now_open_source/",
    "/r/LocalLLaMA/comments/1suqfba/this_is_where_we_are_right_now_localllama/",
]

for t in threads:
    info = fetch_reddit_thread(t)
    print(f"\n{'='*60}")
    print(f"TITLE: {info.get('title', 'N/A')}")
    print(f"SCORE: {info.get('score', 'N/A')}")
    print(f"TEXT: {info.get('selftext', 'N/A')[:2000]}")
    print(f"LINK: {info.get('url', 'N/A')}")
    time.sleep(1)

# Also try to get comments for the most relevant thread
print("\n\n=== COMMENTS for Jan-nano thread ===")
url = "https://www.reddit.com/r/LocalLLaMA/comments/1lbrnod/jannano_a_4b_model_that_can_outperform_671b_on_mcp/.json?limit=15&sort=top"
req = urllib.request.Request(url, headers=HEADERS)
try:
    data = json.loads(urllib.request.urlopen(req, timeout=15).read())
    comments = data[1]["data"]["children"]
    for c in comments[:10]:
        if c["kind"] == "t1":
            body = c["data"].get("body", "")[:500]
            score = c["data"]["ups"]
            print(f"\n[+{score}] {body}")
except Exception as e:
    print(f"Comments error: {e}")
