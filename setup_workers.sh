#!/bin/bash
# Sets up mirrulations-fetch and mirrulations-csv on the EC2 instance.
# Usage: ./setup_workers.sh [--check]
#   --check  Validate/install against existing directories without recloning.
#            Cloning still skips existing directories by default.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PARENT_DIR="$(dirname "$SCRIPT_DIR")"
CHECK_MODE=0

while [[ $# -gt 0 ]]; do
    case "$1" in
        --check)
            CHECK_MODE=1
            ;;
        *)
            echo "Unknown argument: $1" >&2
            echo "Usage: ./setup_workers.sh [--check]" >&2
            exit 1
            ;;
    esac
    shift
done

FETCH_DIR="$PARENT_DIR/mirrulations-fetch"
CSV_DIR="$PARENT_DIR/mirrulations-csv"
SEARCH_VENV_PIP="$SCRIPT_DIR/.venv/bin/pip"

FETCH_URL="https://github.com/mirrulations/mirrulations-fetch.git"
CSV_URL="https://github.com/mirrulations/mirrulations-csv.git"

clone_if_missing() {
    local url="$1"
    local dest="$2"
    local name="$(basename "$dest")"

    if [ -d "$dest" ]; then
        echo "[skip] $name already exists at $dest"
    else
        echo "[clone] Cloning $name into $dest"
        git clone "$url" "$dest"
        echo "[done] $name cloned"
    fi
}

echo "=== mirrulations worker setup ==="
echo "Target directory: $PARENT_DIR"
if [[ "$CHECK_MODE" == "1" ]]; then
    echo "Check mode: enabled"
fi
echo

clone_if_missing "$FETCH_URL" "$FETCH_DIR"
clone_if_missing "$CSV_URL" "$CSV_DIR"

echo
echo "=== Installing dependencies ==="

if [ ! -x "$SEARCH_VENV_PIP" ]; then
    echo "[error] Expected worker venv at $SEARCH_VENV_PIP" >&2
    echo "Create the mirrulations-search .venv before running setup_workers.sh." >&2
    exit 1
fi

if [ -f "$FETCH_DIR/requirements.txt" ]; then
    echo "[pip] Installing mirrulations-fetch dependencies"
    "$SEARCH_VENV_PIP" install -r "$FETCH_DIR/requirements.txt"
    "$SEARCH_VENV_PIP" install -e "$FETCH_DIR"
fi

if [ -f "$CSV_DIR/requirements.txt" ]; then
    echo "[pip] Installing mirrulations-csv dependencies"
    "$SEARCH_VENV_PIP" install -r "$CSV_DIR/requirements.txt"
    "$SEARCH_VENV_PIP" install -e "$CSV_DIR"
fi

echo
echo "=== Setup complete ==="
echo "  mirrulations-fetch: $FETCH_DIR"
echo "  mirrulations-csv:   $CSV_DIR"
