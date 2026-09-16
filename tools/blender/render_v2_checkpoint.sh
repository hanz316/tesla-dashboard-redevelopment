#!/usr/bin/env bash
# Regenerate the Vehicle Visual V2 static checkpoint (task Parts A-H).
#
# Mac-only offline asset step: the T113 never runs Blender, it only reads the
# final PNGs. Six renders, chosen so the checkpoint answers exactly three
# questions:
#   * paint / reflection quality      -> v2a silver01 vs silver03
#   * camera finalisation             -> v2a / v2b / v2c
#   * engine choice                   -> cycles vs eevee at the same camera
#   * does the reflection studio work -> cycles studio vs cycles --no-studio
#
# Usage:
#   bash tools/blender/render_v2_checkpoint.sh
#   BLENDER=/path/to/Blender SAMPLES=64 OUT=/tmp/v2 bash tools/blender/render_v2_checkpoint.sh
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO_ROOT"

BL="${BLENDER:-/Applications/Blender.app/Contents/MacOS/Blender}"
OUT="${OUT:-assets/rendered/v2}"
SAMPLES="${SAMPLES:-96}"

if [[ ! -x "$BL" ]]; then
    echo "Blender not found at: $BL" >&2
    echo "Set BLENDER=/path/to/Blender and retry." >&2
    exit 1
fi

mkdir -p "$OUT"

run() {
    echo "=== $* ==="
    "$BL" -b -P tools/blender/render_vehicle_visual_v2.py -- "$@"
}

# Engine A/B + studio proof at the same camera, so the only variable changes.
run --body silver01 --camera v2a --engine cycles --samples "$SAMPLES" \
    --out "$OUT/v2a_silver01_cycles_studio.png"
run --body silver01 --camera v2a --engine cycles --samples "$SAMPLES" --no-studio \
    --out "$OUT/v2a_silver01_cycles_nostudio.png"
run --body silver01 --camera v2a --engine eevee --samples 192 \
    --out "$OUT/v2a_silver01_eevee_studio.png"

# Camera finalisation candidates.
run --body silver01 --camera v2b --engine cycles --samples "$SAMPLES" \
    --out "$OUT/v2b_silver01_cycles_studio.png"
run --body silver01 --camera v2c --engine cycles --samples "$SAMPLES" \
    --out "$OUT/v2c_silver01_cycles_studio.png"

# Second paint option at the same camera.
run --body silver03 --camera v2a --engine cycles --samples "$SAMPLES" \
    --out "$OUT/v2a_silver03_cycles_studio.png"

echo "checkpoint renders written to $OUT"
