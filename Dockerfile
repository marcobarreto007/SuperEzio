# SuperEzio v4.0.0 — Dockerfile multi-stage
# ==========================================
# Stage 1: build  — compila dependências
# Stage 2: cpu    — runtime CPU-only (cloud)
# Stage 3: gpu    — runtime GPU (RTX 5060 Ti, CUDA 12.x)
#
# Uso:
#   docker build -t superezio:cpu .                           # CPU only
#   docker build -t superezio:gpu --target gpu .              # GPU
#   docker run -p 8002:8002 --env-file .env superezio:cpu

# ── Stage 1: Build ──────────────────────────────────────────────────────────
FROM python:3.12-slim AS build

WORKDIR /build
COPY pyproject.toml ./
COPY src/ ./src/

RUN pip install --no-cache-dir --upgrade pip setuptools wheel \
    && pip install --no-cache-dir -e .

# ── Stage 2: CPU Runtime ────────────────────────────────────────────────────
FROM python:3.12-slim AS cpu

LABEL org.superezio.version="4.0.0"
LABEL org.superezio.target="cpu"

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY --from=build /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=build /usr/local/bin /usr/local/bin
COPY pyproject.toml ./
COPY src/ ./src/
COPY config/ ./config/
COPY data/ ./data/
COPY scripts/ ./scripts/

RUN pip install --no-cache-dir -e .

ENV SUPEREZIO_HOST=0.0.0.0
ENV SUPEREZIO_PORT=8002
ENV SUPEREZIO_DATA_DIR=/app/data

EXPOSE 8002

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8002/health || exit 1

CMD ["python", "-m", "agent_server.main"]

# ── Stage 3: GPU Runtime ────────────────────────────────────────────────────
FROM nvidia/cuda:12.4-runtime-ubuntu22.04 AS gpu

LABEL org.superezio.version="4.0.0"
LABEL org.superezio.target="gpu"

RUN apt-get update && apt-get install -y --no-install-recommends \
    python3.12 python3.12-venv python3-pip \
    curl ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && ln -s /usr/bin/python3.12 /usr/local/bin/python \
    && ln -s /usr/bin/pip3 /usr/local/bin/pip

WORKDIR /app

COPY pyproject.toml ./
COPY src/ ./src/
COPY config/ ./config/
COPY data/ ./data/
COPY scripts/ ./scripts/

RUN pip install --no-cache-dir -e . \
    && pip install --no-cache-dir torch torchvision --index-url https://download.pytorch.org/whl/cu124

ENV SUPEREZIO_HOST=0.0.0.0
ENV SUPEREZIO_PORT=8002
ENV SUPEREZIO_DATA_DIR=/app/data
ENV CEO_LORA_GPU=0

EXPOSE 8002

HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD curl -f http://localhost:8002/health || exit 1

CMD ["python", "-m", "agent_server.main"]
