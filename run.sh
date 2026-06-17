#!/bin/bash
cd "$(dirname "$0")"

if [ ! -d ".venv" ]; then
  echo "ERROR: .venv not found. Run: python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt"
  exit 1
fi

source .venv/bin/activate

# Load API keys from .env
if [ -f .env ]; then
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
fi

PORT=8001

# Stop any old server on this port so restarts pick up new code
if lsof -ti :$PORT >/dev/null 2>&1; then
  echo "Stopping old server on port $PORT..."
  kill $(lsof -ti :$PORT) 2>/dev/null || true
  sleep 1
fi

echo ""
echo "=========================================="
echo "  Voice Agents Platform"
echo "=========================================="
echo ""
echo "  Chat UI:  http://127.0.0.1:$PORT/"
echo "  API docs: http://127.0.0.1:$PORT/docs"
echo ""
echo "  DO NOT CLOSE THIS WINDOW"
echo "  Press Ctrl+C to stop"
echo "=========================================="
echo ""

uvicorn src.main:app --host 127.0.0.1 --port $PORT --reload
