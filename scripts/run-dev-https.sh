#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

exec "$ROOT/.venv/bin/python" -m app.cli \
  --host 0.0.0.0 \
  --port 8787
