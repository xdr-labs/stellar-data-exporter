#!/usr/bin/env bash
set -euo pipefail

DIST_DIR="${1:-dist}"
OUTPUT="${2:-$DIST_DIR/SHA256SUMS}"

mapfile -t artifacts < <(
  find "$DIST_DIR" -maxdepth 1 -type f \
    \( -name '*.whl' -o -name '*.tar.gz' \) \
    -printf '%f\n' | sort
)

if [[ "${#artifacts[@]}" -ne 2 ]]; then
  echo "Expected exactly one wheel and one source archive in $DIST_DIR" >&2
  exit 1
fi

wheel_count=0
sdist_count=0
for artifact in "${artifacts[@]}"; do
  [[ "$artifact" == *.whl ]] && ((wheel_count += 1))
  [[ "$artifact" == *.tar.gz ]] && ((sdist_count += 1))
done

if [[ "$wheel_count" -ne 1 || "$sdist_count" -ne 1 ]]; then
  echo "Expected exactly one wheel and one source archive in $DIST_DIR" >&2
  exit 1
fi

for artifact in "${artifacts[@]}"; do
  sha256sum "$DIST_DIR/$artifact"
done | tee "$OUTPUT"

sha256sum --check "$OUTPUT"

echo "RELEASE_ARTIFACT_HASHES=PASS"
