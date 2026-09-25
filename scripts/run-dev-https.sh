#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

exec "$ROOT/.venv/bin/python" -m uvicorn app.main:app \
  --host 0.0.0.0 \
  --port 8787 \
  --ssl-keyfile "$ROOT/.tls/dev-atlas.key" \
  --ssl-certfile "$ROOT/.tls/dev-atlas.crt"
