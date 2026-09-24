#!/usr/bin/env python3
"""Contact sheet for the trunk assembly: 0 / 25 / 50 / 75 / 100 % open.

Diagnostic evidence only. The labels and markers live OUTSIDE the render, in a
left margin; nothing here is pasted into a production asset. The marker
positions come from `trunk_assembly.json`, which projects each tracked part
through the production camera, so a marker sitting on the lid is the part being
on the lid.

Usage:
    python3 tools/assets/build_trunk_ownership_sheet.py
"""

import json
import os
import sys

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
FRAMES = os.path.join(REPO, "assets", "rendered", "vehicle", "trunk")
ASSEMBLY = os.path.join(REPO, "assets", "checkpoints", "vehicle_state_assets",
                        "trunk_assembly.json")
OUT = os.path.join(REPO, "assets", "checkpoints", "vehicle_state_assets",
                   "trunk_ownership_sheet.png")

# Frame index per progress step, for a 14 frame sequence.
STEPS = [(0.0, "000"), (0.25, "003"), (0.5, "007"), (0.75, "010"), (1.0, "013")]
MARKERS = {
    "trunk_panel": (140, 200, 60),
    "inner_lamp_left": (90, 220, 255),
    "license_plate": (255, 210, 90),
    "brake_lamp": (255, 90, 90),
}
SCALE = 4
MARGIN = 260


def main():
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError as error:
        sys.exit(f"Pillow is required: {error}")
    if not os.path.isfile(ASSEMBLY):
        sys.exit("run tools/blender/verify_trunk_assembly.py first")

    report = json.load(open(ASSEMBLY))
    by_progress = {step["progress"]: step for step in report["steps"]}

    images = []
    for progress, frame in STEPS:
        image = Image.open(os.path.join(FRAMES, f"{frame}.png")).convert("RGBA")
        images.append((progress, frame, image))

    # Crop to the union of the tracked parts plus margin, so every step shows
    # the same region and the eye can compare them.
    boxes = []
    for step in report["steps"]:
        for part in step["parts"].values():
            boxes.append(part["bbox"])
    x0 = max(0, int(min(b[0] for b in boxes)) - 20)
    y0 = max(0, int(min(b[1] for b in boxes)) - 20)
    x1 = min(images[0][2].width, int(max(b[2] for b in boxes)) + 20)
    y1 = min(images[0][2].height, int(max(b[3] for b in boxes)) + 20)
    crop_w, crop_h = x1 - x0, y1 - y0

    cell_w, cell_h = crop_w * SCALE, crop_h * SCALE
    sheet = Image.new("RGB", (MARGIN + cell_w, cell_h * len(images)),
                      (12, 16, 20))
    draw = ImageDraw.Draw(sheet)
    try:
        font = ImageFont.truetype(
            "/System/Library/Fonts/Supplemental/Arial Bold.ttf", 26)
        small = ImageFont.truetype(
            "/System/Library/Fonts/Supplemental/Arial.ttf", 22)
    except OSError:  # pragma: no cover
        font = small = ImageFont.load_default()

    for index, (progress, frame, image) in enumerate(images):
        cell = image.crop((x0, y0, x1, y1)).resize((cell_w, cell_h),
                                                   Image.LANCZOS)
        top = index * cell_h
        sheet.paste(cell.convert("RGB"), (MARGIN, top))
        draw.text((14, top + 10), f"trunk {int(progress * 100)}%",
                  fill=(232, 238, 243), font=font)
        draw.text((14, top + 44), f"frame {frame}", fill=(150, 162, 172),
                  font=small)
        step = by_progress.get(progress)
        if not step:
            continue
        for order, (label, colour) in enumerate(MARKERS.items()):
            part = step["parts"].get(label)
            if not part:
                continue
            cx = MARGIN + int((part["centroid"][0] - x0) * SCALE)
            cy = top + int((part["centroid"][1] - y0) * SCALE)
            draw.ellipse([cx - 7, cy - 7, cx + 7, cy + 7], outline=colour,
                         width=3)
            draw.line([(MARGIN - 14, top + 86 + order * 30), (cx - 10, cy)],
                      fill=colour, width=2)
            draw.text((14, top + 80 + order * 30), label.replace("_", " "),
                      fill=colour, font=small)

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    sheet.save(OUT)
    print(f"[trunk-sheet] {sheet.size[0]}x{sheet.size[1]} -> "
          f"{os.path.relpath(OUT, REPO)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
