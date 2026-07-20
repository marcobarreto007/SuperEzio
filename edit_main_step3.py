content = open('src/agent_server/main.py', encoding='utf-8').read()

# 3. Add trace_id middleware after JWT auth middleware
old_jwt = '@app.middleware("http")\nasync def api_jwt_auth_middleware(request: Request, call_next):\n    return await jwt_auth_middleware(request, call_next)'

new_jwt = '@app.middleware("http")\nasync def api_jwt_auth_middleware(request: Request, call_next):\n    return await jwt_auth_middleware(request, call_next)\n\n\n# ==============================\n# Trace ID middleware\n# ==============================\n\n\n@app.middleware("http")\nasync def trace_id_middleware(request: Request, call_next):\n    """Bind trace_id from header (or generate one) on every request."""\n    trace_id = request.headers.get("X-Trace-ID", "") or uuid.uuid4().hex[:12]\n    bind_trace(trace_id=trace_id)\n    try:\n        response = await call_next(request)\n        return response\n    finally:\n        unbind_trace()'

if old_jwt in content:
    content = content.replace(old_jwt, new_jwt)
    print("Step 3 done: trace_id middleware added")
else:
    print("ERROR: JWT middleware pattern not found")
    # Debug: find similar text
    if '@app.middleware("http")' in content:
        print("Found @app.middleware patterns")
        for line in content.split('\n'):
            if 'jwt' in line.lower():
                print("  JWT line:", line.strip())

open('src/agent_server/main.py', 'w', encoding='utf-8').write(content)
