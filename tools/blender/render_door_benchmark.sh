#!/usr/bin/env bash
# Regenerate the Door_FL benchmark matrix (task Parts I-K).
#
# 3 runtime vehicle widths x 3 frame rates = 9 sequences. The animation
# DURATION is held constant, so higher fps means more frames, never a faster
# door: 24 fps -> 17 frames, 30 fps -> 21, 60 fps -> 40 for the default
# 0.65 s / 52 deg animation.
#
# Usage:
#   bash tools/blender/render_door_benchmark.sh
#   WIDTHS="600" FPS_LIST="30" bash tools/blender/render_door_benchmark.sh
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO_ROOT"

BL="${BLENDER:-/Applications/Blender.app/Contents/MacOS/Blender}"
OUT_ROOT="${OUT_ROOT:-assets/rendered/door_fl}"
SAMPLES="${SAMPLES:-48}"
ENGINE="${ENGINE:-eevee}"
WIDTHS="${WIDTHS:-400 600 800}"
FPS_LIST="${FPS_LIST:-24 30 60}"

if [[ ! -x "$BL" ]]; then
    echo "Blender not found at: $BL" >&2
    exit 1
fi

for width in $WIDTHS; do
    for fps in $FPS_LIST; do
        out="$OUT_ROOT/${width}_${fps}"
        echo "=== ${width}px @ ${fps}fps -> $out ==="
        "$BL" -b -P tools/blender/render_door_animation.py -- \
            --fps "$fps" --vehicle-width "$width" --out "$out" \
            --engine "$ENGINE" --samples "$SAMPLES" 2>&1 \
            | grep -E "frame [0-9]+ |RENDER_TIME|Traceback|Error" || true
    done
done

echo "door benchmark sequences written to $OUT_ROOT"
echo "next: python3 tools/assets/check_budget.py --sequence --alpha-crop $OUT_ROOT/600_30"
