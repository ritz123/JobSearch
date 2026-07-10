#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [[ ! -f "$SCRIPT_DIR/.venv/bin/activate" ]]; then
    echo "Virtual environment not found. Running setup first..."
    bash "$SCRIPT_DIR/setup.sh"
fi

# Default to 'stats' if no arguments given
if [[ $# -eq 0 ]]; then
  exec uv run python "$SCRIPT_DIR/query.py" stats
fi

exec uv run python "$SCRIPT_DIR/query.py" "$@"
