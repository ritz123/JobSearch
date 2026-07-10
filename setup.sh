#!/usr/bin/env bash
set -euo pipefail

# Check if uv is installed; install it if not
if ! command -v uv &>/dev/null; then
  echo "uv not found. Installing uv..."
  curl -LsSf https://astral.sh/uv/install.sh | sh
  # Re-source the shell environment so uv is on PATH
  # shellcheck source=/dev/null
  source "$HOME/.local/bin/env" 2>/dev/null || export PATH="$HOME/.local/bin:$PATH"
fi

# Create virtual environment if it doesn't exist
if [[ ! -d ".venv" ]]; then
  echo "Creating virtual environment..."
  uv venv
fi

# Install dependencies
echo "Installing dependencies..."
uv sync

# Copy .env.example if .env doesn't exist
if [[ ! -f ".env" ]]; then
  cp .env.example .env
  echo ""
  echo "Created .env from .env.example — please fill in your APIFY_TOKEN before running the scraper."
fi

echo ""
echo "Setup complete. Dependencies managed by uv. Activate venv with: source .venv/bin/activate"
