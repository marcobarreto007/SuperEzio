content = open('src/agent_server/main.py', encoding='utf-8').read()

# 4. Enhance metrics_middleware with access log
old_metrics = '@app.middleware("http")\nasync def metrics_middleware(request: Request, call_next):\n    t0 = time.time()\n    response = await call_next(request)\n    elapsed_s = time.time() - t0\n    route = request.url.path or "/"\n    metrics.latency(f"http_{request.method}_{route}", elapsed_s)\n    if response.status_code >= 400:\n        metrics.error(f"http_{request.method}_{route}")\n    return response'

new_metrics = '@app.middleware("http")\nasync def metrics_middleware(request: Request, call_next):\n    t0 = time.time()\n    response = await call_next(request)\n    elapsed_s = time.time() - t0\n    elapsed_ms = round(elapsed_s * 1000, 2)\n    route = request.url.path or "/"\n    metrics.latency(f"http_{request.method}_{route}", elapsed_s)\n    if response.status_code >= 400:\n        metrics.error(f"http_{request.method}_{route}")\n    # Access log: every HTTP request logged with method, path, status, latency\n    logger.info(\n        "http_access",\n        method=request.method,\n        path=route,\n        status=response.status_code,\n        latency_ms=elapsed_ms,\n    )\n    return response'

if old_metrics in content:
    content = content.replace(old_metrics, new_metrics)
    print("Step 4 done: access log added to metrics middleware")
else:
    print("ERROR: metrics middleware pattern not found")
    # Show surrounding text
    idx = content.find('async def metrics_middleware')
    if idx >= 0:
        print("Found at", idx)
        print(repr(content[idx:idx+500]))

open('src/agent_server/main.py', 'w', encoding='utf-8').write(content)
