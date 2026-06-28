import asyncio
import logging
import math
import os
import sys
import time
from copy import deepcopy
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
from core.investor.storage import get_investor_storage  # noqa: E402
from core.mission_context import mission_health_summary  # noqa: E402
from core.observability import log_queue, metrics  # noqa: E402
from core.paths import PROJECT_ROOT  # noqa: E402
from core.sentiment import LiveMonitor, SentimentCurator, WatchlistPulse  # noqa: E402

from .endpoints import router as a2a_router  # noqa: E402

# Load local environment before reading runtime configuration.
# Priority: OS env > .env.local > .env
load_local_env()

logger = logging.getLogger(__name__)


def _json_safe(value):
    """Return a JSON-compliant copy by replacing NaN/Infinity with None."""
    if isinstance(value, dict):
        return {key: _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if isinstance(value, tuple):
        return [_json_safe(item) for item in value]
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    return value

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


def _clean_watchlist_ticker(value: object) -> str:
    return "".join(ch for ch in str(value or "").strip().upper() if ch.isalnum() or ch in ".-")


def _overlay_runtime_broker_snapshot(
    mission: dict,
    portfolio: dict | None,
) -> dict:
    """Overlay static mission broker data with the live cockpit broker snapshot.

    The mission JSON is product posture. It must not be the source of truth for
    account equity, positions, or open orders once the broker service is live.
    """

    if not isinstance(mission, dict) or not isinstance(portfolio, dict):
        return mission

    merged = deepcopy(mission)
    broker = merged.setdefault("broker", {})
    if not isinstance(broker, dict):
        broker = {}
        merged["broker"] = broker
    ibkr = dict(broker.get("ibkr") or {})

    raw_mode = str(portfolio.get("mode") or ibkr.get("mode") or "").lower()
    raw_connection = str(portfolio.get("connection") or ibkr.get("connection") or "")
    connected = portfolio.get("connected") is True or "connected" in raw_connection
    paper = portfolio.get("paper") is True or "paper" in raw_mode or raw_connection == "connected_paper"
    can_submit = portfolio.get("can_submit_orders") is True and paper

    if connected and paper:
        connection = "connected_paper"
        mode = "paper_order_enabled" if can_submit else "paper_read_only"
    elif connected:
        connection = "connected_live_blocked"
        mode = "live_blocked"
        can_submit = False
    else:
        connection = raw_connection or "offline"
        mode = "offline"
        can_submit = False

    equity = portfolio.get("equity")
    positions_count = portfolio.get("positions_count")
    positions = portfolio.get("positions")
    orders_count = portfolio.get("orders_count")
    broker_orders_count = portfolio.get("broker_orders_count")

    ibkr.update(
        {
            "provider": portfolio.get("provider") or ibkr.get("provider") or "IBKR",
            "connection": connection,
            "mode": mode,
            "paper_port": paper,
            "live_port_warning": bool(connected and not paper),
            "account_equity": str(equity) if equity is not None else ibkr.get("account_equity", "unknown"),
            "positions_count": positions_count if positions_count is not None else ibkr.get("positions_count", 0),
            "positions": positions if isinstance(positions, list) else ibkr.get("positions", []),
            "orders_count": orders_count if orders_count is not None else ibkr.get("orders_count", 0),
            "broker_orders_count": (
                broker_orders_count if broker_orders_count is not None else ibkr.get("broker_orders_count", 0)
            ),
            "can_read_account": bool(connected),
            "can_read_positions": bool(connected),
            "can_submit_orders": bool(can_submit),
            "verified_at": portfolio.get("verified_at") or time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "verification_source": "cockpit_portfolio_live",
            "runtime_source": "cockpit_portfolio",
            "orders_source": portfolio.get("orders_source") or ibkr.get("orders_source", "unknown"),
        }
    )
    broker["ibkr"] = ibkr

    paper_trading = merged.get("paper_trading")
    if isinstance(paper_trading, dict) and equity is not None:
        paper_trading["equity"] = f"{equity} USD"

    return merged


def _load_sentiment_watchlist(storage=None) -> list[str]:
    raw = os.getenv("SUPEREZIO_SENTIMENT_WATCHLIST", "").strip()
    if raw:
        parsed = [_clean_watchlist_ticker(item) for item in raw.split(",")]
        return list(dict.fromkeys(ticker for ticker in parsed if ticker))

    try:
        store = storage or get_investor_storage()
        rows = store.get_watchlist()
    except Exception as exc:
        logger.warning("[%s] sentiment watchlist unavailable: %s", AGENT_NAME, exc)
        return []

    tickers: list[str] = []
    for row in rows:
        ticker = row.get("ticker") if isinstance(row, dict) else None
        clean = _clean_watchlist_ticker(ticker)
        if clean:
            tickers.append(clean)
    return list(dict.fromkeys(tickers))


def _sentiment_interval_minutes() -> int:
    raw = os.getenv("SUPEREZIO_SENTIMENT_INTERVAL_MINUTES", "15")
    try:
        return max(1, int(raw))
    except (TypeError, ValueError):
        logger.warning("[%s] invalid SUPEREZIO_SENTIMENT_INTERVAL_MINUTES=%r; using 15", AGENT_NAME, raw)
        return 15


def _start_sentiment_services(app: FastAPI) -> None:
    watchlist = _load_sentiment_watchlist()
    monitor = LiveMonitor(watchlist, interval_minutes=_sentiment_interval_minutes())
    curator = SentimentCurator()
    pulse = WatchlistPulse(monitor, curator)

    app.state.sentiment_monitor = monitor
    app.state.sentiment_curator = curator
    app.state.sentiment_pulse = pulse
    monitor.start()
    logger.info("[%s] Sentiment monitor started for %d tickers.", AGENT_NAME, len(watchlist))


def _stop_sentiment_services(app: FastAPI) -> None:
    monitor = getattr(app.state, "sentiment_monitor", None)
    if monitor is not None:
        monitor.stop()


@asynccontextmanager
async def lifespan(app: FastAPI):
    import sys

    # Configure structured logging FIRST (before any logger is used)
    try:
        from core.config.logging_config import configure_logging
        configure_logging()
        logger.info("structlog_configured: ok")
    except Exception as exc:
        logger.warning("structlog_configuration_failed: %s", str(exc)[:200])

    logger.info("[%s] Agent Server starting on %s:%s...", AGENT_NAME, HOST, PORT)
    sys.stdout.flush()

    # Validate settings at boot — crash early if env vars are misconfigured
    try:
        from core.config.settings import get_settings
        _settings = get_settings()
        logger.info(
            "settings_validated: freeze=%s paper_submit=%s",
            _settings.f51_trading_execution_freeze,
            _settings.superezio_enable_paper_order_submit,
        )
    except Exception as exc:
        logger.critical("settings_validation_failed: %s", str(exc)[:200])
        raise

    # === BRAIN INITIALIZATION ===
    from core.pipeline import build_graph
    from core.model_serving.gateway import create_gateway

    logger.info("[%s] Compiling pipeline graph v4...", AGENT_NAME)
    sys.stdout.flush()
    gateway = create_gateway()
    app.state.pipeline = build_graph(gateway=gateway)
    logger.info("[%s] Pipeline graph ready.", AGENT_NAME)
    _start_sentiment_services(app)

    logger.info(
        "[%s] === SERVER READY ON http://localhost:%s ===",
        AGENT_NAME,
        PORT,
    )
    sys.stdout.flush()

    # ── Start Bob's Autonomic Nervous System (background health monitor) ──
    try:
        from core.bob_consciousness import start_ans
        start_ans()
        logger.info("[%s] Bob's autonomic nervous system started — heartbeat active", AGENT_NAME)
    except Exception as exc:
        logger.warning("[%s] Bob ANS failed to start: %s", AGENT_NAME, str(exc)[:200])

    yield

    # ── Stop Bob's ANS ──
    try:
        from core.bob_consciousness import stop_ans
        stop_ans()
    except Exception:
        pass

    logger.info("[%s] Agent Server shutting down...", AGENT_NAME)
    _stop_sentiment_services(app)
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


# ═══════════════════════════════════════════════════════════════
# Bob's Body — Health endpoint for his autonomic nervous system
# ═══════════════════════════════════════════════════════════════

@app.get("/bob/health")
async def bob_health():
    """Bob's full body scan — all organs, pain levels, sick count."""
    try:
        from core.bob_consciousness import bob_body_scan, get_ans
        report = bob_body_scan()
        ans = get_ans()
        return {
            "bob": "alive",
            "organs": report["organs"],
            "healthy": report["healthy_count"],
            "sick": report["sick_count"],
            "critical": report["critical_count"],
            "pain": report["overall_pain"],
            "scans": report.get("scan_id", ""),
            "ans": ans.status,
        }
    except Exception as e:
        return {"bob": "unconscious", "error": str(e)[:200]}

@app.get("/bob/pain")
async def bob_pain():
    """Bob's pain summary — human-readable status of every organ."""
    try:
        from core.bob_consciousness import bob_pain_summary
        return {"pain_report": bob_pain_summary()}
    except Exception as e:
        return {"pain_report": f"Bob is unconscious: {str(e)[:200]}"}

@app.get("/bob/heal")
async def bob_heal():
    """Bob tries to heal himself — scan + heal + rescan cycle."""
    try:
        from core.bob_consciousness import get_bobs_body
        body = get_bobs_body()
        result = body.heal_and_rescan()
        return {
            "healed": result["organs_healed"],
            "still_sick": result["still_sick"],
            "details": result["heal_attempts"],
        }
    except Exception as e:
        return {"healed": 0, "error": str(e)[:200]}


# ═══════════════════════════════════════════════════════════════
# Prometheus /metrics endpoint — Quality Engineering 2026
# ═══════════════════════════════════════════════════════════════
_PROMETHEUS_AVAILABLE = False
try:
    from prometheus_client import (
        Counter,
        Gauge,
        Histogram,
        generate_latest,
        REGISTRY,
    )

    _PROMETHEUS_AVAILABLE = True

    # Business metrics
    superezio_orders_total = Counter(
        "superezio_orders_total",
        "Total de ordens processadas pelo F51 Trade Gate",
        ["status", "ticker"],
    )
    superezio_gate_failures_total = Counter(
        "superezio_gate_failures_total",
        "Falhas por gate de segurança",
        ["gate", "reason_code"],
    )
    superezio_execution_freeze = Gauge(
        "superezio_execution_freeze",
        "1 se FREEZE está ativo, 0 caso contrário",
    )
    superezio_ibkr_connectivity = Gauge(
        "superezio_ibkr_connectivity",
        "1 se IBKR está reachable, 0 caso contrário",
    )
    superezio_journal_health = Gauge(
        "superezio_journal_health",
        "1 se journal está writable, 0 caso contrário",
    )
    superezio_dead_letters_pending = Gauge(
        "superezio_dead_letters_pending",
        "Número de ordens na dead letter queue",
    )
    superezio_pipeline_duration_seconds = Histogram(
        "superezio_pipeline_duration_seconds",
        "Latência do pipeline completo",
        buckets=[0.1, 0.5, 1, 2, 5, 10, 30, 60],
    )
except ImportError:
    pass


@app.get("/metrics/prometheus", include_in_schema=False)
async def prometheus_metrics_endpoint():
    """Prometheus metrics endpoint — business + infrastructure health."""
    if not _PROMETHEUS_AVAILABLE:
        return Response(
            content="# Prometheus metrics unavailable (prometheus_client not installed)\n",
            media_type="text/plain",
            status_code=503,
        )

    # Update live gauges
    try:
        from core.config.settings import is_frozen
        superezio_execution_freeze.set(1 if is_frozen() else 0)
    except Exception:
        superezio_execution_freeze.set(1)  # SAFE: assume frozen

    try:
        from core.pipeline.f51_trade_gate import is_ibkr_connectable, is_journal_healthy
        superezio_ibkr_connectivity.set(1 if is_ibkr_connectable() else 0)
        superezio_journal_health.set(1 if is_journal_healthy() else 0)
    except Exception:
        superezio_ibkr_connectivity.set(0)
        superezio_journal_health.set(0)

    try:
        from core.idempotency import count_dead_letters
        superezio_dead_letters_pending.set(count_dead_letters())
    except Exception:
        superezio_dead_letters_pending.set(-1)

    return Response(
        content=generate_latest(REGISTRY),
        media_type="text/plain; version=0.0.4; charset=utf-8",
    )

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
    return {"status": "ok", "agent": AGENT_NAME, "version": "4.0.0"}


@app.get("/health/details")
async def health_check():
    """Deep health check â€” verifica GPU, modelos, Redis, providers, cache."""
    import socket as _socket
    from core.investor.cost_guard import get_cost_guard
    from core.model_serving.gateway import PRIMARY_PROVIDER_NAME

    health = {
        "status": "ok",
        "agent": AGENT_NAME,
        "version": "4.0.0",
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
    mission = mission_health_summary()
    try:
        from .endpoints import _cockpit_portfolio_snapshot

        portfolio = _cockpit_portfolio_snapshot()
        health["mission"] = _overlay_runtime_broker_snapshot(mission, portfolio)
        health["checks"]["runtime_broker"] = {
            "source": "cockpit_portfolio",
            "status": "ok" if portfolio.get("connected") else "offline",
            "mode": portfolio.get("mode"),
            "paper": portfolio.get("paper"),
            "equity": portfolio.get("equity"),
            "positions_count": portfolio.get("positions_count", 0),
            "orders_count": portfolio.get("orders_count", 0),
        }
    except Exception as exc:
        logger.warning("[%s] runtime broker overlay unavailable: %s", AGENT_NAME, exc)
        health["mission"] = mission
        health["checks"]["runtime_broker"] = {
            "source": "cockpit_portfolio",
            "status": "unavailable",
            "error": str(exc)[:200],
        }

    all_ok = primary_info["configured"] or any(m["reachable"] for m in local_models.values())
    health["status"] = "ok" if all_ok else "degraded_no_backend"
    return _json_safe(health)


def run():
    uvicorn.run(app, host=HOST, port=PORT)


@app.get("/metrics")
async def get_metrics():
    """Métricas de negócio: latência, erro rate, tokens, cache, Prometheus."""
    base = _json_safe({
        "service": "superezio",
        "version": "4.0.0",
        **metrics.get_all(),
    })
    # Add Prometheus discoverability
    try:
        from core.config.settings import is_frozen
        base["trading_frozen"] = is_frozen()
    except Exception:
        base["trading_frozen"] = True
    base["prometheus_endpoint"] = "/metrics/prometheus"
    return base


# ═══════════════════════════════════════════════════════════════
# Dashboard HTML — Quality Engineering 2026
# ═══════════════════════════════════════════════════════════════


@app.get("/dashboard", include_in_schema=False)
async def dashboard():
    """HTML dashboard with live business metrics."""
    html = """<!DOCTYPE html>
<html lang="pt">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>SuperEzio — Quality Dashboard</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:system-ui,-apple-system,Segoe UI,sans-serif;background:#0a0a0f;color:#e0e0e0;padding:24px}
h1{font-size:28px;margin-bottom:8px;color:#00d4aa}
.sub{color:#888;margin-bottom:24px}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:16px}
.card{background:#14141f;border:1px solid #2a2a3f;border-radius:12px;padding:20px}
.card h3{font-size:14px;color:#888;text-transform:uppercase;letter-spacing:1px;margin-bottom:12px}
.card .value{font-size:36px;font-weight:700;color:#00d4aa}
.card .value.red{color:#ff4466}
.card .value.yellow{color:#ffaa22}
.card .meta{font-size:13px;color:#666;margin-top:8px}
.card .label{display:flex;justify-content:space-between;padding:6px 0;border-bottom:1px solid #1a1a2f;font-size:14px}
.card .label span:first-child{color:#999}
.card .label span:last-child{color:#00d4aa;font-weight:600}
.footer{margin-top:24px;color:#555;font-size:12px;text-align:center}
.refresh{cursor:pointer;background:#00d4aa;color:#000;border:none;padding:8px 20px;border-radius:8px;font-weight:600;margin-top:16px}
.stale{color:#ffaa22 !important}
.gates{display:flex;flex-wrap:wrap;gap:8px;margin-top:12px}
.gate{padding:4px 12px;border-radius:6px;font-size:12px;font-weight:600}
.gate-pass{background:#0a3a2a;color:#00d4aa}
.gate-fail{background:#3a0a0a;color:#ff4466}
</style>
</head>
<body>
<h1>📊 SuperEzio Quality Dashboard</h1>
<p class="sub">Métricas em tempo real — F51 Trade Gate + Pipeline + Dead Letter</p>
<div class="grid">
  <div class="card" id="freeze-card">
    <h3>🔒 Execution Freeze</h3>
    <div class="value" id="freeze-value">—</div>
    <div class="meta">Kill switch global</div>
  </div>
  <div class="card" id="ibkr-card">
    <h3>📡 IBKR Connectivity</h3>
    <div class="value" id="ibkr-value">—</div>
    <div class="meta">TWS/Gateway status</div>
  </div>
  <div class="card" id="journal-card">
    <h3>📝 Journal Health</h3>
    <div class="value" id="journal-value">—</div>
    <div class="meta">Paper journal writable</div>
  </div>
  <div class="card" id="dead-letter-card">
    <h3>💀 Dead Letters</h3>
    <div class="value" id="dead-letter-value">—</div>
    <div class="meta">Ordens na fila de replay</div>
  </div>
  <div class="card" id="orders-card">
    <h3>📋 Ordens (24h)</h3>
    <div class="label"><span>Permitidas</span><span id="orders-allowed">—</span></div>
    <div class="label"><span>Bloqueadas</span><span id="orders-blocked">—</span></div>
    <div class="meta">Via F51 Trade Gate</div>
  </div>
  <div class="card" id="gates-card">
    <h3>🚦 Última Decisão</h3>
    <div id="gates-container"><span class="meta">Nenhuma ordem recente</span></div>
    <div class="meta" id="last-decision"></div>
  </div>
</div>
<button class="refresh" onclick="fetchMetrics()">🔄 Atualizar</button>
<div class="footer">SuperEzio v4.0.0 · Quality Engineering 2026 · <span id="updated"></span></div>
<script>
async function fetchMetrics() {
  try {
    // Fetch Prometheus metrics as text
    const resp = await fetch('/metrics/prometheus');
    const text = await resp.text();
    const lines = text.split('\\n');

    const get = (name) => {
      const line = lines.find(l => l.startsWith(name + ' ')) || '';
      return line.split(' ').pop() || '0';
    };

    // Gauges
    const freeze = get('superezio_execution_freeze');
    const ibkr = get('superezio_ibkr_connectivity');
    const journal = get('superezio_journal_health');
    const deadLetters = get('superezio_dead_letters_pending');

    // Counters
    const ordersAllowed = get('superezio_orders_total{status="allowed"') || '0';
    const ordersBlocked = get('superezio_orders_total{status="blocked"') || '0';

    // Render
    document.getElementById('freeze-value').textContent = freeze === '1' ? 'FROZEN' : 'LIVE';
    document.getElementById('freeze-value').className = freeze === '1' ? 'value red' : 'value';
    document.getElementById('freeze-card').style.borderColor = freeze === '1' ? '#ff4466' : '#00d4aa';

    document.getElementById('ibkr-value').textContent = ibkr === '1' ? 'ONLINE' : 'OFFLINE';
    document.getElementById('ibkr-value').className = ibkr === '1' ? 'value' : 'value red';

    document.getElementById('journal-value').textContent = journal === '1' ? 'HEALTHY' : 'UNHEALTHY';
    document.getElementById('journal-value').className = journal === '1' ? 'value' : 'value red';

    const dl = parseInt(deadLetters) || 0;
    document.getElementById('dead-letter-value').textContent = dl === 0 ? '0 ✓' : dl;
    document.getElementById('dead-letter-value').className = dl > 0 ? 'value yellow' : 'value';

    document.getElementById('orders-allowed').textContent = ordersAllowed;
    document.getElementById('orders-blocked').textContent = ordersBlocked;

    // Gate failures
    const gateFailures = lines
      .filter(l => l.startsWith('superezio_gate_failures_total{'))
      .map(l => {
        const gate = (l.match(/gate="([^"]+)"/) || [,'unknown'])[1];
        const code = (l.match(/reason_code="([^"]+)"/) || [,'?'])[1];
        const val = l.split(' ').pop();
        return {gate, code, val};
      });
    const gatesContainer = document.getElementById('gates-container');
    if (gateFailures.length) {
      gatesContainer.innerHTML = gateFailures.map(g =>
        `<span class="gate gate-fail">${g.gate}: ${g.code} (${g.val})</span>`
      ).join('');
    } else {
      gatesContainer.innerHTML = '<span class="gate gate-pass">Todos os gates OK</span>';
    }

    document.getElementById('updated').textContent = new Date().toISOString();
  } catch(e) {
    console.error('Dashboard fetch error:', e);
  }
}
fetchMetrics();
setInterval(fetchMetrics, 15000);
</script>
</body>
</html>"""
    return Response(content=html, media_type="text/html; charset=utf-8")


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
