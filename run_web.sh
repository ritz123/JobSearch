#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [[ ! -f "$SCRIPT_DIR/.venv/bin/activate" ]]; then
    echo "Virtual environment not found. Running setup first..."
    bash "$SCRIPT_DIR/setup.sh"
fi

if [[ ! -d "$SCRIPT_DIR/web/node_modules" ]]; then
    echo "Installing web dependencies..."
    (cd "$SCRIPT_DIR/web" && npm install)
fi

cleanup() {
    if [[ -n "${API_PID:-}" ]]; then
        kill "$API_PID" 2>/dev/null || true
    fi
}
trap cleanup EXIT INT TERM

echo "Starting API on http://127.0.0.1:8000 ..."
uv run uvicorn api.main:app --host 127.0.0.1 --port 8000 &
API_PID=$!

# Wait briefly for API
for _ in $(seq 1 30); do
    if curl -sf http://127.0.0.1:8000/api/health >/dev/null 2>&1; then
        break
    fi
    sleep 0.2
done

echo "Starting React app on http://127.0.0.1:5173 ..."
cd "$SCRIPT_DIR/web"
exec npm run dev -- --host 127.0.0.1 --port 5173
