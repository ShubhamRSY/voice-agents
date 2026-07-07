#!/bin/bash
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if [ ! -d ".venv" ]; then
  echo "ERROR: .venv not found. Run:"
  echo "  python3 -m venv .venv && source .venv/bin/activate"
  echo "  pip install -e \".[dev]\""
  exit 1
fi

source .venv/bin/activate

ENV_FILE="config/environment/.env"
if [ -f "$ENV_FILE" ]; then
  set -a
  # shellcheck disable=SC1090
  source "$ENV_FILE"
  set +a
fi

PORT=8001

if lsof -ti :$PORT >/dev/null 2>&1; then
  echo "Stopping old server on port $PORT..."
  kill $(lsof -ti :$PORT) 2>/dev/null || true
  sleep 1
fi

echo ""
echo "=========================================="
echo "  Nexus Voice Agents Platform"
echo "=========================================="
echo ""
echo "  Chat UI:   http://127.0.0.1:$PORT/"
echo "  API docs:  http://127.0.0.1:$PORT/docs"
echo "  Health:    http://127.0.0.1:$PORT/api/v1/health"
echo ""
echo "  Server is running — press Ctrl+C to stop"
echo "=========================================="
echo ""

uvicorn src.main:app --host 127.0.0.1 --port $PORT --reload
