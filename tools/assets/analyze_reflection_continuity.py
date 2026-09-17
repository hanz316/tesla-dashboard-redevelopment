#!/usr/bin/env python3
"""Measure how straight the reflection strips stay across the body.

A Class-A reflection line on a clean surface is a straight, unbroken ridge.
Surface waviness moves the ridge up and down; pinching or a bad normal breaks
it. Both are measurable without looking at the image:

    breaks    columns inside the car where the ridge is missing entirely
    waviness  RMS of the discrete second difference of the ridge position
              (a straight line scores 0, a wobble scores high)
    spread    mean ridge thickness, which blows up where a reflection pinches

Reported per view so original vs clean normals can be compared numerically.

Usage:
    python3 tools/assets/analyze_reflection_continuity.py img.png [...]
"""

import argparse
import json
import os
import sys

try:
    from PIL import Image
except ImportError:  # pragma: no cover
    sys.exit("Pillow required")

import numpy as np


def analyse(path, brightness=0.55):
    img = Image.open(path).convert("RGBA")
    arr = np.asarray(img).astype(np.float32)
    lum = arr[..., :3].mean(axis=2)
    car = arr[..., 3] > 8
    if car.sum() < 100:
        return None

    inside = lum[car]
    peak = float(np.percentile(inside, 99.5))
    if peak <= 1.0:
        return None
    ridge_mask = car & (lum > peak * brightness)

    ys, xs = np.nonzero(car)
    x0, x1 = int(xs.min()), int(xs.max())

    positions = []
    thickness = []
    missing = 0
    for x in range(x0, x1 + 1):
        col = np.nonzero(ridge_mask[:, x])[0]
        if col.size == 0:
            positions.append(np.nan)
            missing += 1
        else:
            positions.append(float(col.mean()))
            thickness.append(float(col.max() - col.min() + 1))
    pos = np.array(positions, dtype=np.float32)

    # Waviness only over contiguous runs, so a gap does not create a spike.
    acc = []
    run = []
    for v in pos:
        if np.isnan(v):
            if len(run) >= 4:
                acc.append(np.asarray(run, dtype=np.float32))
            run = []
        else:
            run.append(v)
    if len(run) >= 4:
        acc.append(np.asarray(run, dtype=np.float32))

    second = []
    for seg in acc:
        d2 = seg[2:] - 2 * seg[1:-1] + seg[:-2]
        second.append(float(np.sqrt(np.mean(d2 ** 2))))
    waviness = float(np.mean(second)) if second else 0.0

    return {
        "file": path,
        "car_px": int(car.sum()),
        "ridge_px": int(ridge_mask.sum()),
        "peak": peak,
        "breaks": int(missing),
        "columns": int(x1 - x0 + 1),
        "break_share": round(missing / max(x1 - x0 + 1, 1), 4),
        "waviness": round(waviness, 3),
        "thickness_mean": round(float(np.mean(thickness)), 1) if thickness
        else 0.0,
        "thickness_p95": round(float(np.percentile(thickness, 95)), 1)
        if thickness else 0.0,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("paths", nargs="+")
    ap.add_argument("--json", default=None)
    ap.add_argument("--brightness", type=float, default=0.55)
    args = ap.parse_args()

    results = [r for r in (analyse(p, args.brightness) for p in args.paths)
               if r]
    header = (f"{'image':34s} {'peak':>6s} {'ridge px':>9s} {'breaks':>7s} "
              f"{'break%':>7s} {'waviness':>9s} {'thick p95':>10s}")
    print(header)
    print("-" * len(header))
    for r in results:
        name = os.path.relpath(r["file"]).replace("assets/rendered/", "")
        print(f"{name:34s} {r['peak']:6.0f} {r['ridge_px']:9d} "
              f"{r['breaks']:7d} {r['break_share']*100:7.1f} "
              f"{r['waviness']:9.3f} {r['thickness_p95']:10.1f}")
    if args.json:
        with open(args.json, "w") as fh:
            json.dump(results, fh, indent=2)
            fh.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
