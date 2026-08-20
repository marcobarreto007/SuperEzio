FROM python:3.12-slim

WORKDIR /app

# System deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    cmake \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY . .

# Install the project only after its src/ tree is available.  The previous
# editable install ran with pyproject.toml alone and silently fell back to an
# incomplete hand-maintained dependency list.
RUN python -m pip install --no-cache-dir --upgrade pip && \
    python -m pip install --no-cache-dir .

ENV PYTHONPATH=/app/src
EXPOSE 8002

HEALTHCHECK --interval=30s --timeout=10s \
    CMD curl -f http://localhost:8002/health || exit 1
