#!/usr/bin/env bash
# ────────────────────────────────────────────────────────────────────
# SuperEzio — Bootstrap ONE-CLICK (Linux / macOS)
# ────────────────────────────────────────────────────────────────────
# Usage:
#   chmod +x setup_superezio.sh && ./setup_superezio.sh
#   ./setup_superezio.sh run         # start server only
#   ./setup_superezio.sh --help      # this message
#
# Idempotent: safe to run multiple times.
# ────────────────────────────────────────────────────────────────────
set -euo pipefail

PASS="[OK]"
FAIL="[FAIL]"
SKIP="[SKIP]"
INFO="[INFO]"
ERR_COUNT=0
STEP=0
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

header() {
    clear 2>/dev/null || true
    echo ""
    echo "  ====== SuperEzio Bootstrap v4.0.0 ======"
    echo "  Linux/macOS ONE-CLICK Setup"
    echo ""
}

step_num() {
    STEP=$((STEP + 1))
    echo -e "[${STEP}] ${1}"
}

activate_venv() {
    if [ -f ".venv/bin/activate" ]; then
        # shellcheck disable=SC1091
        source ".venv/bin/activate" 2>/dev/null || true
    fi
}

# ───────── MAIN ─────────
main() {
    header
    step_python
    [ $ERR_COUNT -ne 0 ] && { summary; exit 1; }
    step_venv
    step_install_deps
    step_playwright
    step_env_file
    step_jwt_secret
    step_seed_admin
    summary
}

# ───────── Steps ─────────

step_python() {
    step_num "Checking Python 3.11+..."
    if ! command -v python3 &>/dev/null && ! command -v python &>/dev/null; then
        echo -e "  ${FAIL} Python not found."
        echo "  Install from: https://www.python.org/downloads/"
        ERR_COUNT=$((ERR_COUNT + 1))
        return
    fi

    PY_CMD="python3"
    if command -v python3 &>/dev/null; then
        PY_CMD="python3"
    elif command -v python &>/dev/null; then
        PY_CMD="python"
    fi

    PY_VER=$($PY_CMD --version 2>&1 | awk '{print $2}')
    echo -e "  ${PASS} Python: ${PY_VER}"

    PY_MAJOR=$(echo "$PY_VER" | cut -d. -f1)
    PY_MINOR=$(echo "$PY_VER" | cut -d. -f2)
    if [ "$PY_MAJOR" -lt 3 ] || { [ "$PY_MAJOR" -eq 3 ] && [ "$PY_MINOR" -lt 11 ]; }; then
        echo -e "  ${FAIL} Python 3.11+ required (found ${PY_VER})"
        ERR_COUNT=$((ERR_COUNT + 1))
        return
    fi
    echo -e "  ${PASS} Requirement met."
}

step_venv() {
    step_num "Checking virtual environment..."
    if [ -f ".venv/bin/python" ]; then
        echo -e "  ${PASS} .venv already exists."
        return
    fi
    echo -e "  ${INFO} Creating .venv..."
    python3 -m venv .venv 2>/dev/null || python -m venv .venv
    echo -e "  ${PASS} .venv created."
}

step_install_deps() {
    step_num "Installing dependencies (pip install -e .)..."
    activate_venv
    pip install -e . 2>&1 | grep -v "already satisfied" || true
    echo -e "  ${PASS} Dependencies installed."
}

step_playwright() {
    step_num "Installing Playwright Chromium..."
    activate_venv
    python -m playwright install chromium 2>&1 || true
    echo -e "  ${PASS} Playwright Chromium installed."
}

step_env_file() {
    step_num "Checking .env.local..."
    if [ -f ".env.local" ]; then
        echo -e "  ${PASS} .env.local already exists."
        return
    fi
    if [ -f ".env.example" ]; then
        echo -e "  ${INFO} Copying .env.example to .env.local..."
        cp ".env.example" ".env.local"
        echo -e "  ${PASS} .env.local created from .env.example."
        echo -e "  ${INFO} Edit .env.local to add your API keys."
    else
        echo -e "  ${SKIP} .env.example not found — skipping."
    fi
}

step_jwt_secret() {
    step_num "Checking SUPEREZIO_JWT_SECRET..."
    if [ -f ".env.local" ]; then
        if grep -q "^SUPEREZIO_JWT_SECRET=" ".env.local" 2>/dev/null; then
            JWT_VAL=$(grep "^SUPEREZIO_JWT_SECRET=" ".env.local" | cut -d= -f2)
            if [ -n "$JWT_VAL" ]; then
                echo -e "  ${PASS} SUPEREZIO_JWT_SECRET already configured."
                return
            fi
        fi
    fi
    echo -e "  ${INFO} Generating random JWT_SECRET..."
    JWT_GEN=$(python3 -c "import secrets; print(secrets.token_urlsafe(48))" 2>/dev/null || \
              python -c "import secrets; print(secrets.token_urlsafe(48))")
    if [ -z "$JWT_GEN" ]; then
        echo -e "  ${FAIL} Failed to generate JWT_SECRET."
        ERR_COUNT=$((ERR_COUNT + 1))
        return
    fi
    echo "SUPEREZIO_JWT_SECRET=${JWT_GEN}" >> ".env.local"
    echo -e "  ${PASS} JWT_SECRET generated and saved to .env.local."
}

step_seed_admin() {
    step_num "Checking admin seed..."
    if [ ! -f "scripts/seed_admin.py" ]; then
        echo -e "  ${SKIP} scripts/seed_admin.py not found."
        return
    fi
    if [ -z "${SUPEREZIO_ADMIN_PASSWORD:-}" ]; then
        echo -e "  ${FAIL} SUPEREZIO_ADMIN_PASSWORD is required but not set."
        echo "  Refusing to seed the admin user with a known/default password (fail-closed)."
        echo "  Generate a strong random password with:"
        echo '    python -c "import secrets; print(secrets.token_hex(32))"'
        echo "  Export it and run this script again:"
        echo "    export SUPEREZIO_ADMIN_PASSWORD=<the token above>"
        ERR_COUNT=$((ERR_COUNT + 1))
        return
    fi
    activate_venv
    ADMIN_PASS="${SUPEREZIO_ADMIN_PASSWORD}"
    echo -e "  ${INFO} Seeding admin (admin / ********)..."
    python scripts/seed_admin.py --username admin --email admin@superezio.com --password "${ADMIN_PASS}" 2>&1 || true
    echo -e "  ${PASS} Admin seed verified."
}

step_run() {
    header
    if [ $ERR_COUNT -gt 0 ]; then
        echo -e "  ${FAIL} Fix errors before starting."
        exit 1
    fi
    activate_venv
    echo ""
    echo -e "  ${INFO} Server: http://127.0.0.1:8002"
    echo -e "  ${INFO} Press Ctrl+C to stop."
    echo ""
    # Open browser after short delay
    (sleep 3 && (xdg-open http://127.0.0.1:8002 2>/dev/null || \
                 open http://127.0.0.1:8002 2>/dev/null || true)) &
    python -m agent_server.main
    echo ""
}

usage() {
    header
    echo "  Commands:"
    echo "    ./setup_superezio.sh           full bootstrap"
    echo "    ./setup_superezio.sh run       start server"
    echo "    ./setup_superezio.sh --help    this message"
    echo ""
}

summary() {
    echo ""
    if [ $ERR_COUNT -eq 0 ]; then
        echo -e "  ${GREEN}${PASS}${NC} Bootstrap completed successfully!"
        echo ""
        echo "  To start the server:"
        echo "    ./setup_superezio.sh run"
        echo ""
        echo "  Or manually:"
        echo "    source .venv/bin/activate"
        echo "    python -m agent_server.main"
        echo ""
        echo "  Open: http://127.0.0.1:8002"
    else
        echo -e "  ${RED}${FAIL}${NC} ${ERR_COUNT} error(s) found."
        echo "  Fix and run again."
        exit 1
    fi
    echo ""
}

# ───────── Dispatch ─────────
case "${1:-}" in
    run)    step_run ;;
    --help|-h) usage ;;
    *)      main ;;
esac
