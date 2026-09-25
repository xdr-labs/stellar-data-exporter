#!/usr/bin/env bash
set -euo pipefail

STATE_DIR="${1:-/var/lib/stellar-data-exporter}"
OUTPUT="${2:-/var/backups/stellar-data-exporter-state.tgz}"

if [[ ! -d "$STATE_DIR" ]]; then
  echo "State directory does not exist: $STATE_DIR" >&2
  exit 1
fi

if [[ "$STATE_DIR" == "/var/lib/stellar-data-exporter" ]] \
  && command -v systemctl >/dev/null 2>&1 \
  && systemctl is-active --quiet stellar-data-exporter 2>/dev/null; then
  echo "Stop stellar-data-exporter before taking a state backup." >&2
  exit 1
fi

mkdir -p "$(dirname "$OUTPUT")"
umask 077
TMP="${OUTPUT}.tmp.$$"
trap 'rm -f "$TMP"' EXIT

tar -C "$(dirname "$STATE_DIR")" -czf "$TMP" "$(basename "$STATE_DIR")"
chmod 0600 "$TMP"
mv "$TMP" "$OUTPUT"
trap - EXIT

echo "$OUTPUT"
