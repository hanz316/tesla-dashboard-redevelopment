#!/usr/bin/env bash
# Regenerate the Door_FL benchmark matrix (V3 task Parts 10, 11, 15).
#
# 3 runtime vehicle widths x frame rates, and BOTH directions. Open and close
# are separate animations with independent timing and independent easing; close
# is never a runtime playback of open in reverse.
#
# The per-direction DURATION is held constant, so a higher frame rate means
# more frames, never a faster door.
#
# Usage:
#   bash tools/blender/render_door_benchmark.sh
#   WIDTHS="600" FPS_LIST="30" DIRECTION=open bash tools/blender/render_door_benchmark.sh
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO_ROOT"

BL="${BLENDER:-/Applications/Blender.app/Contents/MacOS/Blender}"
OUT_ROOT="${OUT_ROOT:-assets/rendered/door_fl}"
SAMPLES="${SAMPLES:-48}"
ENGINE="${ENGINE:-eevee}"
MATERIAL="${MATERIAL:-v3}"
LOOK="${LOOK:-normal}"
WIDTHS="${WIDTHS:-400 600 800}"
FPS_LIST="${FPS_LIST:-30 60}"
DIRECTION="${DIRECTION:-both}"

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
            --engine "$ENGINE" --samples "$SAMPLES" \
            --material "$MATERIAL" --look "$LOOK" \
            --direction "$DIRECTION" 2>&1 \
            | grep -E "frame [0-9]+ |RENDER_TIME|Traceback|Error" || true
    done
done

echo "door benchmark sequences written to $OUT_ROOT"
echo "next: python3 tools/assets/report_animation_budget.py \\"
echo "        --full $OUT_ROOT/600_30/open --delta <delta dir> --label 600/30"
