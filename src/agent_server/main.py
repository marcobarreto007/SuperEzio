import asyncio
import logging
import os
import sys
import time
from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from sse_starlette.sse import EventSourceResponse

# Auto-detect src/ no sys.path (evita necessidade de PYTHONPATH=src manual)
_SRC = Path(__file__).resolve().parent.parent
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from core.config import get_config  # noqa: E402
from core.config.secrets import load_local_env  # noqa: E402
from core.observability import log_queue, metrics  # noqa: E402
from core.paths import PROJECT_ROOT  # noqa: E402

from .endpoints import router as a2a_router  # noqa: E402

# Load local environment before reading runtime configuration.
# Priority: OS env > .env.local > .env
load_local_env()

logger = logging.getLogger(__name__)

AGENT_NAME = os.getenv("A2A_AGENT_NAME", "generic_agent")
ROOT_DIR = PROJECT_ROOT
FRONTEND_DIR = ROOT_DIR / "frontend"

# Load config early to get the configured port.
try:
    _conf = get_config()
    conf_port = _conf.server.port if _conf and _conf.server else None
except Exception:
    conf_port = None

PORT = int(conf_port or os.getenv("SUPEREZIO_PORT", "8002"))
HOST = os.getenv("SUPEREZIO_HOST", "127.0.0.1")


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


@asynccontextmanager
async def lifespan(app: FastAPI):
    import sys

    logger.info("[%s] Agent Server starting on %s:%s...", AGENT_NAME, HOST, PORT)
    sys.stdout.flush()

    # === BRAIN INITIALIZATION ===
    from core.pipeline import build_graph
    from core.model_serving.gateway import create_gateway

    logger.info("[%s] Compiling pipeline graph v4...", AGENT_NAME)
    sys.stdout.flush()
    gateway = create_gateway()
    app.state.pipeline = build_graph(gateway=gateway)
    logger.info("[%s] Pipeline graph ready.", AGENT_NAME)

    logger.info(
        "[%s] === SERVER READY ON http://localhost:%s ===",
        AGENT_NAME,
        PORT,
    )
    sys.stdout.flush()

    yield

    logger.info("[%s] Agent Server shutting down...", AGENT_NAME)
    if hasattr(app.state, "pipeline") and app.state.pipeline is not None:
        app.state.pipeline.shutdown()


app = FastAPI(
    title=f"A2A Agent: {AGENT_NAME}",
    lifespan=lifespan,
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)
# === CORS CONFIGURATION ===
_configured_origins = getattr(_conf.server, "cors_origins", []) if _conf else []
_cors_origins = [origin for origin in _configured_origins if origin and origin != "*"] or [
    "http://localhost:8002",
    "http://127.0.0.1:8002",
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS", "HEAD"],
    allow_headers=["Authorization", "Content-Type", "X-API-Key"],
)


# === MÃ©tricas de latÃªncia por request ===
@app.middleware("http")
async def metrics_middleware(request: Request, call_next):
    t0 = time.time()
    response = await call_next(request)
    elapsed_s = time.time() - t0
    route = request.url.path or "/"
    metrics.latency(f"http_{request.method}_{route}", elapsed_s)
    if response.status_code >= 400:
        metrics.error(f"http_{request.method}_{route}")
    return response


# === Security headers ===
@app.middleware("http")
async def security_headers_middleware(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "0"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    if request.url.path == "/" or request.url.path.startswith(("/frontend", "/css", "/js")):
        response.headers["Cache-Control"] = "no-store"
    if request.url.scheme == "https":
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    return response


app.include_router(a2a_router)

if FRONTEND_DIR.exists():
    app.mount(
        "/frontend",
        StaticFiles(directory=str(FRONTEND_DIR), html=False),
        name="frontend",
    )
    for static_name in ("css", "js"):
        static_dir = FRONTEND_DIR / static_name
        if static_dir.exists():
            app.mount(
                f"/{static_name}",
                StaticFiles(directory=str(static_dir), html=False),
                name=f"frontend_{static_name}",
            )
else:
    logger.warning("[%s] Frontend directory not found at %s", AGENT_NAME, FRONTEND_DIR)


@app.get("/")
async def root():
    index_path = FRONTEND_DIR / "index.html"
    if index_path.exists():
        return FileResponse(str(index_path), media_type="text/html")
    return {
        "service": "SuperEzio API",
        "status": "frontend_missing",
        "health": "/health",
        "manifest": "/product/manifest",
    }


@app.get("/favicon.ico", include_in_schema=False)
async def favicon():
    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">'
        '<rect width="64" height="64" rx="14" fill="#172018"/>'
        '<text x="32" y="39" text-anchor="middle" '
        'font-family="Arial, sans-serif" font-size="20" font-weight="700" '
        'fill="#ffffff">SE</text>'
        "</svg>"
    )
    return Response(svg, media_type="image/svg+xml")


@app.api_route("/health", methods=["GET", "HEAD"])
async def health_check_public(request: Request):
    """Public liveness probe â€” minimal, no internal config exposure.

    Detailed health (GPU, providers, redis, cost guard, base URLs) is at
    /health/details and requires auth via the edge gateway.
    """
    if request.method == "HEAD":
        return Response(status_code=200)
    return {"status": "ok", "agent": AGENT_NAME, "version": "3.0.0"}


@app.get("/health/details")
async def health_check():
    """Deep health check â€” verifica GPU, modelos, Redis, providers, cache."""
    import socket as _socket
    from core.investor.cost_guard import get_cost_guard
    from core.model_serving.gateway import PRIMARY_PROVIDER_NAME

    health = {
        "status": "ok",
        "agent": AGENT_NAME,
        "version": "3.0.0",
        "checks": {},
    }

    # â”€â”€ GPU â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    gpu_info: dict = {"available": False, "devices": []}
    try:
        import torch

        gpu_info["available"] = torch.cuda.is_available()
        if gpu_info["available"]:
            for i in range(torch.cuda.device_count()):
                props = torch.cuda.get_device_properties(i)
                gpu_info["devices"].append(
                    {
                        "id": i,
                        "name": props.name,
                        "vram_mb": props.total_memory // (1024 * 1024),
                    }
                )
            gpu_info["status"] = "ok"
        else:
            gpu_info["status"] = "unavailable"
    except ImportError:
        gpu_info["status"] = "no_torch"
    health["checks"]["gpu"] = gpu_info

    # â”€â”€ Local models â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    local_models: dict = {}
    for name, url_env, port in [
        ("agent", "SUPEREZIO_AGENT_BASE_URL", 8082),
        ("agent_lora", "SUPEREZIO_AGENT_LORA_BASE_URL", 8082),
    ]:
        url = os.getenv(url_env, "")
        reachable = False
        if url:
            try:
                s = _socket.socket()
                s.settimeout(1)
                host = url.split("://")[-1].split(":")[0] if "://" in url else "127.0.0.1"
                s.connect((host, port))
                s.close()
                reachable = True
            except Exception as exc:
                # Probe failure expected when local model is offline; record reason.
                logger.debug("[%s] local model probe failed (%s): %s", AGENT_NAME, name, exc)
        local_models[name] = {
            "url": url or None,
            "reachable": reachable,
            "status": "ok" if reachable else ("unconfigured" if not url else "down"),
        }
    health["checks"]["local_models"] = local_models

    # â”€â”€ Redis â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    redis_info: dict = {"status": "skipped"}
    try:
        import redis

        redis_url = os.getenv("MEM0_REDIS_URL", "")
        if redis_url:
            r = redis.from_url(redis_url, socket_connect_timeout=2)
            if r.ping():
                redis_info = {
                    "status": "ok",
                    "url": redis_url.split("@")[-1] if "@" in redis_url else redis_url,
                }
            else:
                redis_info = {
                    "status": "no_pong",
                    "url": redis_url.split("@")[-1] if "@" in redis_url else redis_url,
                }
    except ImportError:
        redis_info = {"status": "no_driver"}
    except Exception as exc:
        redis_info = {"status": "error", "detail": str(exc)[:120]}
    health["checks"]["redis"] = redis_info

    # â”€â”€ Model providers â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    primary_info = {
        "configured": bool(
            os.getenv("SUPEREZIO_PRIMARY_API_KEY") or os.getenv("SUPEREZIO_DEEPSEEK_API_KEY")
        ),
        "provider": PRIMARY_PROVIDER_NAME,
        "model": os.getenv(
            "SUPEREZIO_PRIMARY_MODEL",
            os.getenv("SUPEREZIO_DEEPSEEK_MODEL", "deepseek-chat"),
        ),
        "base_url": os.getenv(
            "SUPEREZIO_PRIMARY_BASE_URL",
            os.getenv("SUPEREZIO_DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
        ),
    }
    try:
        pipeline = getattr(app.state, "pipeline", None)
        gateway = getattr(pipeline, "gateway", None)
        providers = list(getattr(gateway, "providers", []))
        for p in providers:
            key = p.name
            health["checks"][f"provider_{key}"] = {
                "configured": bool((p.api_key or "").strip()),
                "model": p.model,
                "base_url": p.base_url,
                "priority": p.priority,
            }
    except Exception as exc:
        logger.warning("[%s] provider summary unavailable: %s", AGENT_NAME, exc)
        health["checks"]["providers_introspection_error"] = str(exc)[:200]

    health["checks"]["providers_summary"] = {
        "primary": primary_info,
        "deepseek": {
            "configured": bool(os.getenv("SUPEREZIO_DEEPSEEK_API_KEY")),
            "model": os.getenv("SUPEREZIO_DEEPSEEK_MODEL", "deepseek-chat"),
        },
    }

    # â”€â”€ Cost guard â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    try:
        health["checks"]["cost_guard"] = get_cost_guard().status()
    except Exception as exc:
        logger.warning("[%s] cost_guard status unavailable: %s", AGENT_NAME, exc)
        health["checks"]["cost_guard"] = {
            "error": "unavailable",
            "detail": str(exc)[:200],
        }

    # â”€â”€ Aggregated status â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    all_ok = primary_info["configured"] or any(m["reachable"] for m in local_models.values())
    health["status"] = "ok" if all_ok else "degraded_no_backend"
    return health


def run():
    uvicorn.run(app, host=HOST, port=PORT)


@app.get("/metrics")
async def get_metrics():
    """MÃ©tricas de negÃ³cio: latÃªncia, erro rate, tokens, cache."""
    return {
        "service": "superezio",
        "version": "3.0.0",
        **metrics.get_all(),
    }


# === Observability ===
@app.get("/neural/logs")
async def stream_logs(request: Request):
    """SSE endpoint consumed by API clients."""

    async def event_generator():
        while True:
            if await request.is_disconnected():
                break
            if not log_queue.empty():
                log_entry = log_queue.get()
                yield f"data: {log_entry}\n\n"
            await asyncio.sleep(0.1)

    return EventSourceResponse(event_generator())


if __name__ == "__main__":
    run()
