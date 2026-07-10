#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [[ ! -f "$SCRIPT_DIR/.venv/bin/activate" ]]; then
    echo "Virtual environment not found. Running setup first..."
    bash "$SCRIPT_DIR/setup.sh"
fi

# Print usage hint if no arguments given
if [[ $# -eq 0 ]]; then
  echo "Usage: ./run_scraper.sh --keywords \"job title\" --location \"city\""
  echo "Run ./run_scraper.sh --help for all options."
  exit 0
fi

exec uv run python "$SCRIPT_DIR/scraper.py" "$@"
