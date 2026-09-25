#!/usr/bin/env bash
set -euo pipefail

ARCHIVE="${1:-/var/backups/stellar-data-exporter-state.tgz}"

if [[ ! -f "$ARCHIVE" ]]; then
  echo "Backup archive does not exist: $ARCHIVE" >&2
  exit 1
fi

TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

tar -tzf "$ARCHIVE" | python3 -c '
import sys
for raw in sys.stdin:
    path = raw.strip()
    if path.startswith("/") or ".." in path.split("/"):
        raise SystemExit(f"unsafe archive path: {path}")
'
tar -xzf "$ARCHIVE" -C "$TMP_DIR"

STATE_DIR="$TMP_DIR/stellar-data-exporter"
[[ -d "$STATE_DIR" ]] || { echo "Missing state directory in backup" >&2; exit 1; }

python3 - "$STATE_DIR" <<'PY'
import sqlite3
import sys
from pathlib import Path

root = Path(sys.argv[1])
for name in ("export-jobs.sqlite3", "export-schedules.sqlite3"):
    db = root / name
    if not db.exists():
        continue
    with sqlite3.connect(f"file:{db}?mode=ro", uri=True) as conn:
        result = conn.execute("PRAGMA integrity_check").fetchone()[0]
    if result != "ok":
        raise SystemExit(f"{name}: integrity_check={result}")
PY

echo "Restore test PASS: $ARCHIVE"
