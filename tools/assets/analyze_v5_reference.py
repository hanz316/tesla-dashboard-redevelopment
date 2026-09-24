#!/usr/bin/env python3
"""Turn the approved V5 reference image into numbers the layout can consume.

This agent has no visual capability, so "follow the reference" cannot mean
judging it by eye. It means measuring it: where the horizon sits, how bright the
three thirds are, where the vehicle is and how wide it reads, what the
background palette is, which hue is the accent, and where a navigation element
appears. Those numbers are written to
assets/ui/horizon_v5_reference_measurements.json and the V5 layout reads them.

When the image is absent the tool says so and writes nothing: the layout then
falls back to parameters explicitly marked TEMPORARY_PENDING_REFERENCE rather
than inventing a look.

Usage:
    python3 tools/assets/analyze_v5_reference.py
    python3 tools/assets/analyze_v5_reference.py --image path/to/reference.png
"""

import argparse
import json
import os
import sys

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
DEFAULT_IMAGE = os.path.join(REPO, "assets", "ui", "horizon_v5_reference.png")
OUT = os.path.join(REPO, "assets", "ui",
                   "horizon_v5_reference_measurements.json")


def vertical_bands(luminance):
    """Mean luminance per row, smoothed, plus the strongest low-frequency step."""
    import numpy as np
    rows = luminance.mean(axis=1)
    window = max(3, rows.size // 60)
    kernel = np.ones(window) / window
    smooth = np.convolve(rows, kernel, mode="same")
    # search below the top quarter: the horizon cannot be at the very top
    start = rows.size // 4
    slope = np.abs(np.diff(smooth))
    horizon = int(np.argmax(slope[start:]) + start)
    return rows, smooth, horizon


def measure(path):
    import numpy as np
    from PIL import Image

    image = Image.open(path).convert("RGB")
    width, height = image.size
    array = np.asarray(image).astype(np.float32)
    luminance = array.mean(axis=2)
    rows, smoothed, horizon = vertical_bands(luminance)

    thirds = {
        "left": [0, width // 3],
        "centre": [width // 3, 2 * width // 3],
        "right": [2 * width // 3, width],
    }
    third_means = {name: round(float(luminance[:, span[0]:span[1]].mean()), 2)
                   for name, span in thirds.items()}

    # palette: the most common quantised colours in the background band
    background = array[:max(1, horizon - 4)]
    quantised = (background // 8).astype(np.int32)
    flat = quantised.reshape(-1, 3)
    keys, counts = np.unique(flat, axis=0, return_counts=True)
    order = np.argsort(-counts)[:6]
    palette = ["#%02X%02X%02X" % tuple(int(value * 8 + 4) for value in keys[i])
               for i in order]

    # accent: most saturated colour that is not amber/red
    hsv = np.asarray(image.convert("HSV")).astype(np.float32)
    saturation = hsv[:, :, 1]
    value = hsv[:, :, 2]
    hue = hsv[:, :, 0]
    vivid = (saturation > 90) & (value > 90)
    accent = None
    if vivid.any():
        hues = hue[vivid]
        # 0-255 hue: cyan/ice-blue sits around 120-150
        cool = hues[(hues > 100) & (hues < 170)]
        if cool.size:
            accent_hue = int(np.median(cool))
            mask = np.abs(hue - accent_hue) < 6
            if mask.any():
                accent = "#%02X%02X%02X" % tuple(
                    int(value) for value in array[mask].mean(axis=0))

    # vehicle: the band below the horizon minus a column-wise background model
    body = array[horizon:, :, :]
    if body.size:
        column_median = np.median(body, axis=0)
        residual = np.abs(body - column_median).mean(axis=2)
        mask = residual > 18
        columns = mask.sum(axis=0)
        rows_hit = mask.sum(axis=1)
        if columns.max() > 2:
            xs = np.nonzero(columns > max(2, columns.max() * 0.15))[0]
            ys = np.nonzero(rows_hit > max(2, rows_hit.max() * 0.15))[0]
            vehicle_box = [int(xs.min()), int(horizon + ys.min()),
                           int(xs.max()), int(horizon + ys.max())]
        else:
            vehicle_box = None
    else:
        vehicle_box = None

    ground = {
        "horizon_row": horizon,
        "ground_band": [horizon, height],
        "below_horizon_mean": round(float(luminance[horizon:, :].mean()), 2)
        if horizon < height else None,
    }
    return {
        "schema": "horizon-v5-reference-measurements v1",
        "image": os.path.relpath(path, REPO),
        "canvas": [width, height],
        "is_target_canvas": [width, height] == [1920, 480],
        "luminance": {
            "overall_mean": round(float(luminance.mean()), 2),
            "top_band_mean": round(float(luminance[:height // 3].mean()), 2),
            "middle_band_mean": round(float(luminance[height // 3:2 * height // 3].mean()), 2),
            "bottom_band_mean": round(float(luminance[2 * height // 3:].mean()), 2),
            "row_profile_sampled": [round(float(rows[i]), 1)
                                    for i in range(0, height, max(1, height // 24))],
        },
        "thirds": third_means,
        "horizon": ground,
        "palette": palette,
        "accent": accent,
        "vehicle_box": vehicle_box,
        "vehicle_visible_width": (vehicle_box[2] - vehicle_box[0])
        if vehicle_box else None,
        "notes": [
            "vehicle_box is an estimate from the residual against a column-wise "
            "background model; it is a starting point for the composition test, "
            "not a precise alpha bound",
            "palette is quantised to 8 levels per channel and taken from the "
            "background band above the horizon",
            "STATUS: MEASURED FROM THE REFERENCE IMAGE",
        ],
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--image", default=DEFAULT_IMAGE)
    parser.add_argument("--out", default=OUT)
    args = parser.parse_args()
    if not os.path.isfile(args.image):
        print(f"[v5-reference] MISSING: {os.path.relpath(args.image, REPO)}")
        print("[v5-reference] nothing was written. The V5 layout keeps its "
              "reference-derived parameters marked TEMPORARY_PENDING_REFERENCE "
              "and the report says BACKGROUND_ART_REQUIRED.")
        return 2
    try:
        import numpy  # noqa: F401
        from PIL import Image  # noqa: F401
    except ImportError as error:
        sys.exit(f"Pillow and numpy are required: {error}")
    report = measure(args.image)
    with open(args.out, "w") as fh:
        json.dump(report, fh, indent=1)
        fh.write("\n")
    print(f"[v5-reference] measured {report['canvas']} -> "
          f"{os.path.relpath(args.out, REPO)}")
    print(f"[v5-reference] horizon {report['horizon']['horizon_row']}, "
          f"vehicle {report['vehicle_box']}, accent {report['accent']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
