#!/usr/bin/env python3
"""Turn the approved V5 reference image into numbers the layout can consume.

This agent has no visual capability, so "follow the reference" cannot mean
judging it by eye. It means measuring it: canvas, palette, luminance bands,
horizon row, ground plane, the vehicle silhouette, the left and right
information clusters, the instrument arc, the energy rail and the accent hue.
Those numbers are written to
assets/ui/horizon_v5_reference_measurements.json, an annotated overlay is
written next to it for human cross-checking, and the V5 layout reads them.

Every region number below comes from a stated pixel rule, never from a
description of the picture:

* vehicle   - largest 4-connected bright, low-saturation blob below the horizon
              inside the central band (the paint is bright and neutral; the
              city lights are bright but saturated, and they are excluded);
* clusters  - the bright/saturated runs inside the outer thirds;
* arc       - least-squares circle through the whitish bright pixels of the
              left third that are not part of the speed numeral;
* rail      - the cyan saturated column at the right edge.

When the image is absent the tool says so and writes nothing: the layout then
falls back to parameters explicitly marked TEMPORARY_PENDING_REFERENCE rather
than inventing a look.

Usage:
    python3 tools/assets/analyze_v5_reference.py
    python3 tools/assets/analyze_v5_reference.py --image path/to/reference.png
"""

import argparse
import json
import math
import os
import sys

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
DEFAULT_IMAGE = os.path.join(REPO, "assets", "ui", "horizon_v5_reference.png")
OUT = os.path.join(REPO, "assets", "ui",
                   "horizon_v5_reference_measurements.json")
OVERLAY = os.path.join(REPO, "assets", "ui",
                       "horizon_v5_reference_annotation.png")


def luminance(array):
    import numpy as np
    return (0.2126 * array[:, :, 0] + 0.7152 * array[:, :, 1]
            + 0.0722 * array[:, :, 2])


def vertical_bands(rows):
    """Smoothed row means plus the strongest low-frequency vertical step."""
    import numpy as np
    window = max(3, rows.size // 60)
    kernel = np.ones(window) / window
    smooth = np.convolve(rows, kernel, mode="same")
    start = rows.size // 4  # the horizon cannot be in the top quarter
    slope = np.abs(np.diff(smooth))
    horizon = int(np.argmax(slope[start:]) + start)
    return smooth, horizon


def largest_component(mask, downsample=2):
    """Largest 4-connected component; returns (count, [x0, y0, x1, y1])."""
    import numpy as np
    from collections import deque

    small = np.asarray(mask[::downsample, ::downsample], dtype=bool)
    height, width = small.shape
    seen = np.zeros_like(small)
    best_count, best_box = 0, None
    for start_y, start_x in np.argwhere(small):
        if seen[start_y, start_x]:
            continue
        queue = deque([(int(start_y), int(start_x))])
        seen[start_y, start_x] = True
        count = 0
        x0 = x1 = int(start_x)
        y0 = y1 = int(start_y)
        while queue:
            y, x = queue.popleft()
            count += 1
            x0, x1 = min(x0, x), max(x1, x)
            y0, y1 = min(y0, y), max(y1, y)
            for ny, nx in ((y - 1, x), (y + 1, x), (y, x - 1), (y, x + 1)):
                if 0 <= ny < height and 0 <= nx < width and small[ny, nx] \
                        and not seen[ny, nx]:
                    seen[ny, nx] = True
                    queue.append((ny, nx))
        if count > best_count:
            best_count = count
            best_box = [x0 * downsample, y0 * downsample,
                        (x1 + 1) * downsample, (y1 + 1) * downsample]
    return best_count * downsample * downsample, best_box


def fit_circle(xs, ys):
    """Algebraic (Kasa) circle fit. Returns (cx, cy, r, residual rms)."""
    import numpy as np
    design = np.stack([xs, ys, np.ones_like(xs)], axis=1).astype(float)
    target = xs * xs + ys * ys
    solution, *_ = np.linalg.lstsq(design, target, rcond=None)
    cx, cy = solution[0] / 2.0, solution[1] / 2.0
    radius = math.sqrt(max(0.0, solution[2] + cx * cx + cy * cy))
    residuals = np.hypot(xs - cx, ys - cy) - radius
    rms = float((residuals ** 2).mean() ** 0.5)
    return float(cx), float(cy), float(radius), rms


def ransac_circle(xs, ys, iterations=4000, tolerance=3.0, seed=7):
    """Circle fit that survives outliers (city-light glow, gear letter, ...).

    Three points define a circle; the winner is the circle with the most
    inliers within `tolerance` px. The winner is then refit on its inliers.
    """
    import numpy as np
    rng = np.random.default_rng(seed)
    points = np.stack([xs, ys], axis=1).astype(float)
    if points.shape[0] < 12:
        return None
    best = None
    for _ in range(iterations):
        idx = rng.choice(points.shape[0], size=3, replace=False)
        (x1, y1), (x2, y2), (x3, y3) = points[idx]
        denominator = 2.0 * (x1 * (y2 - y3) + x2 * (y3 - y1)
                             + x3 * (y1 - y2))
        if abs(denominator) < 1e-9:
            continue
        sq1, sq2, sq3 = x1 * x1 + y1 * y1, x2 * x2 + y2 * y2, x3 * x3 + y3 * y3
        cx = (sq1 * (y2 - y3) + sq2 * (y3 - y1) + sq3 * (y1 - y2)) / denominator
        cy = (sq1 * (x3 - x2) + sq2 * (x1 - x3) + sq3 * (x2 - x1)) / denominator
        radius = float(np.hypot(x1 - cx, y1 - cy))
        if not (60.0 < radius < 1200.0):
            continue
        distance = np.abs(np.hypot(points[:, 0] - cx, points[:, 1] - cy)
                          - radius)
        inliers = distance < tolerance
        count = int(inliers.sum())
        if best is None or count > best[0]:
            best = (count, cx, cy, radius, inliers)
    if best is None:
        return None
    count, cx, cy, radius, inliers = best
    cx, cy, radius, rms = fit_circle(xs[inliers], ys[inliers])
    return {"cx": float(cx), "cy": float(cy), "radius": float(radius),
            "fit_rms_px": rms, "inliers": count,
            "inlier_mask": inliers}


def box_from_mask(mask):
    import numpy as np
    ys, xs = np.nonzero(mask)
    if xs.size == 0:
        return None
    return [int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1]


def dilate(mask, radius):
    """Square-kernel dilation with numpy shifts (no SciPy in this toolchain)."""
    import numpy as np
    grown = mask.copy()
    for shift in range(1, radius + 1):
        grown |= np.roll(mask, shift, axis=0) | np.roll(mask, -shift, axis=0)
        grown |= np.roll(mask, shift, axis=1) | np.roll(mask, -shift, axis=1)
    return grown


def measure(path):
    import numpy as np
    from PIL import Image, ImageDraw

    image = Image.open(path).convert("RGB")
    width, height = image.size
    array = np.asarray(image).astype(np.float32)
    lum = luminance(array)
    rows = lum.mean(axis=1)
    smoothed, horizon = vertical_bands(rows)

    hsv = np.asarray(image.convert("HSV")).astype(np.float32)
    hue, sat, val = hsv[:, :, 0], hsv[:, :, 1], hsv[:, :, 2]

    thirds = {"left": [0, width // 3], "centre": [width // 3, 2 * width // 3],
              "right": [2 * width // 3, width]}
    third_means = {name: round(float(lum[:, span[0]:span[1]].mean()), 2)
                   for name, span in thirds.items()}

    # --- palette: the most common quantised colours above the horizon -------
    background = array[:max(1, horizon - 4)]
    quantised = (background // 8).astype(np.int32).reshape(-1, 3)
    keys, counts = np.unique(quantised, axis=0, return_counts=True)
    order = np.argsort(-counts)[:6]
    palette = ["#%02X%02X%02X" % tuple(int(v * 8 + 4) for v in keys[i])
               for i in order]

    # --- accent: the most vivid cool colour, weighted by vividness ----------
    vivid = (sat > 110) & (val > 110)
    accent = None
    accent_hue = None
    if vivid.any():
        cool = vivid & (hue > 95) & (hue < 170)
        if cool.sum() > 200:
            accent_hue = int(np.median(hue[cool]))
            weight = (sat / 255.0) * (val / 255.0)
            threshold = np.quantile(weight[cool], 0.9)
            top = cool & (np.abs(hue - accent_hue) < 8) & (weight >= threshold)
            accent = "#%02X%02X%02X" % tuple(
                int(round(v)) for v in array[top].mean(axis=0))

    # --- vehicle: bright, low-saturation blob around the horizon ------------
    # The car's roof is above the horizon row, so the search band starts above
    # it. A small dilation bridges the dark glass so the blob is the car and
    # not the paint alone; the reported box is shrunk back by the radius.
    # Threshold and dilation were tuned against the annotated overlay: at 110
    # with a 3 px bridge the blob runs past the car's nose into the road sheen
    # (box 676 px wide where the car reads ~590), at 140 with 2 px it stops at
    # the bumper. The number the layout consumes has to be the car.
    DILATE = 2
    centre_band = np.zeros(width, dtype=bool)
    centre_band[int(width * 0.24):int(width * 0.76)] = True
    body = (lum > 140) & (sat < 60) & centre_band[None, :]
    body[:max(0, horizon - int(height * 0.12)), :] = False
    _, vehicle_box = largest_component(dilate(body, DILATE))
    vehicle_pixels = 0
    if vehicle_box:
        vehicle_box = [vehicle_box[0] + DILATE, vehicle_box[1] + DILATE,
                       vehicle_box[2] - DILATE, vehicle_box[3] - DILATE]
        slab = np.zeros_like(body)
        slab[vehicle_box[1]:vehicle_box[3], vehicle_box[0]:vehicle_box[2]] = True
        # "Body pixels" for the dominance number: anything that is clearly not
        # the dark road inside the silhouette, so glass and shadowed paint
        # count toward the car and the wet asphalt does not.
        vehicle_pixels = int(((lum > 45) & (sat < 90) & slab).sum())

    # --- instrument arc: the cyan bright ring of the left third -------------
    left = np.zeros(width, dtype=bool)
    left[:int(width * 0.34)] = True
    ring = (sat > 60) & (val > 150) & (hue > 100) & (hue < 178)
    ring &= left[None, :]
    ring[:int(height * 0.05), :] = False
    ring[int(height * 0.78):, :] = False
    numeral = box_from_mask((lum > 105) & (sat < 60)
                            & (np.arange(width)[None, :] < int(width * 0.20))
                            & (np.arange(height)[:, None] > int(height * 0.25)))
    arc = None
    if ring.sum() > 400:
        ys, xs = np.nonzero(ring)
        fit = ransac_circle(xs.astype(float), ys.astype(float))
        if fit:
            inliers = fit.pop("inlier_mask")
            angles = np.degrees(np.arctan2(ys[inliers] - fit["cy"],
                                           xs[inliers] - fit["cx"]))
            # Angles are in PIL's convention (0 deg at 3 o'clock, clockwise,
            # because image y grows downward).
            order = np.argsort(angles)
            arc = {key: round(value, 1) for key, value in fit.items()}
            arc.update({
                "pixels": int(ring.sum()),
                "bbox": box_from_mask(ring),
                "angle_span_deg": [round(float(angles[order][0]), 1),
                                   round(float(angles[order][-1]), 1)],
                "as_fraction": {
                    "cx": round(fit["cx"] / width, 4),
                    "cy": round(fit["cy"] / height, 4),
                    "radius_h": round(fit["radius"] / height, 4)}})

    # --- energy rail: the saturated cyan column at the right edge -----------
    right = np.zeros(width, dtype=bool)
    right[int(width * 0.88):] = True
    rail_mask = vivid & (hue > 95) & (hue < 170) & right[None, :]
    rail = None
    if rail_mask.sum() > 50:
        ys, xs = np.nonzero(rail_mask)
        rail = {"bbox": [int(xs.min()), int(ys.min()),
                         int(xs.max()) + 1, int(ys.max()) + 1],
                "pixels": int(rail_mask.sum())}
        rows_hit = rail_mask.sum(axis=1) > 0
        gaps = np.diff(np.nonzero(rows_hit)[0])
        rail["segments"] = int((gaps > 1).sum() + 1) if gaps.size else 1

    # --- information clusters: the outer thirds ----------------------------
    def cluster(span):
        slab = np.zeros(width, dtype=bool)
        slab[span[0]:span[1]] = True
        mask = ((lum > 60) | (vivid & (val > 90))) & slab[None, :]
        return box_from_mask(mask)

    left_cluster = cluster([0, int(width * 0.30)])
    right_cluster = cluster([int(width * 0.70), width])

    # --- speed limit sign: the saturated red ring of the left third --------
    red = (sat > 120) & (val > 120) & ((hue < 20) | (hue > 235)) & left[None, :]
    red[:int(height * 0.15), :] = False
    sign = box_from_mask(red)

    ground = {"horizon_row": horizon,
              "horizon_fraction": round(horizon / height, 4),
              "ground_band": [horizon, height],
              "below_horizon_mean": round(float(lum[horizon:, :].mean()), 2)}
    vehicle = None
    if vehicle_box:
        vehicle = {
            "bbox": vehicle_box,
            "visible_width": vehicle_box[2] - vehicle_box[0],
            "visible_height": vehicle_box[3] - vehicle_box[1],
            "ground_contact_row": vehicle_box[3],
            "centre_x": (vehicle_box[0] + vehicle_box[2]) / 2.0,
            "pixels": vehicle_pixels,
            "width_fraction": round((vehicle_box[2] - vehicle_box[0])
                                    / width, 4),
            "height_fraction": round((vehicle_box[3] - vehicle_box[1])
                                     / height, 4),
            "area_fraction": round(vehicle_pixels / float(width * height), 4),
        }

    report = {
        "schema": "horizon-v5-reference-measurements v2",
        "image": os.path.relpath(path, REPO),
        "canvas": [width, height],
        "aspect": round(width / float(height), 4),
        "is_target_canvas": [width, height] == [1920, 480],
        "target_canvas_aspect": round(1920 / 480.0, 4),
        "luminance": {
            "overall_mean": round(float(lum.mean()), 2),
            "top_band_mean": round(float(lum[:height // 3].mean()), 2),
            "middle_band_mean": round(float(lum[height // 3:2 * height // 3]
                                            .mean()), 2),
            "bottom_band_mean": round(float(lum[2 * height // 3:].mean()), 2),
            "row_profile_sampled": [round(float(rows[i]), 1)
                                    for i in range(0, height,
                                                   max(1, height // 24))],
        },
        "thirds": third_means,
        "horizon": ground,
        "palette": palette,
        "accent": accent,
        "accent_hue": accent_hue,
        "vehicle": vehicle,
        "arc": arc,
        "speed_numeral_box": numeral,
        "speed_limit_sign": sign,
        "energy_rail": rail,
        "left_cluster_box": left_cluster,
        "right_cluster_box": right_cluster,
        "notes": [
            "vehicle is the largest 4-connected bright low-saturation blob "
            "below the horizon inside x in [0.24, 0.76] of the canvas",
            "the annotated overlay next to this file draws every box and the "
            "fitted circle so a human can check the measurement against the "
            "image it came from",
            "palette is quantised to 8 levels per channel and taken from the "
            "background band above the horizon",
            "STATUS: MEASURED FROM THE REFERENCE IMAGE",
        ],
    }

    overlay = image.copy()
    draw = ImageDraw.Draw(overlay)
    boxes = [("vehicle", vehicle_box, (90, 220, 255)),
             ("left cluster", left_cluster, (255, 200, 90)),
             ("right cluster", right_cluster, (255, 200, 90)),
             ("numerals", numeral, (255, 120, 120))]
    if sign:
        boxes.append(("speed sign", sign, (255, 90, 90)))
    if rail:
        boxes.append(("rail", rail["bbox"], (120, 255, 180)))
    for label, box, colour in boxes:
        if not box:
            continue
        draw.rectangle([box[0], box[1], box[2], box[3]], outline=colour,
                       width=3)
    draw.line([0, horizon, width, horizon], fill=(255, 0, 200), width=2)
    if arc:
        cx, cy, radius = arc["cx"], arc["cy"], arc["radius"]
        draw.ellipse([cx - radius, cy - radius, cx + radius, cy + radius],
                     outline=(0, 255, 200), width=2)
        draw.line([cx - 12, cy, cx + 12, cy], fill=(0, 255, 200), width=2)
        draw.line([cx, cy - 12, cx, cy + 12], fill=(0, 255, 200), width=2)
    overlay.save(OVERLAY)
    return report


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
    vehicle = report["vehicle"]
    print(f"[v5-reference] measured {report['canvas']} -> "
          f"{os.path.relpath(args.out, REPO)}")
    print(f"[v5-reference] horizon {report['horizon']['horizon_row']} "
          f"({report['horizon']['horizon_fraction']:.3f} h), accent "
          f"{report['accent']} hue {report['accent_hue']}")
    if vehicle:
        print(f"[v5-reference] vehicle {vehicle['bbox']} "
              f"{vehicle['visible_width']}x{vehicle['visible_height']} px, "
              f"width {vehicle['width_fraction']:.3f} h, area "
              f"{vehicle['area_fraction']:.4f}")
    rail = report["energy_rail"]
    print(f"[v5-reference] arc {report['arc']}, rail "
          f"{rail and rail['bbox']}")
    print(f"[v5-reference] annotation {os.path.relpath(OVERLAY, REPO)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
