#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BUILD_DIR="${BUILD_DIR:-$ROOT/build}"
OUT_DIR="${1:-$ROOT/product-screenshots}"

cmake -S "$ROOT" -B "$BUILD_DIR" -DCMAKE_BUILD_TYPE=Release
cmake --build "$BUILD_DIR" --parallel --target dashboard_product_simulator
mkdir -p "$OUT_DIR"

BASE="$OUT_DIR/dashboard"
"$BUILD_DIR/dashboard_product_simulator" --screenshot "$BASE" --all-pages

printf 'Rendered seven product pages to %s\n' "$OUT_DIR"
for i in 1 2 3 4 5 6 7; do
  test -f "$BASE-page-$i.bmp"
done
