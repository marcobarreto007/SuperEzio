#!/usr/bin/env python3
"""
First-Run Wizard + Health Check for SuperEzio (F51 Bootstrap).

Usage:
    python scripts/first_run.py                    # Interactive wizard + health check
    python scripts/first_run.py --no-wizard        # Skip wizard, health check only
    python scripts/first_run.py --port 8002        # Custom server port
    python scripts/first_run.py --host 127.0.0.1   # Custom server host

What it does:
  1. Detects if this is the first run (no .env.local / empty auth.db).
  2. If first run: interactive wizard to configure DeepSeek API key and
     create the admin user.
  3. Runs a local health check (disk, env vars, API connectivity, port).
  4. Shows "Tudo pronto! Acesse http://<host>:<port>"

Can be skipped entirely with ``--no-wizard`` - useful for automated deploys.
"""

from __future__ import annotations

import argparse
import os
import secrets
import shutil
import socket
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

# ---------------------------------------------------------------------------
# Project root detection (same logic as core.config.secrets)
# ---------------------------------------------------------------------------
_SRC = Path(__file__).resolve().parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

_PROJECT_ROOT: Path | None = None


def _find_project_root() -> Path:
    """Locate project root by walking up to pyproject.toml."""
    p = Path(__file__).resolve().parent.parent
    for _ in range(10):
        if (p / "pyproject.toml").exists() or (p / ".env.example").exists():
            return p
        p = p.parent
    return Path.cwd()


def _project_root() -> Path:
    global _PROJECT_ROOT
    if _PROJECT_ROOT is None:
        _PROJECT_ROOT = _find_project_root()
    return _PROJECT_ROOT


# ---------------------------------------------------------------------------
# Auth DB path resolution (matches core.auth.service)
# ---------------------------------------------------------------------------
def _resolve_auth_db() -> Path:
    data_dir = os.getenv("SUPEREZIO_DATA_DIR", "")
    if data_dir:
        return Path(data_dir) / "auth.db"
    # Default: runtime/auth.db (used by agent_server and seed_admin)
    return _project_root() / "runtime" / "auth.db"


# ---------------------------------------------------------------------------
# .env.local helpers
# ---------------------------------------------------------------------------
_ENV_LOCAL_PATH: Path | None = None


def _env_local_path() -> Path:
    global _ENV_LOCAL_PATH
    if _ENV_LOCAL_PATH is None:
        _ENV_LOCAL_PATH = _project_root() / ".env.local"
    return _ENV_LOCAL_PATH


def _parse_env_file(path: Path) -> dict[str, str]:
    """Parse a KEY=VALUE dotenv file, preserving only the last value per key."""
    import re

    result: dict[str, str] = {}
    re_line = re.compile(r"^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*?)\s*$")
    re_quoted = re.compile(r'^["\'](.*)["\']$')
    if not path.is_file():
        return result
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        for raw in fh:
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            m = re_line.match(line)
            if not m:
                continue
            key, val = m.group(1), m.group(2).strip()
            qm = re_quoted.match(val)
            if qm:
                val = qm.group(1)
            result[key] = val
    return result


def _read_env_local_lines(path: Path) -> list[str]:
    """Read all lines from .env.local (returns empty list if missing)."""
    if path.is_file():
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            return fh.readlines()
    return []


def _write_env_local(updates: dict[str, str]) -> Path:
    """Update .env.local with the given key-value pairs.

    Preserves existing keys that are not being updated.
    Existing keys being updated are replaced in-place.
    New keys are appended at the end.
    """
    path = _env_local_path()
    lines = _read_env_local_lines(path)

    import re

    re_line = re.compile(r"^(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=")
    updated_keys: set[str] = set()

    # Replace existing keys in-place
    for i, line in enumerate(lines):
        m = re_line.match(line.strip())
        if m and m.group(1) in updates:
            lines[i] = f'{m.group(1)}={updates[m.group(1)]}\n'
            updated_keys.add(m.group(1))

    # Append new keys not already present
    for key, val in updates.items():
        if key not in updated_keys:
            lines.append(f"{key}={val}\n")

    # Ensure trailing newline
    content = "".join(lines)
    if content and not content.endswith("\n"):
        content += "\n"

    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(content)

    return path


# ---------------------------------------------------------------------------
# First-run detection
# ---------------------------------------------------------------------------
def _has_users(auth_db_path: Path) -> bool:
    """Check if the auth database has at least one user."""
    if not auth_db_path.is_file():
        return False
    try:
        conn = sqlite3.connect(str(auth_db_path))
        count = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        conn.close()
        return count > 0
    except Exception:
        return False


def detect_first_run() -> bool:
    """Return True if this looks like a first run (no env or no users)."""
    # No .env.local -> first run
    env_local = _env_local_path()
    if not env_local.is_file():
        return True

    # Check for placeholder API keys (still "substituir")
    env_vars = _parse_env_file(env_local)
    deepseek_key = env_vars.get("SUPEREZIO_DEEPSEEK_API_KEY", "")
    if not deepseek_key or "substituir" in deepseek_key.lower():
        return True

    # No auth.db or no users -> first run
    auth_db = _resolve_auth_db()
    if not _has_users(auth_db):
        # Also check fallback location (data/auth.db) for migration cases
        fallback = _project_root() / "data" / "auth.db"
        if not _has_users(fallback):
            return True

    return False


# ---------------------------------------------------------------------------
# Wizard
# ---------------------------------------------------------------------------
def _print_banner() -> None:
    print()
    print("=" * 60)
    print("  SUPER EZIO v4.0.0 - Assistente de Configuracao Inicial")
    print("  Seu assistente inteligente de investimentos")
    print("=" * 60)
    print()
    print("  Bem-vindo ao SuperEzio! Vamos configurar seu ambiente.")
    print()


def _ask_provider() -> str:
    """Ask the user to choose between DeepSeek API and yfinance."""
    print("Escolha seu provedor de IA:")
    print("  1) DeepSeek API (recomendado) - Requer chave de API")
    print("  2) yfinance (gratis) - Dados de mercado via Yahoo Finance")
    print()
    while True:
        choice = input("Digite 1 ou 2 [1]: ").strip() or "1"
        if choice == "1":
            return "deepseek"
        elif choice == "2":
            return "yfinance"
        print("  Opcao invalida. Digite 1 ou 2.")


def _ask_deepseek_key() -> str:
    """Prompt the user for a DeepSeek API key."""
    print()
    print("--- Configuracao DeepSeek ---")
    print("  Voce precisa de uma chave de API do DeepSeek.")
    print("  Obtenha em: https://platform.deepseek.com/api_keys")
    print()
    while True:
        key = input("  DeepSeek API Key: ").strip()
        key = key.strip()
        if key and len(key) >= 16:
            return key
        print("  Chave invalida (minimo 16 caracteres). Tente novamente.")


def _ask_admin_credentials() -> tuple[str, str, str]:
    """Prompt the user for admin account credentials."""
    print()
    print("--- Criacao de Conta Admin ---")
    print("  Crie sua conta de administrador para acessar o sistema.")
    print()
    while True:
        username = input("  Username (3-32 caracteres, letras/numeros/_): ").strip()
        if username and 3 <= len(username) <= 32:
            break
        print("  Username invalido (3-32 caracteres).")
    while True:
        email = input("  Email: ").strip()
        if "@" in email and len(email) <= 128:
            break
        print("  Email invalido.")
    while True:
        password = input("  Password (min 8 caracteres): ")
        if len(password) >= 8:
            break
        print("  Password muito curta (min 8 caracteres).")
    return username, email, password


def _generate_jwt_secret() -> str:
    """Generate a cryptographically secure JWT secret."""
    return secrets.token_urlsafe(48)


def _create_admin_user(username: str, email: str, password: str) -> dict:
    """Create admin user via core.auth and promote to admin role.

    Returns the user dict on success.
    Raises ValueError on duplicate or invalid data.
    """
    from core.auth.models import UserRegister
    from core.auth.service import AuthDB

    auth_db_path = _resolve_auth_db()
    db = AuthDB(db_path=auth_db_path)

    # Validate via Pydantic
    payload = UserRegister(username=username, email=email, password=password)

    # Register user
    user = db.register(payload)

    # Promote to admin
    conn = sqlite3.connect(str(auth_db_path))
    try:
        conn.execute("UPDATE users SET role='admin' WHERE id=?", (user["id"],))
        conn.commit()
    except sqlite3.OperationalError:
        # Older schema may not have 'role' column - add it and retry
        conn.execute("ALTER TABLE users ADD COLUMN role TEXT NOT NULL DEFAULT 'user'")
        conn.execute("UPDATE users SET role='admin' WHERE id=?", (user["id"],))
        conn.commit()
    finally:
        conn.close()

    return user


def _show_summary(
    provider: str,
    deepseek_key: str | None,
    admin_user: dict | None,
    env_path: Path,
) -> None:
    """Display a configuration summary to the user."""
    print()
    print("=" * 60)
    print("  RESUMO DA CONFIGURACAO")
    print("=" * 60)
    print(f"  Provedor IA:     {'DeepSeek API' if provider == 'deepseek' else 'yfinance (gratis)'}")
    if provider == "deepseek" and deepseek_key:
        masked = deepseek_key[:8] + "..." + deepseek_key[-4:] if len(deepseek_key) > 12 else "***"
        print(f"  DeepSeek Key:    {masked}")
    if admin_user:
        print(f"  Admin Username:  {admin_user['username']}")
        print(f"  Admin Email:     {admin_user['email']}")
        print(f"  Admin ID:        {admin_user['id']}")
    print(f"  Arquivo env:     {env_path}")
    print("=" * 60)
    print()


def run_wizard() -> tuple[str, str | None, dict | None]:
    """Run the interactive first-run wizard.

    Returns (provider, deepseek_key_or_None, admin_user_or_None).
    """
    _print_banner()

    # Step 1: Choose provider
    provider = _ask_provider()

    # Step 2: DeepSeek key
    deepseek_key: str | None = None
    if provider == "deepseek":
        deepseek_key = _ask_deepseek_key()

    # Step 3: Write .env.local with provider settings
    updates: dict[str, str] = {}
    if provider == "deepseek" and deepseek_key:
        updates["SUPEREZIO_DEEPSEEK_API_KEY"] = deepseek_key
        updates["SUPEREZIO_AGENT_API_KEY"] = deepseek_key
        updates["SUPEREZIO_AGENT_BASE_URL"] = "https://api.deepseek.com"
        updates["SUPEREZIO_AGENT_MODEL"] = "deepseek-v4-flash"
        updates["SUPEREZIO_DEEPSEEK_MODEL"] = "deepseek-v4-pro"
        updates["SUPEREZIO_BOB_SOVEREIGN"] = "1"
    else:
        # yfinance mode - still need basic env
        updates["SUPEREZIO_AGENT_BASE_URL"] = "http://127.0.0.1:8082/v1"
        updates["SUPEREZIO_AGENT_MODEL"] = "bob-core-gguf"
        updates["SUPEREZIO_BOB_SOVEREIGN"] = "0"

    # Always set JWT secret if missing
    existing = _parse_env_file(_env_local_path())
    if "SUPEREZIO_JWT_SECRET" not in existing:
        updates["SUPEREZIO_JWT_SECRET"] = _generate_jwt_secret()
        updates["SUPEREZIO_JWT_ALGORITHM"] = "HS256"
        updates["SUPEREZIO_JWT_ACCESS_TTL"] = "3600"
        updates["SUPEREZIO_JWT_REFRESH_TTL"] = "2592000"

    env_path = _write_env_local(updates)
    print(f"\n  >> Configuracao salva em: {env_path}")

    # Step 4: Create admin account
    admin_user: dict | None = None
    try:
        username, email, password = _ask_admin_credentials()
        admin_user = _create_admin_user(username, email, password)
        print("\n  >> Conta admin criada com sucesso!")
    except ValueError as exc:
        print(f"\n  ERRO ao criar admin: {exc}")
        print("  Execute novamente ou use: python scripts/seed_admin.py")
    except Exception as exc:
        print(f"\n  ERRO inesperado: {exc}")
        print("  Execute novamente ou use: python scripts/seed_admin.py")

    # Step 5: Summary
    _show_summary(provider, deepseek_key, admin_user, env_path)

    return provider, deepseek_key, admin_user


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------
def _check_disk(threshold_mb: int = 500) -> dict:
    """Check available disk space on the project drive."""
    result = {"status": "ok", "detail": ""}
    try:
        path = _project_root()
        usage = shutil.disk_usage(path.anchor if path.anchor else path)
        free_mb = usage.free // (1024 * 1024)
        result["free_mb"] = free_mb
        result["total_mb"] = usage.total // (1024 * 1024)
        if free_mb < threshold_mb:
            result["status"] = "warning"
            result["detail"] = f"Only {free_mb} MB free (threshold: {threshold_mb} MB)"
        else:
            result["detail"] = f"{free_mb} MB free"
    except Exception as exc:
        result["status"] = "error"
        result["detail"] = str(exc)[:120]
    return result


def _check_env_vars() -> dict:
    """Check critical environment variables."""
    result = {"status": "ok", "checks": []}
    critical_vars = [
        "SUPEREZIO_JWT_SECRET",
        "SUPEREZIO_AGENT_BASE_URL",
        "SUPEREZIO_AGENT_MODEL",
    ]
    for var in critical_vars:
        val = os.getenv(var, "")
        if not val:
            result["checks"].append({"var": var, "status": "missing"})
            result["status"] = "warning"
        elif "substituir" in val.lower():
            result["checks"].append({"var": var, "status": "placeholder"})
            result["status"] = "warning"
        else:
            result["checks"].append({"var": var, "status": "ok"})

    # DeepSeek key check
    deepseek_key = os.getenv("SUPEREZIO_DEEPSEEK_API_KEY", "")
    if deepseek_key and "substituir" not in deepseek_key.lower():
        result["checks"].append({"var": "SUPEREZIO_DEEPSEEK_API_KEY", "status": "ok"})
    elif deepseek_key:
        result["checks"].append({"var": "SUPEREZIO_DEEPSEEK_API_KEY", "status": "placeholder"})
        result["status"] = "warning"
    else:
        result["checks"].append({"var": "SUPEREZIO_DEEPSEEK_API_KEY", "status": "not_set"})

    return result


def _check_port(host: str, port: int) -> dict:
    """Check if the server port is available (not in use)."""
    result = {"status": "ok", "host": host, "port": port}
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(2)
        code = s.connect_ex((host, port))
        s.close()
        if code == 0:
            result["status"] = "in_use"
            result["detail"] = f"Port {port} is already in use"
            # Try to figure out what's using it
            try:
                s2 = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                s2.settimeout(1)
                s2.connect((host, port))
                s2.send(b"GET /health HTTP/1.0\r\nHost: localhost\r\n\r\n")
                resp = s2.recv(1024)
                s2.close()
                if b"superezio" in resp.lower() or b"ok" in resp:
                    result["detail"] = f"SuperEzio already running on {host}:{port}"
                    result["server_running"] = True
            except Exception:
                pass
        else:
            result["detail"] = f"Port {port} is available"
    except Exception as exc:
        result["status"] = "error"
        result["detail"] = str(exc)[:120]
    return result


def _check_auth_db() -> dict:
    """Check that the auth database exists and has users."""
    result = {"status": "ok", "detail": ""}
    try:
        auth_db = _resolve_auth_db()
        if not auth_db.is_file():
            result["status"] = "missing"
            result["detail"] = f"Auth DB not found at {auth_db}"
            return result
        conn = sqlite3.connect(str(auth_db))
        count = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        has_admin = 0
        try:
            has_admin = conn.execute(
                "SELECT COUNT(*) FROM users WHERE role='admin'"
            ).fetchone()[0]
        except sqlite3.OperationalError:
            # Older schema may not have 'role' column
            pass
        conn.close()
        result["user_count"] = count
        result["admin_count"] = has_admin
        if count == 0:
            result["status"] = "empty"
            result["detail"] = "No users in auth database"
        elif has_admin == 0:
            result["status"] = "warning"
            result["detail"] = f"{count} user(s) but no admin"
        else:
            result["detail"] = f"{count} user(s), {has_admin} admin(s)"
    except Exception as exc:
        result["status"] = "error"
        result["detail"] = str(exc)[:120]
    return result


def _check_deepseek_api() -> dict:
    """Ping the DeepSeek API to verify connectivity and key validity.

    This does NOT send a real completion - it only checks HTTP connectivity
    by attempting a GET on the base URL.
    """
    result = {"status": "skipped", "detail": "DeepSeek not configured"}
    api_key = os.getenv("SUPEREZIO_DEEPSEEK_API_KEY", "")
    if not api_key or "substituir" in api_key.lower():
        return result

    base_url = os.getenv(
        "SUPEREZIO_DEEPSEEK_BASE_URL", "https://api.deepseek.com"
    )
    try:
        import urllib.request
        import urllib.error

        req = urllib.request.Request(
            f"{base_url}/v1/models",
            headers={"Authorization": f"Bearer {api_key}"},
            method="GET",
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            if resp.status == 200:
                result["status"] = "ok"
                result["detail"] = "API reachable and key valid"
            else:
                result["status"] = "error"
                result["detail"] = f"HTTP {resp.status}"
    except urllib.error.HTTPError as exc:
        if exc.code == 401:
            result["status"] = "error"
            result["detail"] = "Invalid API key (HTTP 401)"
        elif exc.code == 404:
            # Some DeepSeek endpoints return 404 on model list
            result["status"] = "ok"
            result["detail"] = "API reachable (HTTP 404 on model list, expected)"
        else:
            result["status"] = "error"
            result["detail"] = f"HTTP {exc.code}: {str(exc)[:100]}"
    except Exception as exc:
        result["status"] = "error"
        result["detail"] = str(exc)[:120]
    return result


def _check_data_dirs() -> dict:
    """Check that critical data directories exist and are writable."""
    result = {"status": "ok", "checks": []}
    dirs = [
        (_project_root() / "data", "data"),
        (_project_root() / "runtime", "runtime"),
        (_project_root() / "data" / "memory", "memory"),
    ]
    for d, name in dirs:
        check = {"dir": name, "path": str(d)}
        try:
            d.mkdir(parents=True, exist_ok=True)
            test_file = d / ".write_test"
            test_file.write_text("ok")
            test_file.unlink()
            check["status"] = "ok"
            check["detail"] = "Writable"
        except Exception as exc:
            check["status"] = "error"
            check["detail"] = str(exc)[:80]
            result["status"] = "error"
        result["checks"].append(check)
    return result


def run_health_checks(host: str = "127.0.0.1", port: int = 8002) -> dict:
    """Run all health checks and return the aggregated report."""
    print()
    print("=" * 60)
    print("  HEALTH CHECK - Verificacao do Sistema")
    print("=" * 60)
    print()

    checks = {
        "disk": _check_disk(),
        "env_vars": _check_env_vars(),
        "port": _check_port(host, port),
        "auth_db": _check_auth_db(),
        "deepseek_api": _check_deepseek_api(),
        "data_dirs": _check_data_dirs(),
    }

    # Display results
    all_ok = True
    for name, result in checks.items():
        status_tag = {
            "ok": "  OK",
            "warning": " WARN",
            "error": " ERROR",
            "missing": " MISSING",
            "empty": " EMPTY",
            "in_use": " IN USE",
            "skipped": " SKIP",
        }.get(result["status"], " ???? ")

        icon = {
            "ok": "v",
            "warning": "!",
            "error": "x",
            "missing": "?",
            "empty": "?",
            "in_use": "!",
            "skipped": "-",
        }.get(result["status"], "?")

        label = name.replace("_", " ").title()
        detail = result.get("detail", result.get("status", ""))
        print(f"  [{icon}] {label:<20} {status_tag:<8} {detail}")

        if result["status"] in ("error", "missing"):
            all_ok = False

    # Sub-checks for env_vars
    env_result = checks.get("env_vars", {})
    for check in env_result.get("checks", []):
        if check["status"] == "missing":
            print(f"       ! VAR: {check['var']} - nao configurada")
        elif check["status"] == "placeholder":
            print(f"       ! VAR: {check['var']} - contem placeholder 'substituir'")

    print()
    checks["_all_ok"] = all_ok

    if not all_ok:
        print("  >> Algumas verificacoes nao passaram. Reveja os warnings acima.")
        print("  >> O servidor pode funcionar, mas com capacidade reduzida.")
    else:
        print("  >> Todas as verificacoes ok!")

    return checks


# ---------------------------------------------------------------------------
# Server launcher
# ---------------------------------------------------------------------------
def _find_server_command() -> list[str]:
    """Return the command to start the agent server."""
    return [sys.executable, "-m", "agent_server.main"]


def print_server_info(host: str, port: int, checks: dict) -> None:
    """Print the final 'Tudo pronto' message with access URL."""
    print()
    print("=" * 60)
    print("  TUDO PRONTO!")
    print("=" * 60)
    print()
    print(f"  Acesse: http://{host}:{port}")
    print()
    print("  Para iniciar o servidor:")
    print("    python -m agent_server.main")
    print()
    print("  Quick smoke test:")
    print("    python scripts/browser_smoke.py")
    print()
    print("  Documentacao:")
    print("    .env.example - Variaveis de ambiente")
    print("    docs/        - Arquitetura e runbooks")
    print("    .f51/        - Inventario, contratos, checkpoints")
    print()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="SuperEzio First-Run Wizard & Health Check",
    )
    parser.add_argument(
        "--no-wizard",
        action="store_true",
        help="Skip the interactive wizard (useful for automated deploys)",
    )
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="Server host (default: 127.0.0.1)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8002,
        help="Server port (default: 8002)",
    )
    parser.add_argument(
        "--start-server",
        action="store_true",
        help="Automatically start the server after setup",
    )
    return parser.parse_args(argv)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main(argv: list[str] | None = None) -> None:
    args = _parse_args(argv)

    # Load existing env vars first
    try:
        from core.config.secrets import load_local_env
        load_local_env()
    except Exception:
        pass

    first_run = detect_first_run()

    # --- Wizard (unless --no-wizard or not first run) ---
    if args.no_wizard:
        print("  [--no-wizard] Pulado. Executando health check apenas.")
    elif not first_run:
        print("  Sistema ja configurado. Pulando wizard.")
        print('  Use --no-wizard para silenciar esta mensagem.')
    else:
        print()
        print("  >> Primeira execucao detectada! Iniciando wizard...")
        run_wizard()
        # Reload env after wizard writes .env.local
        try:
            from dotenv import load_dotenv
            load_dotenv(dotenv_path=str(_env_local_path()), override=True)
        except Exception:
            pass

    # --- Health check ---
    checks = run_health_checks(host=args.host, port=args.port)

    # --- Server info ---
    print_server_info(host=args.host, port=args.port, checks=checks)

    # --- Optional: start server ---
    if args.start_server:
        server_running = checks.get("port", {}).get("server_running", False)
        if server_running:
            print("  >> Servidor ja esta rodando.")
            return

        cmd = _find_server_command()
        print(f"  >> Iniciando servidor: {' '.join(cmd)}")
        print()
        try:
            subprocess.Popen(
                cmd,
                cwd=str(_project_root()),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            time.sleep(2)
            print(f"  >> Servidor iniciado em http://{args.host}:{args.port}")
        except Exception as exc:
            print(f"  >> ERRO ao iniciar servidor: {exc}")
            print("  >> Inicie manualmente: python -m agent_server.main")
    else:
        print("  Dica: use --start-server para iniciar automaticamente.")
    print()


if __name__ == "__main__":
    main()
