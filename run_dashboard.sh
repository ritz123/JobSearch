#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [[ ! -f "$SCRIPT_DIR/.venv/bin/activate" ]]; then
    echo "Virtual environment not found. Running setup first..."
    bash "$SCRIPT_DIR/setup.sh"
fi

exec uv run streamlit run "$SCRIPT_DIR/app.py" --server.port 8501 --server.headless false
