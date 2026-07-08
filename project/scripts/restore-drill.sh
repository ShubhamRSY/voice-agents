#!/usr/bin/env bash
# Non-destructive restore drill — validates latest backup without touching production.
#
# Usage:
#   ./scripts/restore-drill.sh
#   ./scripts/restore-drill.sh --timestamp 20260708-212307

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKUP_DIR="${BACKUP_DIR:-$ROOT/backups}"
TIMESTAMP=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --timestamp) TIMESTAMP="$2"; shift 2 ;;
    *) echo "Unknown option: $1"; exit 1 ;;
  esac
done

if [ -z "$TIMESTAMP" ]; then
  SQLITE=$(ls -t "$BACKUP_DIR"/nexus-sqlite-*.db 2>/dev/null | head -1)
  if [ -z "$SQLITE" ]; then
    echo "ERROR: No SQLite backups found in $BACKUP_DIR"
    exit 1
  fi
  TIMESTAMP=$(basename "$SQLITE" | sed 's/nexus-sqlite-//;s/.db//')
fi

SQLITE="$BACKUP_DIR/nexus-sqlite-$TIMESTAMP.db"
CHROMA="$BACKUP_DIR/nexus-chroma-$TIMESTAMP.tar.gz"
CONFIG="$BACKUP_DIR/nexus-config-$TIMESTAMP.tar.gz"
DRILL="/tmp/nexus-restore-drill-$TIMESTAMP"

echo "=========================================="
echo "  Nexus restore drill — $TIMESTAMP"
echo "=========================================="

for f in "$SQLITE" "$CHROMA" "$CONFIG"; do
  if [ ! -f "$f" ]; then
    echo "ERROR: Missing $f"
    exit 1
  fi
  echo "OK: $(basename "$f")"
done

rm -rf "$DRILL"
mkdir -p "$DRILL/data" "$DRILL/config/environment"

cp -f "$SQLITE" "$DRILL/data/nexus.db"
tar xzf "$CHROMA" -C "$DRILL/data"
tar xzf "$CONFIG" -C "$DRILL"

PYTHON="${ROOT}/.venv/bin/python3"
if [ ! -x "$PYTHON" ]; then
  PYTHON=python3
fi

"$PYTHON" - <<PY
import sqlite3, sys
live = "$ROOT/data/nexus.db"
restored = "$DRILL/data/nexus.db"
for label, path in [("restored", restored), ("live", live)]:
    con = sqlite3.connect(path)
    ok = con.execute("PRAGMA integrity_check").fetchone()[0]
    users = con.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    print(f"{label}: integrity={ok} users={users}")
    if ok != "ok":
        sys.exit(1)
    con.close()
print("PASS: SQLite integrity OK")
PY

if [ ! -d "$DRILL/data/chroma" ]; then
  echo "ERROR: Chroma not restored"
  exit 1
fi
echo "OK: Chroma restored ($(du -sh "$DRILL/data/chroma" | cut -f1))"

if [ ! -f "$DRILL/config/environment/.env" ]; then
  echo "ERROR: Config .env missing"
  exit 1
fi
echo "OK: Config restored"

echo ""
echo "✅ Restore drill PASSED"
echo "   Temp dir: $DRILL"
echo "   Production untouched."
echo "=========================================="
