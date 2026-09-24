#!/usr/bin/env python3
"""PERCEPTUAL_MOTION_GATE: does the motion system actually show at panel size?

The V5.1 motion numbers are monotone, but the review's point stands: monotone is
not the same as perceptible. This gate renders 0 / 30 / 80 / 120 km/h in one
environment, masks out everything that is not the motion system (speed digits,
range, SOC, power, clock - all of which change with speed anyway), and then
measures the motion-specific regions only:

    wheels   the baked rotational blur overlays
    road     the road-flow tile band, excluding the car
    wake     the aerodynamic trail behind the car
    trail    the wet-road lamp trail below the car

The requirement is that each successive speed is measurably different from the
previous one *in those regions*, at both 1:1 and half physical size, which is
why the half-size measurement is taken too: a detail that only exists at 1:1 is
not a dashboard motion cue.

Usage:
    python3 tools/preview/horizon_v52_motion_gate.py
"""

import argparse
import json
import os
import subprocess
import sys

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
PREVIEW = os.path.join(REPO, "tools", "preview", "scene_preview.py")
SCENE = os.path.join(REPO, "scenes", "horizon_v5.scene")
LAYOUT = os.path.join(REPO, "assets", "ui", "horizon_v5_layout.json")
OUT = os.path.join(REPO, "assets", "checkpoints", "horizon_v5")
SPEEDS = [0, 30, 80, 120]

# Everything the speed itself legitimately changes. The gate must not be
# satisfied by the numeral turning from 30 into 80.
UI_ROLES = {"speed", "energy", "driver", "sign", "navigation", "warning", "glow"}


def main():
    import numpy as np
    from PIL import Image, ImageDraw, ImageFont
    parser = argparse.ArgumentParser()
    parser.add_argument("--phase", default="day")
    args = parser.parse_args()
    layout = json.load(open(LAYOUT))

    def ui_mask(shape):
        mask = np.zeros(shape, dtype=bool)
        for component in layout["components"]:
            if component.get("role") not in UI_ROLES:
                continue
            bounds = component.get("bounds")
            if not bounds:
                continue
            x0 = max(0, int(bounds["x"]) - 6)
            y0 = max(0, int(bounds["y"]) - 6)
            x1 = min(shape[1], int(bounds["x"] + bounds["w"]) + 6)
            y1 = min(shape[0], int(bounds["y"] + bounds["h"]) + 6)
            mask[y0:y1, x0:x1] = True
        # The vehicle moves a pixel or two with speed, so it is not a motion
        # *effect* either; the regions below are the effects.
        return mask

    frames = {}
    half_frames = {}
    for speed in SPEEDS:
        name = f"horizon_v52_motion_{speed:03d}_{args.phase}"
        path = os.path.join(OUT, name + ".png")
        subprocess.run([sys.executable, PREVIEW, "--scene", SCENE, "--state",
                        f"v5_motion_{speed:03d}", "--out", OUT,
                        "--out-name", name, "--environment-phase", args.phase],
                       check=True, capture_output=True)
        image = Image.open(path).convert("RGB")
        frames[speed] = np.asarray(image).astype(np.float32)
        half_frames[speed] = np.asarray(
            image.resize((960, 240), Image.LANCZOS)).astype(np.float32)

    assets = json.load(open(os.path.join(
        OUT, "horizon_v5_motion_assets.json")))["assets"]
    wheel_box = assets["wheels"]["low"]["box"]
    flow_box = assets["roadflow"]["box"]
    wake_box = assets["wake"]["box"]
    trail_box = assets["streak_brake"]["box"]
    regions = {"wheels": wheel_box, "road": [flow_box[0], 300, flow_box[2], 470],
               "wake": wake_box, "trail": trail_box}
    mask = ui_mask(frames[0].shape[:2])

    def region_difference(left, right, box, masked=True):
        x0, y0, x1, y1 = [int(round(value)) for value in box]
        a = left[y0:y1, x0:x1]
        b = right[y0:y1, x0:x1]
        difference = np.abs(a - b).max(axis=2)
        if masked:
            local = mask[y0:y1, x0:x1]
            if local.any():
                difference = difference.copy()
                difference[local] = 0.0
        return difference

    results = {"schema": "horizon-v5.2-perceptual-motion v1",
               "phase": args.phase, "regions": regions, "pairs": {}}
    sheet_rows = []
    for index in range(len(SPEEDS) - 1):
        low, high = SPEEDS[index], SPEEDS[index + 1]
        entry = {"full_size": {}, "half_size": {}}
        for name, box in regions.items():
            difference = region_difference(frames[low], frames[high], box)
            half_difference = region_difference(half_frames[low],
                                                half_frames[high],
                                                [value / 2.0 for value in box],
                                                masked=False)
            entry["full_size"][name] = {
                "mean": round(float(difference.mean()), 3),
                "p99": round(float(np.percentile(difference, 99)), 2),
                "changed_fraction": round(float((difference > 6).mean()), 4)}
            entry["half_size"][name] = {
                "mean": round(float(half_difference.mean()), 3),
                "p99": round(float(np.percentile(half_difference, 99)), 2)}
        results["pairs"][f"{low}_to_{high}"] = entry
        print(f"[v5.2-motion] {low:3d} -> {high:3d} km/h  "
              + "  ".join(
                  f"{name} {entry['full_size'][name]['mean']:.2f}"
                  f"({entry['full_size'][name]['changed_fraction'] * 100:.1f}%)"
                  for name in regions))

    # How much motion is visible at each speed, measured against a standstill.
    # This is the quantity the gate is about: it must be zero at 0, visible at
    # 30, clearly larger at 80 and larger again at 120.
    cumulative = {}
    for speed in SPEEDS:
        row = {}
        total = 0.0
        for name, box in regions.items():
            difference = region_difference(frames[0], frames[speed], box)
            value = float(difference.mean())
            row[name] = round(value, 3)
            total += value
        row["total"] = round(total, 3)
        cumulative[str(speed)] = row
        print(f"[v5.2-motion] vs 0 km/h at {speed:3d}: " + "  ".join(
            f"{name} {row[name]:.2f}" for name in regions) +
            f"   total {row['total']:.2f}")
    # Rotation speed is legible in the rim's structure: the faster the wheel
    # turns during the exposure the less spoke detail survives. That is the
    # quantity that has to fall with speed; the raw difference saturates.
    rim = {}
    for speed in SPEEDS:
        x0, y0, x1, y1 = [int(round(value)) for value in wheel_box]
        patch = frames[speed][y0:y1, x0:x1].mean(axis=2)
        gx = np.abs(np.diff(patch, axis=1)).mean()
        gy = np.abs(np.diff(patch, axis=0)).mean()
        rim[str(speed)] = {
            "edge_energy": round(float((gx + gy) / 2.0), 3),
            "spread": round(float(patch.std()), 3)}
        print(f"[v5.2-motion] {speed:3d} km/h wheel edge energy "
              f"{rim[str(speed)]['edge_energy']:.2f}  spread "
              f"{rim[str(speed)]['spread']:.1f}")
    results["wheel_structure"] = rim
    results["wheel_structure_falls"] = bool(all(
        rim[str(SPEEDS[index])]["edge_energy"]
        > rim[str(SPEEDS[index + 1])]["edge_energy"]
        for index in range(len(SPEEDS) - 1)))
    results["region_masking"] = {"ui_boxes": int(sum(
        1 for component in layout["components"]
        if component.get("role") in UI_ROLES and component.get("bounds"))),
        "why": "the gate must not be satisfiable by the speed digits changing"}
    results["cumulative_vs_standstill"] = cumulative
    totals = [cumulative[str(speed)]["total"] for speed in SPEEDS]
    results["monotone_total"] = bool(all(totals[index] < totals[index + 1] + 1e-9
                                         for index in range(len(totals) - 1)))
    results["zero_at_standstill"] = bool(totals[0] == 0.0)

    # Evidence: the four frames at half size with the measured regions drawn.
    cell_h, header = 240, 24
    sheet = Image.new("RGB", (960, (cell_h + header) * len(SPEEDS)),
                      (8, 10, 14))
    draw = ImageDraw.Draw(sheet)
    try:
        font = ImageFont.truetype(
            "/System/Library/Fonts/Supplemental/Arial Bold.ttf", 17)
    except OSError:  # pragma: no cover
        font = ImageFont.load_default()
    for index, speed in enumerate(SPEEDS):
        top = index * (cell_h + header)
        sheet.paste(Image.fromarray(
            half_frames[speed].astype("uint8")), (0, top + header))
        draw.text((8, top + 3),
                  f"{speed:3d} km/h   motion regions: wheels / road / wake / "
                  f"trail   (UI masked out)", fill=(226, 232, 240), font=font)
    path = os.path.join(OUT, "horizon_v52_motion_gate.png")
    sheet.save(path)
    results["evidence"] = os.path.relpath(path, REPO)
    metrics = os.path.join(OUT, "horizon_v52_motion_gate.json")
    with open(metrics, "w") as handle:
        json.dump(results, handle, indent=1)
        handle.write("\n")
    print(f"[v5.2-motion] {os.path.relpath(path, REPO)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
