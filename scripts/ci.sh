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
echo ">> [1/2] Unit & integration tests"
pytest tests/ \
  --ignore=tests/e2e \
  --ignore=tests/reports \
  -v --tb=short \
  --junitxml=tests/reports/junit-unit.xml \
  --cov=src \
  --cov-report=term-missing \
  --cov-report=xml:tests/reports/coverage-unit.xml

echo ""
echo ">> [2/2] E2E & non-functional tests"
pytest tests/e2e/ \
  -v --tb=short \
  --junitxml=tests/reports/junit-e2e.xml \
  --cov=src \
  --cov-append \
  --cov-report=term-missing \
  --cov-report=xml:tests/reports/coverage-full.xml

echo ""
echo "=========================================="
echo "  CI passed — reports in tests/reports/"
echo "=========================================="
