#!/usr/bin/env python3
"""Reflection spatial-frequency analysis for HDRI selection.

The previous round partly ranked environments by the standard deviation of the
car luminance. That is a bad metric on its own: a striped roof has a very high
standard deviation and looks terrible. What separates a premium environment
from a strip-light tunnel is the SPATIAL FREQUENCY of the reflection, so this
tool splits it in two:

    low frequency  = large, smooth tonal regions (dark / mid / bright silver
                     sweeping across the panel)
    high frequency = the residual after a Gaussian low-pass: stripes, lamp
                     arrays, repeated ceiling lights

It also counts prominent light/dark alternations across the roof, which is the
most direct numeric stand-in for "how many stripes can I see".

No single number here decides anything. The tool prints a ranking for triage.

Usage:
    python3 tools/assets/analyze_reflection_frequency.py render.png [...]
"""

import argparse
import json
import os
import sys

try:
    from PIL import Image, ImageFilter
except ImportError:  # pragma: no cover
    sys.exit("Pillow required")

import numpy as np

LOWPASS_FRACTION = 0.025   # gaussian radius as a fraction of car width
STRIPE_PROMINENCE = 10.0   # 0-255 minimum visible alternation
STRIPE_MIN_GAP = 5         # px between counted stripes


def car_bbox(img):
    bbox = img.getchannel("A").getbbox()
    return bbox or (0, 0, img.width, img.height)


def luminance(img):
    arr = np.asarray(img.convert("RGBA")).astype(np.float32)
    return arr[..., :3].mean(axis=2), arr[..., 3] > 0


def count_stripes(profile, prominence=STRIPE_PROMINENCE, min_gap=STRIPE_MIN_GAP):
    """Count prominent light/dark alternations along a 1-D luminance profile."""
    n = len(profile)
    if n < 3:
        return 0
    extrema = []
    for i in range(1, n - 1):
        if profile[i] >= profile[i - 1] and profile[i] > profile[i + 1]:
            extrema.append((i, float(profile[i]), "max"))
        elif profile[i] <= profile[i - 1] and profile[i] < profile[i + 1]:
            extrema.append((i, float(profile[i]), "min"))
    counted = []
    for idx, value, kind in extrema:
        if counted and kind == counted[-1][2]:
            prev = counted[-1]
            if abs(value - prev[1]) < prominence:
                continue
            if (kind == "max" and value > prev[1]) or (kind == "min"
                                                       and value < prev[1]):
                counted[-1] = (idx, value, kind)
            continue
        if counted and idx - counted[-1][0] < min_gap:
            continue
        counted.append((idx, value, kind))
    stripes = 0
    for i in range(len(counted) - 1):
        if abs(counted[i][1] - counted[i + 1][1]) >= prominence:
            stripes += 1
    return stripes


def gaussian_blur(plane, radius):
    """Separable gaussian blur on a float array.

    Pillow's GaussianBlur refuses mode 'F', and quantising to 8 bit first would
    put its own rounding error straight into the high-frequency residual we are
    trying to measure.
    """
    sigma = max(radius / 2.0, 0.5)
    half = max(1, int(round(sigma * 3)))
    offsets = np.arange(-half, half + 1, dtype=np.float32)
    kernel = np.exp(-(offsets ** 2) / (2.0 * sigma * sigma))
    kernel /= kernel.sum()

    padded = np.pad(plane, ((half, half), (half, half)), mode="edge")
    tmp = np.zeros_like(padded)
    for i, w in enumerate(kernel):
        tmp += w * np.roll(padded, i - half, axis=1)
    out = np.zeros_like(tmp)
    for i, w in enumerate(kernel):
        out += w * np.roll(tmp, i - half, axis=0)
    return out[half:half + plane.shape[0], half:half + plane.shape[1]]


def band_metrics(lum, mask, box, radius):
    x0, y0, x1, y1 = box
    region = lum[y0:y1, x0:x1].copy()
    region_mask = mask[y0:y1, x0:x1]
    if region_mask.sum() < 50:
        return None
    fill = float(region[region_mask].mean())
    region[~region_mask] = fill
    low = gaussian_blur(region.astype(np.float32), radius)
    residual = region - low
    hf = residual[region_mask]
    lf = low[region_mask]
    # Count stripes per ROW and take the median. Averaging the band into a
    # single 1-D profile first smooths the stripes away, which is exactly what
    # this metric is supposed to detect.
    per_row = [count_stripes(low[r]) for r in range(low.shape[0])]
    per_row = [v for v in per_row if v > 0] or [0]
    return {
        "mean": float(region[region_mask].mean()),
        "lf_std": float(lf.std()),
        "hf_std": float(hf.std()),
        "hf_energy": float(np.abs(hf).mean()),
        "hf_ratio": float(hf.std() / max(lf.std(), 1e-6)),
        "stripes": int(np.median(per_row)),
        "stripes_max": int(np.max(per_row)),
    }


def analyse(path):
    img = Image.open(path).convert("RGBA")
    lum, mask = luminance(img)
    x0, y0, x1, y1 = car_bbox(img)
    car_w, car_h = x1 - x0, y1 - y0
    radius = max(2.0, car_w * LOWPASS_FRACTION)
    roof = (int(x0 + car_w * 0.28), int(y0 + car_h * 0.02),
            int(x0 + car_w * 0.72), int(y0 + car_h * 0.22))
    side = (int(x0 + car_w * 0.05), int(y0 + car_h * 0.34),
            int(x0 + car_w * 0.95), int(y0 + car_h * 0.66))
    visible = lum[mask]
    return {
        "file": path,
        "car_px": [car_w, car_h],
        "radius": round(radius, 1),
        "mean": float(visible.mean()),
        "std": float(visible.std()),
        "p05": float(np.percentile(visible, 5)),
        "p95": float(np.percentile(visible, 95)),
        "max": float(visible.max()),
        "clipped_px": int((visible >= 250).sum()),
        "roof": band_metrics(lum, mask, roof, radius),
        "side": band_metrics(lum, mask, side, radius),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("paths", nargs="+")
    ap.add_argument("--json", default=None)
    args = ap.parse_args()
    results = [r for r in (analyse(p) for p in args.paths) if r["roof"]]
    header = (f"{'candidate':34s} {'mean':>5s} {'std':>5s} {'roofLF':>7s} "
              f"{'roofHF':>7s} {'HF/LF':>6s} {'stripes':>7s} {'strMax':>6s} "
              f"{'sideHF':>7s} {'clip':>5s}")
    print(header)
    print("-" * len(header))
    for r in sorted(results, key=lambda r: -r["roof"]["hf_std"]):
        name = os.path.basename(r["file"]).replace("_only_600.png", "")
        print(f"{name:34s} {r['mean']:5.0f} {r['std']:5.0f} "
              f"{r['roof']['lf_std']:7.1f} {r['roof']['hf_std']:7.1f} "
              f"{r['roof']['hf_ratio']:6.3f} {r['roof']['stripes']:7d} "
              f"{r['roof']['stripes_max']:6d} "
              f"{r['side']['hf_std']:7.1f} {r['clipped_px']:5d}")
    print()
    print("sorted by roof high-frequency energy (lower = smoother roof).")
    print("This ranks for triage. It does not decide, and it is not a visual")
    print("judgement.")
    if args.json:
        with open(args.json, "w") as fh:
            json.dump(results, fh, indent=2)
            fh.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
