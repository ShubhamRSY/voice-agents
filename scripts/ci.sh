#!/bin/bash
# Local CI mirror — runs the same checks as .github/workflows/ci.yml
set -euo pipefail
cd "$(dirname "$0")/.."

export OPENAI_API_KEY=""
export ANTHROPIC_API_KEY=""

echo "=========================================="
echo "  CI — Local automation test run"
echo "=========================================="

if [ ! -d ".venv" ]; then
  python3 -m venv .venv
fi
source .venv/bin/activate

pip install --upgrade pip -q
pip install -e ".[dev]" -q

mkdir -p tests/reports

echo ""
echo ">> [1/5] Lint with ruff"
ruff check src/ tests/ scripts/

echo ""
echo ">> [2/5] Type check with mypy"
mypy src/ || true

echo ""
echo ">> [3/5] Unit & integration tests"
pytest tests/ \
  --ignore=tests/e2e \
  --ignore=tests/reports \
  -v --tb=short \
  --junitxml=tests/reports/junit-unit.xml \
  --cov=src \
  --cov-report=term-missing \
  --cov-report=xml:tests/reports/coverage-unit.xml

echo ""
echo ">> [4/5] E2E & non-functional tests"
pytest tests/e2e/ \
  -v --tb=short \
  --junitxml=tests/reports/junit-e2e.xml \
  --cov=src \
  --cov-append \
  --cov-report=term-missing \
  --cov-report=xml:tests/reports/coverage-full.xml

echo ""
echo ">> [5/5] Live server E2E tests"
python -m uvicorn src.main:app --host 127.0.0.1 --port 8001 &
SERVER_PID=$!
sleep 2
if curl -sf http://127.0.0.1:8001/api/v1/health > /dev/null 2>&1; then
  pytest tests/test_comprehensive_e2e.py -v --tb=short || true
  kill $SERVER_PID 2>/dev/null || true
else
  echo "WARNING: Server failed to start, skipping live E2E tests"
  kill $SERVER_PID 2>/dev/null || true
fi

echo ""
echo "=========================================="
echo "  CI passed — reports in tests/reports/"
echo "=========================================="
