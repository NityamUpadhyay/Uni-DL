#!/usr/bin/env bash
# start.sh — launch UniDL on macOS / Linux
set -e
cd "$(dirname "$0")"

echo "============================================================"
echo "  UniDL — Universal Downloader"
echo "============================================================"
echo ""

# ── Find Python ──────────────────────────────────────────────────────────────
PYTHON=""
for cmd in python3 python; do
    if command -v "$cmd" &>/dev/null; then
        PYTHON=$(command -v "$cmd")
        break
    fi
done

if [ -z "$PYTHON" ]; then
    echo "[ERROR] Python 3 not found."
    echo ""
    echo "  Install it from: https://www.python.org/downloads/"
    echo "  On Ubuntu/Debian: sudo apt install python3 python3-pip"
    echo "  On macOS with Homebrew: brew install python"
    exit 1
fi

echo "  Found: $($PYTHON --version)"
echo ""

# ── Run bootstrap (installs deps + launches app) ─────────────────────────────
"$PYTHON" bootstrap.py "$@"
