#!/usr/bin/env bash
# Hearthwren Single-Script Launcher for macOS and Linux

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "====================================================================="
echo "   Hearthwren - Local AI Coding Agent Studio (Ultra-Lightweight)"
echo "====================================================================="

# Locate Python 3.11+
PY_CMD=""
for cmd in python3 python py; do
    if command -v "$cmd" >/dev/null 2>&1; then
        if "$cmd" -c "import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)" 2>/dev/null; then
            PY_CMD="$cmd"
            break
        fi
    fi
done

if [ -z "$PY_CMD" ]; then
    echo "[ERROR] Python 3.11+ is required but was not found on PATH."
    echo "Please install Python 3.11+ from https://www.python.org/ or via your package manager."
    exit 1
fi

VENV_DIR="$SCRIPT_DIR/.venv"
VENV_PYTHON="$VENV_DIR/bin/python"

if [ ! -f "$VENV_PYTHON" ]; then
    echo "[*] Creating virtual environment in .venv..."
    "$PY_CMD" -m venv "$VENV_DIR"
    echo "[*] Installing dependencies..."
    "$VENV_DIR/bin/pip" install --quiet --disable-pip-version-check -e "$SCRIPT_DIR"
fi

echo "[*] Starting Hearthwren Desktop Studio (< 30 MB RAM)..."
"$VENV_PYTHON" "$SCRIPT_DIR/run_hearthwren.py" "$@"
