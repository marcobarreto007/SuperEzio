"""
Unified environment loader — single entry point for .env loading.

Order of precedence (first wins):
  1. OS environment variables (already set)
  2. .env.local (local overrides, never committed)
  3. .env (base config, never committed)

Usage:
    from core.config.env import load_env_once
    load_env_once()  # safe to call multiple times — only loads once
"""

from __future__ import annotations

from .secrets import load_local_env as load_env_once

__all__ = ["load_env_once"]
