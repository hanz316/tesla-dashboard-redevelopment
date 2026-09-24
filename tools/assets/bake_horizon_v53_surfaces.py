#!/usr/bin/env python3
"""Three information-surface candidates, baked once for the DAY readability pass.

The human review rejected the daylight backplates (two black holes) and asked
for exactly three controlled candidates before any of them is chosen:

    A  soft optical scrim      - luminance control in the ink's neighbourhood
    B  subtle frosted glass    - low-opacity glass with baked diffusion
    C  smoked optical glass    - a darker automotive smoked surface

All three share the same rules: no rectangle, no circle, no oval, no visible
boundary, strongest where the information is, feathering rapidly to nothing,
and almost invisible at physical half size. The edges are therefore built as a
long smooth falloff rather than a shape.

Candidate B and C need a *diffused* environment rather than a blurred one at
run time. That is pre-baked here: the phase plate is blurred once, cropped to
the cluster box and stored as a small RGBA asset, so the device only composites.

Usage:
    python3 tools/assets/bake_horizon_v53_surfaces.py
"""

import argparse
import json
import math
import os
import sys

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
UI = os.path.join(REPO, "assets", "ui")
OUT = os.path.join(REPO, "assets", "checkpoints", "horizon_v5",
                   "horizon_v53_surfaces.json")
PHASES = ("dawn", "day", "dusk", "night")

# The two information boxes: the speed cluster and the energy module. They are
# the regions the support surface is allowed to touch.
BOXES = {
    "speed": (250, 96, 600, 372),
    "energy": (1300, 100, 1700, 392),
}


def falloff(distance, radius, hardness):
    """A long, smooth falloff: 1 at the centre, 0 at the radius, with no edge a
    viewer can point at. `hardness` controls how far the plateau reaches."""
    if distance >= radius:
        return 0.0
    t = distance / radius
    if t <= hardness:
        return 1.0
    u = (t - hardness) / (1.0 - hardness)
    return 0.5 + 0.5 * math.cos(math.pi * min(1.0, max(0.0, u)))


def surface_mask(size, boxes, centres, radii, hardness):
    """One alpha field for the two clusters, built from overlapping smooth
    falloffs. No shape is ever drawn, so no boundary exists to be seen."""
    import numpy as np
    height, width = size[1], size[0]
    yy, xx = np.mgrid[0:height, 0:width].astype(np.float32)
    field = np.zeros((height, width), dtype=np.float32)
    for key, (cx, cy) in centres.items():
        rx, ry = radii[key]
        distance = np.sqrt(((xx - cx) / rx) ** 2 + ((yy - cy) / ry) ** 2)
        value = np.zeros_like(field)
        inside = distance < 1.0
        t = distance[inside]
        plateau = t <= hardness
        value[inside] = np.where(
            plateau, 1.0,
            0.5 + 0.5 * np.cos(np.pi * np.clip(
                (t - hardness) / (1.0 - hardness), 0.0, 1.0)))
        field = np.maximum(field, value)
    # No box clipping: a hard rectangle would be exactly the visible boundary
    # the review forbids, and the falloff already reaches zero well inside the
    # canvas. The boxes only describe where the surface is strongest for the
    # report.
    return field


def mask_boxes(height, width, boxes):
    import numpy as np
    mask = np.zeros((height, width), dtype=np.float32)
    for (x0, y0, x1, y1) in boxes.values():
        mask[max(0, y0):y1, max(0, x0):x1] = 1.0
    return mask


def main():
    import numpy as np
    from PIL import Image, ImageFilter
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default=UI)
    parser.add_argument("--report", default=OUT)
    args = parser.parse_args()
    canvas = (1920, 480)
    centres = {"speed": (409.0, 224.0), "energy": (1500.0, 240.0)}
    radii = {"speed": (215.0, 190.0), "energy": (235.0, 195.0)}

    report = {"schema": "horizon-v5.3-surfaces v1",
              "why": "three controlled candidates, same rules, chosen on "
                     "measured dominance rather than on contrast alone",
              "boxes": BOXES, "candidates": {}}

    # A: soft optical scrim. Luminance control only, no colour, no sheen.
    alpha = surface_mask(canvas, BOXES, centres, radii, 0.30)
    scrim = np.zeros((canvas[1], canvas[0], 4), dtype=np.float32)
    scrim[:, :, 0:3] = np.array([8, 12, 18], dtype=np.float32)
    scrim[:, :, 3] = alpha * 152.0
    _save(scrim, args.out, "horizon_v53_surface_scrim.png", report, "scrim",
          "low-opacity luminance control, colourless, no sheen")

    # B/C: glass needs a *diffused* environment, pre-baked per phase.
    diffusion = {}
    for phase in PHASES:
        plate = os.path.join(UI, "horizon_v5_background.png" if phase == "night"
                             else f"horizon_v5_background_{phase}.png")
        if not os.path.isfile(plate):
            continue
        image = Image.open(plate).convert("RGB").filter(
            ImageFilter.GaussianBlur(18.0))
        path = os.path.join(args.out, f"horizon_v53_diffusion_{phase}.png")
        image.save(path)
        diffusion[phase] = os.path.relpath(path, REPO)
        report["candidates"].setdefault("diffusion", {})[phase] = \
            diffusion[phase]

    yy = np.mgrid[0:canvas[1], 0:canvas[0]][0].astype(np.float32)
    # A smooth cosine over the whole height: the previous version clipped at the
    # top, which put a one-pixel step into the sheen's own alpha.
    gradient = 0.5 + 0.5 * np.cos(np.pi * np.clip(yy / 480.0, 0.0, 1.0))
    for name, label, body, peak, hardness, sheen, mix in (
            ("frost", "subtle frosted glass", (232, 240, 246), 104, 0.30, 9,
             0.62),
            ("smoked", "smoked optical glass", (10, 14, 20), 132, 0.42, 27,
             0.78)):
        field = surface_mask(canvas, BOXES, centres, radii, hardness)
        per_phase = {}
        for phase in PHASES:
            plate = os.path.join(UI, "horizon_v5_background.png"
                                 if phase == "night"
                                 else f"horizon_v5_background_{phase}.png")
            if not os.path.isfile(plate):
                continue
            # The glass body is the *diffused* environment, pre-baked once: the
            # device never blurs anything.
            diffused = np.asarray(Image.open(plate).convert("RGB").filter(
                ImageFilter.GaussianBlur(18.0))).astype(np.float32)
            layer = np.zeros((canvas[1], canvas[0], 4), dtype=np.float32)
            layer[:, :, 0:3] = (diffused * mix
                                + np.array(body, dtype=np.float32) * (1.0 - mix))
            layer[:, :, 0:3] += gradient[:, :, None] * sheen
            layer[:, :, 3] = field * peak
            path = _save(layer, args.out,
                         f"horizon_v53_{name}_{phase}.png", report,
                         f"{name}_{phase}", f"{label} ({phase})")
            per_phase[phase] = {"file": os.path.relpath(path, REPO),
                                "box": report["candidates"][f"{name}_{phase}"]["box"]}
        report["candidates"].setdefault("per_phase", {})[name] = per_phase

    with open(args.report, "w") as handle:
        json.dump(report, handle, indent=1)
        handle.write("\n")
    for key, value in report["candidates"].items():
        if key in ("diffusion", "per_phase") or not isinstance(value, dict):
            continue
        if "peak_alpha" not in value:
            continue
        print(f"[v5.3] {key:14s} {value['label']:24s} peak alpha "
              f"{value['peak_alpha']:5.1f}  {value['file']}")
    for name, entries in report["candidates"].get("per_phase", {}).items():
        print(f"[v5.3] {name:14s} {len(entries)} phase assets")
    print(f"[v5.3] diffusion assets: {len(diffusion)} phases")
    print(f"[v5.3] {os.path.relpath(args.report, REPO)}")
    return 0


def _save(array, out, filename, report, key, label):
    import numpy as np
    from PIL import Image
    image = Image.fromarray(np.clip(array, 0, 255).astype("uint8"), "RGBA")
    box = image.getchannel("A").getbbox() or (0, 0, 1, 1)
    box = (max(0, box[0] - 2), max(0, box[1] - 2),
           min(image.width, box[2] + 2), min(image.height, box[3] + 2))
    cropped = image.crop(box)
    path = os.path.join(out, filename)
    cropped.save(path)
    report["candidates"][key] = {
        "file": os.path.relpath(path, REPO), "label": label,
        "box": list(box), "size": list(cropped.size),
        "peak_alpha": round(float(np.asarray(cropped)[:, :, 3].max()), 1),
        "decoded_rgba_bytes": cropped.width * cropped.height * 4}
    return path


if __name__ == "__main__":
    sys.exit(main())
