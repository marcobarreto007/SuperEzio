content = open('src/agent_server/main.py', encoding='utf-8').read()

# Add health dashboard routes to public set
old_public = '_PUBLIC_EXACT = frozenset(\n    {\n        "/health",\n        "/favicon.ico",\n        "/",\n        "/metrics",\n    }\n)'
new_public = '_PUBLIC_EXACT = frozenset(\n    {\n        "/health",\n        "/health/dashboard",\n        "/api/health/dashboard-data",\n        "/favicon.ico",\n        "/",\n        "/metrics",\n    }\n)'

if old_public in content:
    content = content.replace(old_public, new_public)
    print("Public routes updated")
else:
    print("ERROR: public routes pattern not found")

open('src/agent_server/main.py', 'w', encoding='utf-8').write(content)
print("main.py public routes done")
