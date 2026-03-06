"""SuperEzio CEO Server — llama-cpp-python OpenAI-compatible API.

Serves Gemma-4-26B-A4B-abliterated (Q4_K_M GGUF) on port 8082.

Usage:
    python scripts/server.py                          # default port 8082
    python scripts/server.py --port 8083              # custom port
    python scripts/server.py --model /path/to.gguf    # custom model path

Env vars:
    SUPEREZIO_CEO_MODEL_PATH  — path to GGUF file (default: WSL path)
    SUPEREZIO_CEO_PORT        — port (default: 8082)
    SUPEREZIO_CEO_N_GPU       — GPU layers to offload (default: 32)
    SUPEREZIO_CEO_N_CTX       — context window (default: 8192)
    SUPEREZIO_CEO_HOST        — bind host (default: 127.0.0.1)
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path


def _find_model() -> str | None:
    """Find the GGUF model file. Checks env var and common locations."""
    env_path = os.getenv("SUPEREZIO_CEO_MODEL_PATH")
    if env_path and Path(env_path).exists():
        return env_path

    candidates = [
        # WSL path (primary — where we downloaded it)
        "/home/marco/models/Huihui-gemma-4-26B-A4B-it-abliterated.Q4_K_M.gguf",
        # Windows paths
        r"C:\Users\marco\models\Huihui-gemma-4-26B-A4B-it-abliterated.Q4_K_M.gguf",
        # Project-local
        Path(__file__).parent.parent
        / "models"
        / "Huihui-gemma-4-26B-A4B-it-abliterated.Q4_K_M.gguf",
    ]

    for candidate in candidates:
        p = Path(candidate)
        if p.exists():
            return str(p)

    return None


def main() -> None:
    parser = argparse.ArgumentParser(
        description="SuperEzio CEO Server — Gemma-4-26B via llama-cpp",
    )
    parser.add_argument(
        "--model",
        default=None,
        help="Path to GGUF model file (default: auto-detect)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.getenv("SUPEREZIO_CEO_PORT", "8082")),
        help="Port to listen on (default: 8082)",
    )
    parser.add_argument(
        "--host",
        default=os.getenv("SUPEREZIO_CEO_HOST", "127.0.0.1"),
        help="Host to bind to (default: 127.0.0.1)",
    )
    parser.add_argument(
        "--n-gpu-layers",
        type=int,
        default=int(os.getenv("SUPEREZIO_CEO_N_GPU", "32")),
        help="Number of layers to offload to GPU (default: 32)",
    )
    parser.add_argument(
        "--n-ctx",
        type=int,
        default=int(os.getenv("SUPEREZIO_CEO_N_CTX", "8192")),
        help="Context window size (default: 8192)",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        default=False,
        help="Enable verbose llama.cpp logging",
    )

    args = parser.parse_args()

    # ── Find model ──
    model_path = args.model or _find_model()
    if not model_path:
        print("ERROR: GGUF model not found.", file=sys.stderr)
        print("Set SUPEREZIO_CEO_MODEL_PATH env var or pass --model.", file=sys.stderr)
        print("Checked:", file=sys.stderr)
        print("  /home/marco/models/Huihui-gemma-4-26B-A4B-it-abliterated.Q4_K_M.gguf")
        print("  C:\\Users\\marco\\models\\Huihui-gemma-4-26B-A4B-it-abliterated.Q4_K_M.gguf")
        sys.exit(1)

    print(f"Model: {model_path}")
    print(f"Port:  {args.port}")
    print(f"GPU layers: {args.n_gpu_layers}")
    print(f"Context: {args.n_ctx}")

    # ── Start server ──
    from llama_cpp.server.app import create_app
    from llama_cpp.server.settings import Settings

    settings = Settings(
        model=model_path,
        host=args.host,
        port=args.port,
        n_gpu_layers=args.n_gpu_layers,
        n_ctx=args.n_ctx,
        chat_format="gemma",
        verbose=args.verbose,
    )

    app = create_app(settings=settings)

    import uvicorn

    uvicorn.run(
        app,
        host=args.host,
        port=args.port,
        log_level="info",
    )


if __name__ == "__main__":
    main()
