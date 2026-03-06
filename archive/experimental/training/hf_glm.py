import urllib.request, json, time

HEADERS = {"User-Agent": "ClaudeCode/1.0"}

# Search HF for GLM Flash variants
searches = ["GLM-Flash", "glm-4-flash", "glm4-flash", "GLM-4.5-Flash", "GLM-4.7-Flash", "glm-flash-abliterated", "huihui-glm"]

for s in searches:
    url = f"https://huggingface.co/api/models?search={s}&sort=likes&direction=-1&limit=8"
    req = urllib.request.Request(url, headers=HEADERS)
    try:
        data = json.loads(urllib.request.urlopen(req, timeout=15).read())
        print(f"\n=== Search: {s} ===")
        if not data:
            print("  (no results)")
        for m in data[:8]:
            likes = m.get('likes', 0)
            downloads = m.get('downloads', 0)
            model_id = m['id']
            pipeline_tag = m.get('pipeline_tag', 'N/A')
            created = m.get('createdAt', '')[:10]
            print(f"  {model_id}")
            print(f"    likes={likes}, downloads={downloads}, tag={pipeline_tag}, created={created}")
    except Exception as e:
        print(f"\n=== Search '{s}' FAILED: {e} ===")
    time.sleep(0.5)

# Also get info about zai-org/GLM-4.7-Flash specifically
print("\n\n=== zai-org/GLM-4.7-Flash DETAILS ===")
url = "https://huggingface.co/api/models/zai-org/GLM-4.7-Flash"
req = urllib.request.Request(url, headers=HEADERS)
try:
    data = json.loads(urllib.request.urlopen(req, timeout=15).read())
    for k in ['id', 'author', 'likes', 'downloads', 'pipeline_tag', 'createdAt', 'lastModified', 'library_name', 'model_type']:
        print(f"  {k}: {data.get(k, 'N/A')}")
    # Check siblings for GGUF
    siblings = [s['rfilename'] for s in data.get('siblings', []) if 'gguf' in s['rfilename'].lower() or 'README' in s['rfilename']][:10]
    print(f"  Relevant files: {siblings}")
except Exception as e:
    print(f"Error: {e}")
