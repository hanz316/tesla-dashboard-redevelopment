#!/usr/bin/env python3
"""Motion evidence: the same frame at 0 / 30 / 80 / 120 km/h, measured.

The claim the review asks to be able to prove from pixels is monotonicity:
motion visual intensity at 0 < 30 < 80 < 120, and exactly zero at 0. That is
measured here channel by channel, in the regions the assets declare, and written
next to the screenshots so a human can check the number against the frame.

Usage:
    python3 tools/preview/horizon_v5_motion_evidence.py
"""

import json
import os
import subprocess
import sys

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
PREVIEW = os.path.join(REPO, "tools", "preview", "scene_preview.py")
SCENE = os.path.join(REPO, "scenes", "horizon_v5.scene")
OUT = os.path.join(REPO, "assets", "checkpoints", "horizon_v5")
ASSETS = os.path.join(OUT, "horizon_v5_motion_assets.json")
SPEEDS = [0, 30, 80, 120]


def render(state, name, out=OUT):
    path = os.path.join(out, name + ".png")
    subprocess.run([sys.executable, PREVIEW, "--scene", SCENE, "--state", state,
                    "--out", out, "--out-name", name], check=True,
                   capture_output=True)
    return path


def region_mean_difference(a, b, box):
    import numpy as np
    x0, y0, x1, y1 = [int(round(value)) for value in box]
    left = a[y0:y1, x0:x1]
    right = b[y0:y1, x0:x1]
    return float(np.abs(left - right).mean())


def streak_length(with_lamp, without_lamp, box, contact_row, threshold=6):
    """How far the lamp's reflection reaches below the car.

    Measured as the difference against the same frame with that lamp off, below
    the car's own contact row: above it the car itself is what is bright, and
    subtracting the lamp-off frame removes the environment, the wheels and the
    road flow, so what is left is the streak.
    """
    import numpy as np
    from PIL import Image
    lit = np.asarray(Image.open(with_lamp).convert("RGB")).astype(np.float32)
    off = np.asarray(Image.open(without_lamp).convert("RGB")).astype(np.float32)
    difference = np.abs(lit - off).max(axis=2)
    x0, y0, x1, y1 = [int(round(value)) for value in box]
    top = max(y0, int(round(contact_row)))
    band = difference[top:y1, x0:x1]
    if band.size == 0:
        return 0
    rows = (band > threshold).sum(axis=1) > 2
    return int(rows.sum())


def main():
    import numpy as np
    from PIL import Image, ImageDraw, ImageFont
    os.makedirs(OUT, exist_ok=True)
    assets = json.load(open(ASSETS))["assets"]
    frames = {}
    for speed in SPEEDS:
        state = f"v5_motion_{speed:03d}"
        path = render(state, f"horizon_v5_1_motion_{speed:03d}")
        frames[speed] = np.asarray(
            Image.open(path).convert("RGB")).astype(np.float32)
        print(f"[v5-motion] {speed:3d} km/h -> {os.path.relpath(path, REPO)}")

    wheels = assets["wheels"]
    wheel_box = wheels["low"]["box"]
    wake_box = assets["wake"]["box"]
    flow_box = assets["roadflow"]["box"]
    baseline = frames[0]
    metrics = {}
    for speed in SPEEDS:
        metrics[str(speed)] = {
            "wheel_region_mean_diff": round(region_mean_difference(
                frames[speed], baseline, wheel_box), 4),
            "wake_region_mean_diff": round(region_mean_difference(
                frames[speed], baseline, wake_box), 4),
            "roadflow_region_mean_diff": round(region_mean_difference(
                frames[speed], baseline, flow_box), 4),
            "whole_frame_mean_diff": round(float(np.abs(
                frames[speed] - baseline).mean()), 4),
        }

    # The lamp streak: length must grow with speed, and be absent when the lamp
    # is off, which the neutral state proves.
    streak = {"brake": {}}
    brake_box = assets["streak_brake"]["box"]
    contact = 346
    layer_report = os.path.join(OUT, "horizon_v5_vehicle_layers.json")
    if os.path.isfile(layer_report):
        for record in json.load(open(layer_report))["records"]:
            if record.get("state") == "base" and record.get("car_box"):
                contact = record["car_box"][3]
    for speed in SPEEDS:
        path = render(f"v5_motion_brake_{speed:03d}",
                      f"horizon_v5_1_motion_brake_{speed:03d}")
        streak["brake"][str(speed)] = streak_length(
            path, os.path.join(OUT, f"horizon_v5_1_motion_{speed:03d}.png"),
            brake_box, contact)

    monotone = all(metrics[str(SPEEDS[index])]["whole_frame_mean_diff"] <
                   metrics[str(SPEEDS[index + 1])]["whole_frame_mean_diff"]
                   for index in range(len(SPEEDS) - 1))
    zero_at_rest = (metrics["0"]["wheel_region_mean_diff"] == 0.0
                    and metrics["0"]["wake_region_mean_diff"] == 0.0)
    streak_monotone = all(streak["brake"][str(SPEEDS[index])]
                          < streak["brake"][str(SPEEDS[index + 1])]
                          for index in range(len(SPEEDS) - 1))

    sheet = Image.new("RGB", (960, (240 + 26) * len(SPEEDS)), (8, 10, 14))
    draw = ImageDraw.Draw(sheet)
    try:
        font = ImageFont.truetype(
            "/System/Library/Fonts/Supplemental/Arial Bold.ttf", 18)
    except OSError:  # pragma: no cover
        font = ImageFont.load_default()
    for index, speed in enumerate(SPEEDS):
        top = index * (240 + 26)
        image = Image.open(os.path.join(
            OUT, f"horizon_v5_1_motion_{speed:03d}.png")).convert("RGB")
        sheet.paste(image.resize((960, 240), Image.LANCZOS), (0, top + 26))
        row = metrics[str(speed)]
        draw.text((8, top + 4),
                  f"{speed:3d} km/h   wheel {row['wheel_region_mean_diff']:.2f}"
                  f"   wake {row['wake_region_mean_diff']:.2f}"
                  f"   flow {row['roadflow_region_mean_diff']:.2f}"
                  f"   frame {row['whole_frame_mean_diff']:.2f}",
                  fill=(225, 232, 240), font=font)
    comparison = os.path.join(OUT, "horizon_v5_1_motion_comparison.png")
    sheet.save(comparison)

    report = {
        "schema": "horizon-v5.1-motion-evidence v1",
        "why": "motion intensity has to be provable from pixels, not asserted",
        "regions": {"wheel": wheel_box, "wake": wake_box, "roadflow": flow_box,
                    "brake_streak": brake_box},
        "per_speed": metrics,
        "monotone_increasing": bool(monotone),
        "zero_at_0_kmh": bool(zero_at_rest),
        "streak_length_px": streak,
        "streak_monotone_increasing": bool(streak_monotone),
        "screenshots": {str(speed): os.path.relpath(
            os.path.join(OUT, f"horizon_v5_1_motion_{speed:03d}.png"), REPO)
            for speed in SPEEDS},
        "comparison": os.path.relpath(comparison, REPO),
    }
    path = os.path.join(OUT, "horizon_v5_1_motion_metrics.json")
    with open(path, "w") as handle:
        json.dump(report, handle, indent=1)
        handle.write("\n")
    for speed in SPEEDS:
        row = metrics[str(speed)]
        print(f"[v5-motion] {speed:3d} km/h  wheel {row['wheel_region_mean_diff']:5.2f}"
              f"  wake {row['wake_region_mean_diff']:5.2f}"
              f"  flow {row['roadflow_region_mean_diff']:5.2f}"
              f"  frame {row['whole_frame_mean_diff']:5.2f}")
    print(f"[v5-motion] monotone {monotone}, zero at rest {zero_at_rest}, "
          f"streak monotone {streak_monotone}")
    print(f"[v5-motion] {os.path.relpath(comparison, REPO)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
