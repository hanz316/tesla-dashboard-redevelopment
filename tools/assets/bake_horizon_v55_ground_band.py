#!/usr/bin/env python3
"""Bake the near-ground band that carries the environment's parallax.

The environment plate is a still place. A driving car needs the near ground to
travel past faster than the distance does, and the cheap honest way to get that
is two layers, not a 3D scene: the plate stays where it is (the far layer
moves by nothing) and the road/ground below the horizon is drawn again as its
own band, which the runtime translates along the screen motion vector.

The band is cut slightly below the measured horizon row and feathered upward,
so where the band ends the plate underneath is what shows: no seam, no gap and
nothing invented, because every pixel in the band is a plate pixel.

Usage:
    python3 tools/assets/bake_horizon_v55_ground_band.py
"""

import argparse
import json
import os
import sys

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
UI = os.path.join(REPO, "assets", "ui")
REPORT = os.path.join(REPO, "assets", "checkpoints", "horizon_v5",
                      "horizon_v55_ground_band.json")

# The measured composition: cars sit on a ground plane whose horizon is this
# row on the 1920x480 panel.
HORIZON_ROW = 167
# The band starts below the horizon and feathers upward over this many rows.
BAND_OFFSET = 6
FEATHER = 22

PHASES = {
    "night": "horizon_v5_background.png",
    "day": "horizon_v5_background_day.png",
    "dawn": "horizon_v5_background_dawn.png",
    "dusk": "horizon_v5_background_dusk.png",
}


def main():
    import numpy as np
    from PIL import Image

    parser = argparse.ArgumentParser()
    parser.add_argument("--ui", default=UI)
    parser.add_argument("--report", default=REPORT)
    parser.add_argument("--horizon-row", type=int, default=HORIZON_ROW)
    parser.add_argument("--offset", type=int, default=BAND_OFFSET)
    parser.add_argument("--feather", type=int, default=FEATHER)
    args = parser.parse_args()

    top = args.horizon_row + args.offset
    report = {"schema": "horizon-v5.5-ground-band v1",
              "why": "the near ground moves, the distance does not; the "
                     "difference between the two layers is the parallax",
              "horizon_row": args.horizon_row,
              "band_top": top,
              "feather": args.feather,
              "phases": {}}
    for phase, name in PHASES.items():
        source = os.path.join(args.ui, name)
        if not os.path.isfile(source):
            print(f"[v5.5-ground] missing {name}, skipped")
            continue
        plate = Image.open(source).convert("RGBA")
        width, height = plate.size
        band = np.asarray(plate).astype(np.float32).copy()
        rows = np.arange(height, dtype=np.float32)
        # Above the band top the layer is transparent; the ramp is a smoothstep
        # so the seam between band and plate cannot show a line.
        ramp = np.clip((rows - top) / float(max(1, args.feather)), 0.0, 1.0)
        ramp = ramp * ramp * (3.0 - 2.0 * ramp)
        band[:, :, 3] *= ramp[:, None]
        # Cropped to the band itself, so the layout's rectangle and the bitmap
        # are the same size: the same rule every other baked layer follows.
        band = band[top:, :, :]
        out_name = ("horizon_v5_ground.png" if phase == "night"
                    else f"horizon_v5_ground_{phase}.png")
        out = os.path.join(args.ui, out_name)
        Image.fromarray(np.clip(band, 0, 255).astype("uint8"), "RGBA").save(out)
        report["phases"][phase] = {
            "source": os.path.relpath(source, REPO),
            "file": os.path.relpath(out, REPO),
            "box": [0, top, width, height],
            "band_top": top,
            "band_height_px": height - top,
            "band_size": [width, height - top],
            "alpha_pixels": int((band[:, :, 3] > 0).sum()),
            "decoded_rgba_bytes": width * (height - top) * 4}
        print(f"[v5.5-ground] {phase:5s} band {width}x{height - top} "
              f"from row {top}")
    os.makedirs(os.path.dirname(args.report), exist_ok=True)
    with open(args.report, "w") as handle:
        json.dump(report, handle, indent=1)
        handle.write("\n")
    print(f"[v5.5-ground] {os.path.relpath(args.report, REPO)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
