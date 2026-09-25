#!/usr/bin/env bash
set -euo pipefail

DIST_DIR="${1:-dist}"

uv run --extra dev pytest -q
node --check app/static/app.js
git diff --check

rm -rf "$DIST_DIR"
mkdir -p "$DIST_DIR"
BUILD_LOG="$(mktemp)"
trap 'rm -f "$BUILD_LOG"' EXIT

uv build --out-dir "$DIST_DIR" >"$BUILD_LOG" 2>&1
cat "$BUILD_LOG"
if grep -q "Package would be ignored" "$BUILD_LOG"; then
  echo "setuptools emitted ambiguous package-data warning" >&2
  exit 1
fi

uv run python tools/verify_release_artifacts.py "$DIST_DIR"

echo "RELEASE_QUALIFICATION=PASS"
