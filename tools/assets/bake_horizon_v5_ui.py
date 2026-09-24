#!/usr/bin/env python3
"""Bake the two bitmap pieces the V5 clusters need.

The V5 review forbids runtime blur and asks for baked glow, a baked rail
background and a baked arc with depth. This tool writes those bitmaps once:

    assets/ui/horizon_v5_arc_glow.png     soft ring glow under the speed arc
    assets/ui/horizon_v5_rail_track.png   energy rail track + segment gaps
    assets/ui/horizon_v5_numeral_glow.png soft glow behind the speed numeral

They are drawn from the measured dial geometry
(assets/ui/horizon_v5_reference_measurements.json -> arc), mapped into the
panel with the same content-box transform the layout uses, so the glow and the
rail cannot drift away from the vector geometry drawn on top of them.

Usage:
    python3 tools/assets/bake_horizon_v5_ui.py
"""

import argparse
import json
import math
import os
import sys

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
UI = os.path.join(REPO, "assets", "ui")
MEASUREMENTS = os.path.join(UI, "horizon_v5_reference_measurements.json")
ALIGNMENT = os.path.join(UI, "horizon_v5_speed_alignment.json")

# The mapping the layout uses: 2172x724 mapped 1:1 by height into a centred
# 1440x480 content box.
CONTENT_SCALE = 480 / 724.0
CONTENT_CENTRE_X = 1086.0
PANEL_CENTRE_X = 960.0

# Semantics, not decoration: the dial runs 0..240 km/h over 225 degrees,
# starting at the lower left (PIL angles: 0 deg at 3 o'clock, clockwise).
ARC_START_DEG = 135.0
ARC_END_DEG = 360.0


def panel_x(x_ref):
    return PANEL_CENTRE_X + (x_ref - CONTENT_CENTRE_X) * CONTENT_SCALE


def panel_y(y_ref):
    return y_ref * CONTENT_SCALE


def panel_size(value):
    return value * CONTENT_SCALE


def dial_geometry(measurements):
    arc = measurements["arc"]
    dial_dx = 0.0
    if os.path.isfile(ALIGNMENT):
        try:
            dial_dx = float(json.load(open(ALIGNMENT)).get("dial_dx", 0.0))
        except (OSError, ValueError):
            dial_dx = 0.0
    return {
        "cx": panel_x(arc["cx"]) + dial_dx,
        "cy": panel_y(arc["cy"]),
        "radius": panel_size(arc["radius"]),
        "width": max(3.0, panel_size(arc["radius"] * 0.045)),
        "ref_cx": arc["cx"], "ref_cy": arc["cy"], "ref_radius": arc["radius"],
        "dial_dx": dial_dx,
    }


def glow_ring(size, centre, radius, inner_width, outer_width, colour,
               inner_alpha, outer_alpha):
    from PIL import Image, ImageDraw
    glow = Image.new("RGBA", size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(glow, "RGBA")
    steps = 48
    for step in range(steps, 0, -1):
        t = step / float(steps)
        width = inner_width + (outer_width - inner_width) * t
        alpha = int(round(inner_alpha + (outer_alpha - inner_alpha) * (1 - t)))
        r = radius
        draw.arc([centre[0] - r, centre[1] - r, centre[0] + r, centre[1] + r],
                 start=ARC_START_DEG, end=ARC_END_DEG,
                 fill=(*colour, alpha), width=int(round(width)))
    return glow


def numeral_glow(size, centre, radius, colour, alpha):
    """A soft pool of light behind the speed numeral - baked, never blurred at
    run time. Concentric ellipses from the outside in."""
    from PIL import Image, ImageDraw
    glow = Image.new("RGBA", size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(glow, "RGBA")
    steps = 64
    for step in range(steps):
        t = step / float(steps - 1)
        r = radius * (1.0 - 0.55 * t)
        a = int(round(alpha * (t ** 2.2)))
        box = [centre[0] - r * 0.95, centre[1] - r * 0.62,
               centre[0] + r * 0.95, centre[1] + r * 0.62]
        draw.ellipse(box, fill=(*colour, a))
    return glow


def rail_track(size, box, segments, colours):
    from PIL import Image, ImageDraw
    track = Image.new("RGBA", size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(track, "RGBA")
    x0, y0, x1, y1 = box
    radius = (x1 - x0) / 2.0
    draw.rounded_rectangle([x0, y0, x1, y1], radius=radius,
                           fill=(*colours["track_fill"], colours["track_alpha"]),
                           outline=(*colours["track_edge"],
                                    colours["edge_alpha"]), width=2)
    span = (y1 - y0) - 8
    step = span / float(segments)
    for index in range(1, segments):
        y = y0 + 4 + step * index
        draw.line([x0 + 3, y, x1 - 3, y],
                  fill=(*colours["gap"], colours["gap_alpha"]), width=2)
    return track


def main():
    from PIL import Image
    parser = argparse.ArgumentParser()
    parser.add_argument("--measurements", default=MEASUREMENTS)
    parser.add_argument("--out", default=UI)
    parser.add_argument("--size", default="1920x480")
    args = parser.parse_args()
    width, height = (int(v) for v in args.size.lower().split("x"))
    measurements = json.load(open(args.measurements))
    dial = dial_geometry(measurements)

    boxes = {}

    def save(image, name, margin=2):
        box = image.getchannel("A").getbbox() or (0, 0, 1, 1)
        box = (max(0, box[0] - margin), max(0, box[1] - margin),
               min(width, box[2] + margin), min(height, box[3] + margin))
        image.crop(box).save(os.path.join(args.out, name))
        boxes[name] = list(box)
        return box

    ring = glow_ring((width, height), (dial["cx"], dial["cy"]),
                     dial["radius"], dial["width"],
                     dial["width"] * 4.2, (88, 200, 216), 14, 0)
    save(ring, "horizon_v5_arc_glow.png")

    numeral = numeral_glow((width, height),
                           (dial["cx"] - dial["radius"] * 0.55,
                            dial["cy"] - dial["radius"] * 0.05),
                           dial["radius"] * 1.05, (120, 205, 225), 16)
    save(numeral, "horizon_v5_numeral_glow.png")

    rail = json.load(open(args.measurements))["energy_rail"]["bbox"]
    rail_box = (panel_x(rail[0]), panel_y(rail[1]),
                panel_x(rail[2]), panel_y(rail[3]))
    # The measured rail box contains its glow; the track itself is the narrow
    # bar in the middle of it.
    track_x0 = rail_box[0] + (rail_box[2] - rail_box[0]) * 0.55
    track_x1 = rail_box[2] - (rail_box[2] - rail_box[0]) * 0.12
    track = rail_track((width, height), (track_x0, rail_box[1] + 6,
                                         track_x1, rail_box[3] - 6), 24,
                       {"track_fill": (8, 18, 28), "track_alpha": 170,
                        "track_edge": (46, 96, 122), "edge_alpha": 190,
                        "gap": (6, 12, 18), "gap_alpha": 220})
    save(track, "horizon_v5_rail_track.png")
    # The lit segments live inside the baked track: their box is derived from
    # the same numbers, so the ink and the track cannot drift apart.
    segments_box = [track_x0 + 4, rail_box[1] + 11,
                    track_x1 - 4, rail_box[3] - 11]

    report = {
        "schema": "horizon-v5-ui-assets v1",
        "dial": dial,
        "arc_degrees": [ARC_START_DEG, ARC_END_DEG],
        "content_scale": CONTENT_SCALE,
        "assets": {
            "arc_glow": "assets/ui/horizon_v5_arc_glow.png",
            "numeral_glow": "assets/ui/horizon_v5_numeral_glow.png",
            "rail_track": "assets/ui/horizon_v5_rail_track.png",
        },
        "asset_boxes": boxes,
        "rail_track_box": [round(v, 1) for v in
                           (track_x0, rail_box[1] + 6, track_x1, rail_box[3] - 6)],
        "rail_segments_box": [round(v, 1) for v in segments_box],
    }
    path = os.path.join(args.out, "horizon_v5_ui_assets.json")
    with open(path, "w") as handle:
        json.dump(report, handle, indent=1)
        handle.write("\n")
    print(f"[v5-ui] dial centre ({dial['cx']:.1f},{dial['cy']:.1f}) "
          f"radius {dial['radius']:.1f} stroke {dial['width']:.1f}")
    print(f"[v5-ui] rail track {report['rail_track_box']}")
    print(f"[v5-ui] {os.path.relpath(path, REPO)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
