#!/usr/bin/env python3
"""V4 evidence: 14 states, two scales, contact sheets, V3 comparison, metrics.

Also writes the spec document from the same layout the scene is generated from,
so the document cannot describe a screen the scene does not draw.

Usage:
    python3 tools/preview/horizon_v4_shots.py
"""

import json
import os
import subprocess
import sys

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
PREVIEW = os.path.join(REPO, "tools", "preview", "scene_preview.py")
LAYOUT = os.path.join(REPO, "assets", "ui", "horizon_v4_layout.json")
SCENE = os.path.join(REPO, "scenes", "horizon_v4.scene")
OUT = os.path.join(REPO, "assets", "checkpoints", "horizon_v4")
V3B = os.path.join(REPO, "assets", "checkpoints", "horizon_v3", "b_concept_ev",
                   "neutral.png")
# The vehicle node, so the V3/V4 difference can exclude the bitmap that both
# candidates share.
VEHICLE_BOX = (703, 115, 1218, 401)


def main():
    from PIL import Image, ImageDraw, ImageFont
    layout = json.load(open(LAYOUT))
    states = layout["screenshot_states"]
    names = layout["screenshot_names"]
    os.makedirs(OUT, exist_ok=True)
    rendered = []
    for state, name in zip(states, names):
        subprocess.run([sys.executable, PREVIEW, "--scene", SCENE,
                        "--state", state, "--out", OUT,
                        "--out-name", name[:-4]], check=True, capture_output=True)
        path = os.path.join(OUT, name)
        if Image.open(path).size != (1920, 480):
            sys.exit(f"[v4] {name} is not 1920x480")
        rendered.append(path)
    try:
        font = ImageFont.truetype(
            "/System/Library/Fonts/Supplemental/Arial Bold.ttf", 22)
        big = ImageFont.truetype(
            "/System/Library/Fonts/Supplemental/Arial Bold.ttf", 28)
    except OSError:  # pragma: no cover
        font = big = ImageFont.load_default()

    def sheet(paths, labels, out_path, cell=(960, 240)):
        cell_w, cell_h, label_h = cell[0], cell[1], 26
        canvas = Image.new("RGB", (cell_w, (cell_h + label_h) * len(paths)),
                           (10, 14, 18))
        draw = ImageDraw.Draw(canvas)
        for index, (path, label) in enumerate(zip(paths, labels)):
            image = Image.open(path).convert("RGB").resize((cell_w, cell_h),
                                                           Image.LANCZOS)
            top = index * (cell_h + label_h)
            canvas.paste(image, (0, top + label_h))
            draw.text((10, top + 4), label, fill=(220, 228, 235), font=font)
        canvas.save(out_path)
        return out_path

    contact = sheet(rendered, [os.path.basename(p)[:-4] for p in rendered],
                    os.path.join(OUT, "horizon_v4_contact_sheet.png"))
    key_names = ["horizon_v4_01_neutral.png", "horizon_v4_02_left_indicator.png",
                 "horizon_v4_05_brake.png", "horizon_v4_08_door_fl.png",
                 "horizon_v4_13_navigation.png"]
    key_labels = ["neutral", "left indicator", "brake", "driver door open",
                  "navigation"]
    key = sheet([os.path.join(OUT, name) for name in key_names], key_labels,
                os.path.join(OUT, "horizon_v4_key_states.png"), cell=(1280, 320))

    # physical-size view: the same frames at half scale, to show what survives
    # when the panel is seen at its real size rather than magnified on a desk
    physical = Image.new("RGB", (960 * 2, 240 * len(key_names) + 26),
                         (10, 14, 18))
    draw = ImageDraw.Draw(physical)
    draw.text((10, 4), "physical-size view: half scale, native pixels",
              fill=(220, 228, 235), font=font)
    for index, name in enumerate(key_names):
        image = Image.open(os.path.join(OUT, name)).convert("RGB").resize(
            (960, 240), Image.LANCZOS)
        physical.paste(image, (0, 26 + index * 240))
    physical_path = os.path.join(OUT, "horizon_v4_physical_scale.png")
    physical.save(physical_path)

    # V3 B vs V4, same scale
    width, height = 1280, 320
    comparison = Image.new("RGB", (width, (height + 30) * 2), (10, 14, 18))
    draw = ImageDraw.Draw(comparison)
    for index, (label, source) in enumerate(
            (("V3 B neutral (rejected)", V3B),
             ("V4 SPATIAL GLASS neutral", os.path.join(
                 OUT, "horizon_v4_01_neutral.png")))):
        image = Image.open(source).convert("RGB").resize((width, height),
                                                         Image.LANCZOS)
        top = index * (height + 30)
        comparison.paste(image, (0, top + 30))
        draw.text((10, top + 4), label, fill=(232, 238, 243), font=big)
    comparison_path = os.path.join(OUT, "horizon_v3_vs_v4.png")
    comparison.save(comparison_path)

    # difference sanity: outside the shared vehicle bitmap
    import numpy as np
    a = np.asarray(Image.open(V3B).convert("RGB")).astype(np.int16)
    b = np.asarray(Image.open(os.path.join(OUT,
                                           "horizon_v4_01_neutral.png"))
                   .convert("RGB")).astype(np.int16)
    mask = np.ones(a.shape[:2], dtype=bool)
    x0, y0, x1, y1 = VEHICLE_BOX
    mask[y0:y1, x0:x1] = False
    diff = np.abs(a - b).max(axis=2)
    changed = int(((diff > 8) & mask).sum())
    total = int(mask.sum())
    metrics = {
        "vehicle_box_excluded": list(VEHICLE_BOX),
        "pixels_compared": total,
        "changed_pixels": changed,
        "changed_percent": round(100.0 * changed / total, 2),
        "mean_absolute_rgb_difference": round(
            float(np.abs(a - b).mean(axis=2)[mask].mean()), 2),
    }
    report = {
        "schema": "horizon-v4-evidence v1",
        "status": "HORIZON_V4_SPATIAL_GLASS = AWAITING HUMAN VISUAL APPROVAL",
        "states": {name: os.path.relpath(path, REPO)
                   for name, path in zip(names, rendered)},
        "contact_sheet": os.path.relpath(contact, REPO),
        "key_states": os.path.relpath(key, REPO),
        "physical_scale": os.path.relpath(physical_path, REPO),
        "v3_vs_v4": os.path.relpath(comparison_path, REPO),
        "v3_to_v4_difference": metrics,
    }
    with open(os.path.join(OUT, "horizon_v4_report.json"), "w") as fh:
        json.dump(report, fh, indent=1)
        fh.write("\n")
    print(f"[v4] {len(rendered)} states, contact {os.path.relpath(contact, REPO)}")
    print(f"[v4] key states {os.path.relpath(key, REPO)}")
    print(f"[v4] comparison {os.path.relpath(comparison_path, REPO)}")
    print(f"[v4] V3->V4 changed {metrics['changed_percent']}% of non-vehicle "
          f"pixels, mean abs diff {metrics['mean_absolute_rgb_difference']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
