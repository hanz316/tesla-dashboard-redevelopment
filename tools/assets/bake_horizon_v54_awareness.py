#!/usr/bin/env python3
"""Bake the peripheral Side Awareness Zones and the secondary ghost cue.

The human review rejected the previous solution: a yellow car-shaped outline
floating on the road beside the Tesla read as a debug overlay. The replacement
uses the panel's own physical structure - the slanted trapezoid edges - as the
place where a driver's peripheral vision actually lives.

Each side gets a wedge between the slanted panel edge and a vertical internal
boundary. The field is strongest on the outer edge and falls to nothing at the
inner boundary with a nonlinear curve, so there is no shape to identify: no
triangle fill, no rectangle, no card, no circle. A thin brighter accent follows
the physical edge.

Three semantic colours are baked per side, because the scene selects between
them by state rather than tinting at run time:

    green  TURN ONLY            indicator on, that side clear
    amber  BLIND PRESENCE ONLY  someone there, no turn intent
    red    SIDE CONFLICT        turn intent + presence on the same side

The ghost vehicle is reduced to a soft, low-detail silhouette with no outline.

Usage:
    python3 tools/assets/bake_horizon_v54_awareness.py
"""

import argparse
import json
import os
import sys

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
UI = os.path.join(REPO, "assets", "ui")
REPORT = os.path.join(REPO, "assets", "checkpoints", "horizon_v54",
                      "awareness_assets.json")

CANVAS = (1920, 480)

# The panel's calibrated trapezoid: x = cut(y) on the left, mirrored on the
# right. These are the same numbers the mask and the QA use.
TOP_CUT = 116
BOTTOM_CUT = 51

# The vertical internal boundary, and the vertical extent of the zone.
INNER_LEFT = 224.0
INNER_RIGHT = 1920.0 - INNER_LEFT
TOP_Y = 40.0
BOTTOM_Y = 480.0

SEMANTIC = {
    "green": (58, 176, 118, "TURN ONLY - emerald"),
    "amber": (214, 158, 62, "BLIND PRESENCE ONLY - amber"),
    "red": (206, 74, 62, "SIDE CONFLICT - controlled warning red"),
}


def panel_cut(y):
    return TOP_CUT + (BOTTOM_CUT - TOP_CUT) * (float(y) / CANVAS[1])


def zone_field(side):
    """Alpha field for one side: outer edge strongest, nonlinear fade inward."""
    import numpy as np
    height, width = CANVAS[1], CANVAS[0]
    ys = np.mgrid[0:height, 0:width][0].astype(np.float32)
    xs = np.mgrid[0:height, 0:width][1].astype(np.float32)
    cut = TOP_CUT + (BOTTOM_CUT - TOP_CUT) * (ys / CANVAS[1])
    if side == "left":
        outer = np.clip(xs - cut, 0.0, None)
        span = np.clip(INNER_LEFT - cut, 1.0, None)
    else:
        outer = np.clip((width - cut) - xs, 0.0, None)
        span = np.clip((width - cut) - INNER_RIGHT, 1.0, None)
    inward = np.clip(outer / span, 0.0, 1.0)
    # Nonlinear falloff: near the edge the field holds, then it drops away
    # quickly so nothing inside the stage is ever covered.
    field = (1.0 - inward) ** 1.7
    vertical = np.clip((ys - TOP_Y) / 70.0, 0.0, 1.0) \
        * np.clip((BOTTOM_Y - ys) / 46.0, 0.0, 1.0)
    vertical = vertical * vertical * (3.0 - 2.0 * vertical)
    field = field * vertical
    # Only the peripheral strip exists at all.
    inside = ((xs >= cut) & (xs <= INNER_LEFT)) if side == "left" \
        else ((xs <= width - cut) & (xs >= INNER_RIGHT))
    field = np.where(inside, field, 0.0)
    # Edge accent: a thin brighter band following the physical panel edge.
    edge = np.exp(-((outer - 7.0) ** 2) / (2.0 * 7.5 ** 2))
    return field, edge


def main():
    import numpy as np
    from PIL import Image
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default=UI)
    parser.add_argument("--report", default=REPORT)
    args = parser.parse_args()
    height, width = CANVAS[1], CANVAS[0]
    report = {"schema": "horizon-v5.4-awareness-assets v1",
              "geometry": {"inner_left": INNER_LEFT, "inner_right": INNER_RIGHT,
                           "top_y": TOP_Y, "bottom_y": BOTTOM_Y,
                           "panel_cut": {"top": TOP_CUT, "bottom": BOTTOM_CUT}},
              "semantic": {name: {"rgb": value[0:3], "meaning": value[3]}
                           for name, value in SEMANTIC.items()},
              "assets": {}}
    # The two sides must mirror each other raster-exactly. Recomputing the
    # field for the right side is one pixel off: column i mirrors to width-1-i,
    # so a right-side formula measured back from `width - cut` lands one pixel
    # further out than the mirror of the left field.
    left_field, left_edge = zone_field("left")
    fields = {"left": (left_field, left_edge),
              "right": (np.fliplr(left_field), np.fliplr(left_edge))}
    for side in ("left", "right"):
        field, edge = fields[side]
        for name, (red, green, blue, meaning) in SEMANTIC.items():
            # The accent carries more of the colour than the body, which is what
            # makes the edge read as light rather than as a filled shape.
            body_alpha = field * 96.0
            accent_alpha = edge * field * 150.0
            alpha = np.clip(body_alpha + accent_alpha, 0, 210)
            colour_mix = np.clip((body_alpha * 0.75 + accent_alpha) /
                                 np.maximum(alpha, 1e-3), 0.0, 1.0)
            layer = np.zeros((height, width, 4), dtype=np.float32)
            layer[:, :, 0] = red * colour_mix
            layer[:, :, 1] = green * colour_mix
            layer[:, :, 2] = blue * colour_mix
            layer[:, :, 3] = alpha
            image = Image.fromarray(np.clip(layer, 0, 255).astype("uint8"),
                                    "RGBA")
            box = image.getchannel("A").getbbox() or (0, 0, 1, 1)
            box = (max(0, box[0] - 2), max(0, box[1] - 2),
                   min(width, box[2] + 2), min(height, box[3] + 2))
            cropped = image.crop(box)
            path = os.path.join(args.out, f"horizon_v54_zone_{side}_{name}.png")
            cropped.save(path)
            report["assets"][f"{side}_{name}"] = {
                "file": os.path.relpath(path, REPO), "box": list(box),
                "size": list(cropped.size), "meaning": meaning,
                "decoded_rgba_bytes": cropped.width * cropped.height * 4}
            if name == "amber":
                print(f"[v5.4] zone {side:5s} {cropped.size} at {box[:2]} "
                      f"peak alpha {int(np.asarray(cropped)[:, :, 3].max())}")

    # Ghost: a soft, low-detail adjacent silhouette, no outline anywhere.
    ghost = np.zeros((96, 168, 4), dtype=np.float32)
    yy, xx = np.mgrid[0:96, 0:168].astype(np.float32)
    body = (((xx - 84.0) / 78.0) ** 2 + ((yy - 58.0) / 26.0) ** 2) < 1.0
    cabin = (((xx - 78.0) / 46.0) ** 2 + ((yy - 40.0) / 20.0) ** 2) < 1.0
    shape = body | cabin
    # A soft silhouette: the alpha is feathered so no edge can be traced.
    from PIL import ImageFilter
    mask = Image.fromarray((shape * 255).astype("uint8")).filter(
        ImageFilter.GaussianBlur(6.0))
    ghost[:, :, 0] = 176
    ghost[:, :, 1] = 150
    ghost[:, :, 2] = 118
    ghost[:, :, 3] = np.asarray(mask).astype(np.float32) * 0.52
    ghost_image = Image.fromarray(np.clip(ghost, 0, 255).astype("uint8"),
                                  "RGBA")
    for side in ("left", "right"):
        image = ghost_image if side == "left" else ghost_image.transpose(
            Image.FLIP_LEFT_RIGHT)
        path = os.path.join(args.out, f"horizon_v54_ghost_{side}.png")
        image.save(path)
        report["assets"][f"ghost_{side}"] = {
            "file": os.path.relpath(path, REPO), "size": list(image.size),
            "why": "soft low-detail adjacent silhouette, no outline, amber-grey",
            "decoded_rgba_bytes": image.width * image.height * 4}
    print(f"[v5.4] ghost {ghost_image.size} (soft silhouette, no outline)")
    os.makedirs(os.path.dirname(args.report), exist_ok=True)
    with open(args.report, "w") as handle:
        json.dump(report, handle, indent=1)
        handle.write("\n")
    print(f"[v5.4] {os.path.relpath(args.report, REPO)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
