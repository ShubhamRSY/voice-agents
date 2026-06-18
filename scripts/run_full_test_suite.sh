#!/bin/bash
# Full test suite: unit + E2E + non-functional (delegates to ci.sh).
set -euo pipefail
exec "$(dirname "$0")/ci.sh"
