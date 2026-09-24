#!/usr/bin/env python3
"""Optical centring for the V5 speed cluster, measured on rendered ink.

"The number is centred in the arc" is a claim about pixels, not about layout
boxes, so it is measured the way the eye sees it: the renderer's own font, the
real ink bounding box of the numeral, and the centroid of that ink. The tool
prints the offsets and, with --solve, writes the correction the layout builder
applies to the reference-derived boxes.

The vertical axis is deliberately *not* forced to zero: `km/h` and the PRND row
sit under the numeral, so a numeral centred exactly on the arc centre reads low.
The optical compensation is stated in the output rather than hidden.

Usage:
    python3 tools/preview/v5_speed_alignment.py
    python3 tools/preview/v5_speed_alignment.py --solve
"""

import argparse
import json
import os
import sys

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
SCENE = os.path.join(REPO, "scenes", "horizon_v5.scene")
TOKENS = os.path.join(REPO, "assets", "ui", "horizon_v5_tokens.json")
UI = os.path.join(REPO, "assets", "ui")
OUT = os.path.join(UI, "horizon_v5_speed_alignment.json")
EVIDENCE = os.path.join(REPO, "assets", "checkpoints", "horizon_v5",
                        "horizon_v5_speed_alignment.png")

# The numeral is centred on the arc's horizontal centre; the vertical axis
# carries a deliberate optical offset because `km/h` and the gear row sit below
# it. -6 px keeps the *visual* centroid (ink centroid, not the bbox centre)
# inside 3 px of the arc centre without pushing the numeral into `km/h`.
TARGET_TOLERANCE_PX = 3.0
VERTICAL_OPTICAL_OFFSET_PX = -6.0


def measure():
    from PIL import Image, ImageDraw
    import scene_preview as previewer

    scene = json.load(open(SCENE))
    tokens = json.load(open(TOKENS))
    dial = tokens["ui_assets"]["dial"]
    nodes = {node["id"]: node for node in scene["nodes"]}
    scratch = Image.new("RGB", (scene["canvas"]["width"],
                                scene["canvas"]["height"]))
    draw = ImageDraw.Draw(scratch)

    def ink(node_id, text):
        node = nodes[node_id]
        font = previewer.load_font(node.get("font", 32), node.get("bold", False),
                                   node.get("font_role"))
        anchor = {"center": "mm", "left": "lm", "right": "rm"}.get(
            node.get("align", "center"), "mm")
        return draw.textbbox((node.get("x", 0), node.get("y", 0)), text,
                             font=font, anchor=anchor)

    def centroid(node_id, text):
        import numpy as np
        node = nodes[node_id]
        font = previewer.load_font(node.get("font", 32), node.get("bold", False),
                                   node.get("font_role"))
        anchor = {"center": "mm", "left": "lm", "right": "rm"}.get(
            node.get("align", "center"), "mm")
        canvas = Image.new("L", (scene["canvas"]["width"],
                                 scene["canvas"]["height"]))
        ImageDraw.Draw(canvas).text((node.get("x", 0), node.get("y", 0)), text,
                                    font=font, anchor=anchor, fill=255)
        box = ink(node_id, text)
        array = np.asarray(canvas)[max(0, int(box[1])):int(box[3]) + 1,
                                   max(0, int(box[0])):int(box[2]) + 1] > 96
        ys, xs = np.nonzero(array)
        if xs.size == 0:
            return None
        return (max(0, int(box[0])) + xs.mean(), max(0, int(box[1])) + ys.mean())

    speed_box = ink("speed.value", "88")
    speed_centroid = centroid("speed.value", "88")
    report = {
        "schema": "horizon-v5-speed-alignment v1",
        "arc_center": [dial["cx"], dial["cy"]],
        "arc_radius": dial["radius"],
        "speed_ink_bbox": list(speed_box),
        "speed_ink_center": [(speed_box[0] + speed_box[2]) / 2.0,
                             (speed_box[1] + speed_box[3]) / 2.0],
        "speed_visual_centroid": list(speed_centroid) if speed_centroid else None,
        "unit_ink_bbox": list(ink("speed.unit", "km/h")),
        "gear_ink_bbox": list(ink("gear.d", "D")),
        "ready_ink_bbox": list(ink("driver.status", "READY")),
        "chill_ink_bbox": list(ink("climate.status", "CHILL")),
        "limit_ink_bbox": list(ink("speedlimit.value", "120")),
        "tolerance_px": TARGET_TOLERANCE_PX,
        "vertical_optical_offset_px": VERTICAL_OPTICAL_OFFSET_PX,
    }
    centre_x = (speed_box[0] + speed_box[2]) / 2.0
    centroid_x = speed_centroid[0] if speed_centroid else centre_x
    report["dx_ink_center"] = round(centroid_x - dial["cx"], 2)
    report["dx_ink_bbox_center"] = round(centre_x - dial["cx"], 2)
    centre_y = (speed_box[1] + speed_box[3]) / 2.0
    centroid_y = speed_centroid[1] if speed_centroid else centre_y
    report["dy_visual_centroid"] = round(centroid_y - dial["cy"]
                                         - VERTICAL_OPTICAL_OFFSET_PX, 2)
    report["within_tolerance"] = bool(
        abs(report["dx_ink_center"]) <= TARGET_TOLERANCE_PX)
    return scene, report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--solve", action="store_true",
                        help="write the correction the layout builder applies")
    parser.add_argument("--json", default=None, help="write the report here")
    parser.add_argument("--evidence", default=None,
                        help="write the annotated PNG here")
    args = parser.parse_args()
    try:
        import numpy  # noqa: F401
        from PIL import Image  # noqa: F401
    except ImportError as error:
        sys.exit(f"Pillow and numpy are required: {error}")
    scene, report = measure()
    print(f"[v5-speed] arc centre ({report['arc_center'][0]:.1f},"
          f"{report['arc_center'][1]:.1f}) r={report['arc_radius']:.1f}")
    print(f"[v5-speed] numeral ink bbox {report['speed_ink_bbox']} "
          f"centroid "
          f"{[round(v, 1) for v in report['speed_visual_centroid']]}")
    print(f"[v5-speed] dx (ink centroid - arc centre) "
          f"{report['dx_ink_center']:+.2f} px, tolerance "
          f"{report['tolerance_px']} px -> "
          f"{'OK' if report['within_tolerance'] else 'OUT OF TOLERANCE'}")
    print(f"[v5-speed] dy after the declared optical offset "
          f"{report['dy_visual_centroid']:+.2f} px")
    if args.json:
        with open(args.json, "w") as handle:
            json.dump(report, handle, indent=1)
            handle.write("\n")
    if args.evidence:
        draw_evidence(scene, report, args.evidence)
    if args.solve:
        # The numeral's ink centre and the arc centre must coincide. Both can
        # move, so the correction is split: the numeral steps left, the dial
        # steps right, by half the measured gap each. The reference's own
        # numeral sits 27.6 reference px right of its ring centre, so splitting
        # keeps both elements within ~9 px of where the reference has them while
        # making them concentric.
        current = {"dial_dx": 0.0, "text_dx": 0.0}
        if os.path.isfile(OUT):
            try:
                with open(OUT) as handle:
                    previous = json.load(handle)
                current["dial_dx"] = float(previous.get("dial_dx", 0.0))
                current["text_dx"] = float(previous.get("text_dx", 0.0))
            except (OSError, ValueError):
                pass
        gap = report["dx_ink_center"]
        correction = {
            "schema": "horizon-v5-speed-alignment v1",
            "why": "the numeral's rendered ink centre and the dial centre must "
                   "coincide within 3 px. The correction is split between the "
                   "dial (moves right) and the numeral (moves left) so neither "
                   "element drifts far from the reference's own positions.",
            "dial_dx": round(current["dial_dx"] + gap / 2.0, 2),
            "text_dx": round(current["text_dx"] - gap / 2.0, 2),
            "dy": 0.0,
            "vertical_optical_offset_px": VERTICAL_OPTICAL_OFFSET_PX,
            "measured_before": report,
        }
        with open(OUT, "w") as handle:
            json.dump(correction, handle, indent=1)
            handle.write("\n")
        print(f"[v5-speed] correction dial_dx {correction['dial_dx']:+.2f} "
              f"text_dx {correction['text_dx']:+.2f} -> "
              f"{os.path.relpath(OUT, REPO)}")
    return 0


def draw_evidence(scene, report, path):
    from PIL import Image, ImageDraw, ImageFont
    base = Image.open(os.path.join(REPO, "assets", "checkpoints", "horizon_v5",
                                   "horizon_v5_neutral.png")).convert("RGB")
    scaled = 2
    base = base.resize((base.width * scaled, base.height * scaled),
                       Image.LANCZOS)
    draw = ImageDraw.Draw(base)
    cx, cy = report["arc_center"]
    radius = report["arc_radius"]

    def box(rect, colour):
        return [rect[0] * scaled, rect[1] * scaled, rect[2] * scaled,
                rect[3] * scaled]

    draw.ellipse(box([cx - radius, cy - radius, cx + radius, cy + radius],
                     None), outline=(255, 0, 200), width=2)
    draw.line([cx * scaled - 26, cy * scaled, cx * scaled + 26, cy * scaled],
              fill=(255, 0, 200), width=2)
    draw.line([cx * scaled, cy * scaled - 26, cx * scaled, cy * scaled + 26],
              fill=(255, 0, 200), width=2)
    draw.rectangle(box(report["speed_ink_bbox"], None), outline=(90, 220, 255),
                   width=2)
    centroid = report["speed_visual_centroid"]
    draw.line([centroid[0] * scaled - 12, centroid[1] * scaled,
               centroid[0] * scaled + 12, centroid[1] * scaled],
              fill=(120, 255, 120), width=3)
    draw.line([centroid[0] * scaled, centroid[1] * scaled - 12,
               centroid[0] * scaled, centroid[1] * scaled + 12],
              fill=(120, 255, 120), width=3)
    for key, colour in (("unit_ink_bbox", (255, 200, 90)),
                        ("gear_ink_bbox", (255, 200, 90)),
                        ("ready_ink_bbox", (180, 255, 180)),
                        ("chill_ink_bbox", (180, 255, 180)),
                        ("limit_ink_bbox", (255, 120, 120))):
        draw.rectangle(box(report[key], None), outline=colour, width=2)
    try:
        font = ImageFont.truetype(
            "/System/Library/Fonts/Supplemental/Arial.ttf", 22)
    except OSError:  # pragma: no cover
        font = ImageFont.load_default()
    crop = base.crop((int(240 * scaled), 0, int(720 * scaled), 480 * scaled))
    label = ImageDraw.Draw(crop)
    label.rectangle([0, 0, 470, 30], fill=(0, 0, 0))
    label.text((6, 5), f"dx {report['dx_ink_center']:+.2f} px (tol "
                       f"{report['tolerance_px']:.0f})  dy "
                       f"{report['dy_visual_centroid']:+.2f} px",
               fill=(240, 240, 240), font=font)
    crop.save(path)
    print(f"[v5-speed] evidence {os.path.relpath(path, REPO)}")


if __name__ == "__main__":
    sys.exit(main())
