#!/usr/bin/env python3
"""Measure what each chase yaw does to the car's presented size.

The framing solver holds the projected *width*, which is right for a still: the
reference car is a known number of pixels wide. Orbit the camera towards the
rear, though, and the car foreshortens - the width stays pinned while the car
grows taller on screen, which is exactly the scale pumping a chase view must not
have. So each yaw's own rendered height is measured here and the runtime scales
the presented layer by the ratio, which keeps the car the same size on screen
while its projected shape changes with the view.

Usage:
    python3 tools/assets/measure_horizon_v55_chase_boxes.py
"""

import argparse
import json
import os
import sys

import numpy as np
from PIL import Image

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
RENDERED = os.path.join(REPO, "assets", "rendered", "vehicle", "horizon_v5")
REPORT = os.path.join(REPO, "assets", "checkpoints", "horizon_v5",
                      "horizon_v55_chase_boxes.json")


def car_pass(phase, yaw):
    if yaw > 0:
        # Chase variants always live under their phase directory, night too.
        return os.path.join(RENDERED, "chase", f"yaw{int(round(yaw)):02d}",
                            phase, "car", "base", "000.png")
    tail = "" if phase == "night" else phase
    return os.path.join(RENDERED, tail, "car", "base", "000.png")


def measure(path):
    alpha = np.asarray(Image.open(path).convert("RGBA"))[:, :, 3]
    ys, xs = np.nonzero(alpha > 8)
    if not xs.size:
        return None
    box = [int(xs.min()), int(ys.min()), int(xs.max() + 1), int(ys.max() + 1)]
    return {"box": box, "width": box[2] - box[0], "height": box[3] - box[1],
            "centre_x": (box[0] + box[2]) / 2.0, "contact_y": box[3],
            "source": os.path.relpath(path, REPO)}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--phases", default="night,day,dawn,dusk")
    parser.add_argument("--report", default=REPORT)
    args = parser.parse_args()
    chase = os.path.join(RENDERED, "chase")
    yaws = sorted(float(int(name[3:])) for name in os.listdir(chase)
                  if name.startswith("yaw")) if os.path.isdir(chase) else []
    report = {"schema": "horizon-v5.5-chase-boxes v1",
              "why": "the projected width is pinned by the framing solver and "
                     "the height foreshortens as the camera orbits; the ratio "
                     "of the two is the correction that keeps the presented "
                     "car the same size",
              "phases": {}}
    for phase in args.phases.split(","):
        entries = {}
        for yaw in [0.0] + yaws:
            path = car_pass(phase, yaw)
            if not os.path.isfile(path):
                continue
            measured = measure(path)
            if measured:
                entries[f"{yaw:g}"] = measured
        base = entries.get("0")
        if base:
            for key, entry in entries.items():
                entry["height_ratio_vs_standstill"] = round(
                    entry["height"] / float(base["height"]), 4)
                entry["width_ratio_vs_standstill"] = round(
                    entry["width"] / float(base["width"]), 4)
        report["phases"][phase] = entries
        print(f"[v5.5-boxes] {phase:5s} " + "  ".join(
            f"{key}:{entry['height']}px h, "
            f"x{entry.get('height_ratio_vs_standstill', 1.0):.3f}"
            for key, entry in sorted(entries.items(), key=lambda kv: float(kv[0]))))
    os.makedirs(os.path.dirname(args.report), exist_ok=True)
    with open(args.report, "w") as handle:
        json.dump(report, handle, indent=1)
        handle.write("\n")
    print(f"[v5.5-boxes] {os.path.relpath(args.report, REPO)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
