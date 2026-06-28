FROM python:3.12-slim

WORKDIR /app

# System deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Python deps
COPY pyproject.toml .
RUN pip install --no-cache-dir -e ".[dev]" 2>/dev/null || \
    pip install --no-cache-dir \
    structlog pydantic-settings prometheus-client tenacity \
    fastapi uvicorn httpx aiohttp pydantic pyyaml \
    pandas numpy scipy scikit-learn yfinance \
    hypothesis coverage pytest pytest-asyncio pytest-cov pytest-xdist

COPY . .

ENV PYTHONPATH=/app/src
EXPOSE 8002

HEALTHCHECK --interval=30s --timeout=10s \
    CMD curl -f http://localhost:8002/health || exit 1
