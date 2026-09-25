#!/usr/bin/env bash
set -euo pipefail

uv run python -m compileall -q app
node --check app/static/app.js
bash -n scripts/*.sh
git diff --check

uv run --extra dev pytest -q   tests/test_production_deployment.py   tests/test_paths.py

echo "RELEASE_PREFLIGHT=PASS"
