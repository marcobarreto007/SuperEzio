content = open('src/agent_server/main.py', encoding='utf-8').read()

# Add health dashboard endpoints before the existing /dashboard endpoint
old = '\n@app.get("/dashboard", include_in_schema=False)\nasync def dashboard():'

new = '''
# =================================
# Health Dashboard endpoints
# =================================

_HEALTH_DASHBOARD_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "templates", "health_dashboard.html")


@app.get("/health/dashboard", include_in_schema=False)
async def health_dashboard():
    """Health dashboard HTML — provider status, latency, memory, uptime."""
    try:
        from pathlib import Path
        tmpl = Path(_HEALTH_DASHBOARD_PATH)
        if tmpl.exists():
            html = tmpl.read_text(encoding="utf-8")
            return Response(content=html, media_type="text/html; charset=utf-8")
    except Exception:
        pass
    return Response(
        content="<html><body><h1>Health Dashboard</h1><p>Template not found</p></body></html>",
        media_type="text/html; charset=utf-8",
    )


@app.get("/api/health/dashboard-data", include_in_schema=False)
async def health_dashboard_data():
    """JSON data endpoint consumed by the health dashboard."""
    uptime_s = metrics.uptime_seconds()
    memory_mb = _get_memory_usage_mb()

    gpu_info = {"available": False, "devices": []}
    try:
        import torch
        gpu_info["available"] = torch.cuda.is_available()
        if gpu_info["available"]:
            for i in range(torch.cuda.device_count()):
                props = torch.cuda.get_device_properties(i)
                gpu_info["devices"].append({"id": i, "name": props.name, "vram_mb": props.total_memory // (1024 * 1024)})
    except ImportError:
        gpu_info["status"] = "no_torch"

    primary_configured = bool(os.getenv("SUPEREZIO_PRIMARY_API_KEY") or os.getenv("SUPEREZIO_DEEPSEEK_API_KEY"))
    deepseek_configured = bool(os.getenv("SUPEREZIO_DEEPSEEK_API_KEY"))
    agent_url = os.getenv("SUPEREZIO_AGENT_BASE_URL", "")

    providers_status = {}
    try:
        pipeline = getattr(app.state, "pipeline", None)
        gateway = getattr(pipeline, "gateway", None) if pipeline else None
        for p in (list(getattr(gateway, "providers", [])) if gateway else []):
            providers_status[p.name] = {
                "configured": bool((p.api_key or "").strip()),
                "model": p.model,
                "base_url": p.base_url,
                "priority": p.priority,
            }
    except Exception as exc:
        providers_status = {"error": str(exc)[:200]}

    all_metrics = metrics.get_all()
    errors_list = []
    for k, v in all_metrics.get("counters", {}).items():
        if "_errors" in k and v > 0:
            endpoint = k.replace("_errors", "").replace("http_", "", 1)
            errors_list.append({"endpoint": endpoint, "count": v})

    latency_list = {}
    for k, v in all_metrics.get("histograms", {}).items():
        if "_latency_s" in k:
            endpoint = k.replace("_latency_s", "").replace("http_", "", 1)
            latency_list[endpoint] = {
                "avg_ms": round(v.get("avg", 0) * 1000, 2),
                "p95_ms": round(v.get("p95", 0) * 1000, 2),
                "count": v.get("count", 0),
            }

    bob_status = {}
    try:
        from core.bob_consciousness import bob_body_scan
        scan = bob_body_scan()
        bob_status = {
            "healthy": scan.get("healthy_count", 0),
            "sick": scan.get("sick_count", 0),
            "critical": scan.get("critical_count", 0),
            "pain": scan.get("overall_pain", 0),
        }
    except Exception:
        bob_status = {"healthy": 0, "sick": 0, "critical": 0, "pain": 0}

    return {
        "status": "ok",
        "version": "4.0.0",
        "agent": AGENT_NAME,
        "uptime_seconds": uptime_s,
        "memory_mb": memory_mb,
        "gpu": gpu_info,
        "providers": providers_status,
        "primary_configured": primary_configured,
        "deepseek_configured": deepseek_configured,
        "agent_url": agent_url,
        "errors": errors_list[:10],
        "latency": latency_list,
        "bob": bob_status,
    }


def _get_memory_usage_mb() -> float:
    """Get current process memory usage in MB (cross-platform, no psutil required)."""
    try:
        import psutil
        proc = psutil.Process(os.getpid())
        return round(proc.memory_info().rss / (1024 * 1024), 1)
    except ImportError:
        pass
    try:
        import ctypes
        from ctypes import wintypes
        kernel32 = ctypes.windll.kernel32
        process_handle = kernel32.GetCurrentProcess()
        class PMC(ctypes.Structure):
            _fields_ = [
                ("cb", wintypes.DWORD),
                ("PageFaultCount", wintypes.DWORD),
                ("PeakWorkingSetSize", ctypes.c_size_t),
                ("WorkingSetSize", ctypes.c_size_t),
                ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                ("PagefileUsage", ctypes.c_size_t),
                ("PeakPagefileUsage", ctypes.c_size_t),
            ]
        pmc = PMC()
        if kernel32.GetProcessMemoryInfo(ctypes.c_void_p(process_handle), ctypes.byref(pmc), ctypes.sizeof(pmc)):
            return round(pmc.WorkingSetSize / (1024 * 1024), 1)
    except (AttributeError, OSError, ImportError):
        pass
    try:
        with open(f"/proc/{os.getpid()}/status") as fh:
            for line in fh:
                if line.startswith("VmRSS:"):
                    parts = line.strip().split()
                    if len(parts) >= 2:
                        return round(float(parts[1]) / 1024, 1)
    except (FileNotFoundError, IOError, IndexError):
        pass
    return 0.0


''' + old

content = content.replace(old, new)
open('src/agent_server/main.py', 'w', encoding='utf-8').write(content)
print("Step 5b done: health dashboard endpoints added")
