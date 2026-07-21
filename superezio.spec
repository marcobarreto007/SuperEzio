# -*- mode: python ; coding: utf-8 -*-
"""
SuperEzio — PyInstaller spec for Windows one-click executable.

Build:
    pyinstaller superezio.spec --clean
"""

import os
import sys
from pathlib import Path

block_cipher = None

# ---------------------------------------------------------------------------
# Collect all Python modules the project uses.
# The src-layout means PyInstaller needs the whole `src/` tree patched in.
# ---------------------------------------------------------------------------
a = Analysis(
    ['src/agent_server/main.py'],
    pathex=[str(Path('src').resolve())],
    binaries=[],
    datas=[
        # Frontend static assets
        ('frontend', 'frontend'),
        # HTML templates (health dashboard, etc.)
        ('templates', 'templates'),
        # Project marker (needed by paths.find_project_root)
        ('pyproject.toml', '.'),
        # Config defaults
        ('.env.example', '.'),
    ],
    hiddenimports=[
        # ── Web framework ──
        'uvicorn',
        'uvicorn.logging',
        'uvicorn.loops',
        'uvicorn.loops.auto',
        'uvicorn.protocols',
        'uvicorn.protocols.http.auto',
        'uvicorn.middleware',
        'uvicorn.middleware.asgi2',
        'uvicorn.middleware.wsgi',
        'uvicorn.workers',
        'fastapi',
        'sse_starlette',
        'pydantic',
        'pydantic_settings',
        'starlette',
        'starlette.middleware',
        'starlette.middleware.cors',
        'starlette.staticfiles',
        'starlette.responses',
        'starlette.routing',

        # ── Config / secrets ──
        'python_dotenv',
        'dotenv',
        'yaml',
        'pyyaml',

        # ── Auth ──
        'PyJWT',
        'jwt',
        'passlib',
        'passlib.handlers',
        'passlib.context',
        'passlib.handlers.bcrypt',

        # ── Observability ──
        'structlog',
        'structlog.stdlib',
        'structlog.dev',
        'prometheus_client',
        'prometheus_client.core',

        # ── Resilience ──
        'tenacity',

        # ── HTTP / network ──
        'httpx',
        'httpx._client',
        'httpx._transports',
        'requests',

        # ── Data / math ──
        'pandas',
        'numpy',
        'scipy',
        'sklearn',
        'scikit_learn',
        'yfinance',
        'textblob',

        # ── Storage / infra ──
        'redis',

        # ── Pipeline / graph ──
        'langgraph',
        'langgraph.graph',
        'langgraph.graph.state',
        'langchain_core',
        'openai',

        # ── Broker ──
        'ib_insync',
        'alpaca_trade_api',

        # ── AI / ML (core deps) ──
        'torch',
        'transformers',
        'peft',
        'sentence_transformers',
        'faiss',
        'llama_cpp',

        # ── Core project modules (dynamic imports) ──
        'core',
        'core.config',
        'core.config.settings',
        'core.config.secrets',
        'core.config.logging_config',
        'core.paths',
        'core.pipeline',
        'core.pipeline.build_graph',
        'core.pipeline.f51_trade_gate',
        'core.model_serving',
        'core.model_serving.gateway',
        'core.investor',
        'core.investor.storage',
        'core.investor.cost_guard',
        'core.resilience',
        'core.bob_consciousness',
        'core.sentiment',
        'core.sentiment.live_monitor',
        'core.sentiment.curator',
        'core.sentiment.watchlist_pulse',
        'core.idempotency',
        'core.observability',
        'core.mission_context',
        'core.ports',
        'core.ports.protocol',
        'core.evidence',
        'core.f51_adapter',
        'agent_server',
        'agent_server.auth',
        'agent_server.endpoints',
        'adapters',
        'adapters.broker',
        'adapters.broker.ibkr_service',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # GUI toolkits — server-only, no UI
        'tkinter',
        'PyQt5',
        'PySide6',
        'PyQt6',
        'wx',
        # Heavy ML frameworks not used directly
        'tensorflow',
        'keras',
        'jax',
        # Jupyter / notebook (dev only)
        'jupyter',
        'ipython',
        'notebook',
        'nbformat',
        # Image processing (not used)
        'cv2',
        'PIL',
        # Testing (not needed in production binary)
        'pytest',
        '_pytest',
        'playwright',
        'hypothesis',
        'coverage',
        'bandit',
        # Dev servers
        'werkzeug.debug',
        # Build tools
        'setuptools',
        'pip',
        'wheel',
    ],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='SuperEzio',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=['vcruntime*.dll'],
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=['vcruntime*.dll'],
    name='SuperEzio',
)
