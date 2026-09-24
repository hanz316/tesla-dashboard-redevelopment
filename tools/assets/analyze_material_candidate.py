#!/usr/bin/env python3
"""Measure the material candidate: are the classes actually different?

The author cannot see the render, so the honest evidence is distributions. For
each material class (paint, glass, tire, rim, trim) this reports the luminance
mean, p10, p50, p90 and the spread, before and after the candidate revision,
plus the separation between classes - the property that decides whether the car
reads as a toy (one flat response everywhere) or as an object with distinct
materials.

These numbers are proxies, not approval. They cannot say "this looks premium";
they can only say "these two materials no longer share one response".

Usage:
    python3 tools/assets/analyze_material_candidate.py
"""

import json
import os
import subprocess
import sys

AFTER_OVERRIDE = None
REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
DIR = os.path.join(REPO, "assets", "checkpoints", "model_a_material")
# The mask pass goes through Blender's view transform, so an emission of pure
# red arrives as something like (219, 57, 33). Classes are identified by which
# channels dominate, not by an exact colour.
MASK_CHANNELS = {"paint": ("r",), "glass": ("g",), "tire": ("b",),
                 "rim": ("r", "g"), "trim": ("r", "b")}


def class_masks(mask_rgba):
    """Split the mask render into one boolean mask per material class."""
    import numpy as np
    rgb = mask_rgba[:, :, :3].astype(float)
    alpha = mask_rgba[:, :, 3]
    peak = rgb.max(axis=2)
    lit = (alpha > 128) & (peak > 20)
    # 0.75 rather than 0.5: the view transform lifts the other channels
    # (pure green arrives as 110/197/81), so a 0.5 threshold would make
    # every mask look like it contains every channel.
    strong = rgb > (peak[:, :, None] * 0.75)
    index = {"r": 0, "g": 1, "b": 2}
    out = {}
    for name, channels in MASK_CHANNELS.items():
        wanted = np.ones_like(lit)
        for channel in ("r", "g", "b"):
            if channel in channels:
                wanted &= strong[:, :, index[channel]]
            else:
                wanted &= ~strong[:, :, index[channel]]
        out[name] = lit & wanted
    return out
SCENE = os.path.join(REPO, "scenes", "horizon_v2.scene")
PREVIEW = os.path.join(REPO, "tools", "preview", "scene_preview.py")


def stats(values):
    import numpy as np
    return {
        "mean": round(float(values.mean()), 2),
        "p10": round(float(np.percentile(values, 10)), 2),
        "p50": round(float(np.percentile(values, 50)), 2),
        "p90": round(float(np.percentile(values, 90)), 2),
        "spread": round(float(np.percentile(values, 90) -
                              np.percentile(values, 10)), 2),
        "pixels": int(values.size),
    }


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--after", default="material_after.png",
                        help="which candidate render to compare against the "
                             "production one (material_after.png, "
                             "material_after_variantB.png, ...)")
    parser.add_argument("--tag", default="", help="suffix for the outputs")
    extra = parser.parse_args()
    global AFTER_OVERRIDE
    AFTER_OVERRIDE = extra.after
    try:
        import numpy as np
        from PIL import Image, ImageDraw, ImageFont
    except ImportError as error:
        sys.exit(f"Pillow and numpy are required: {error}")

    mask_rgba = np.asarray(Image.open(os.path.join(DIR, "material_classes.png"))
                           .convert("RGBA"))
    masks = class_masks(mask_rgba)
    before = np.asarray(Image.open(os.path.join(DIR, "material_before.png"))
                        .convert("RGB")).astype(float)
    after = np.asarray(Image.open(os.path.join(DIR, AFTER_OVERRIDE))
                       .convert("RGB")).astype(float)
    luminance_before = before.mean(axis=2)
    luminance_after = after.mean(axis=2)

    report = {"schema": "model-a-material-metrics v1",
              "status": "MODEL_A_MATERIAL_REVISION = AWAITING HUMAN VISUAL APPROVAL",
              "why": "proxy metrics only; the decision is human visual review",
              "classes": {}, "separation": {}}
    medians_before, medians_after = {}, {}
    for name in MASK_CHANNELS:
        mask = masks[name]
        if mask.sum() < 50:
            report["classes"][name] = {"error": "class not found in the mask"}
            continue
        entry = {"pixels": int(mask.sum()),
                 "before": stats(luminance_before[mask]),
                 "after": stats(luminance_after[mask])}
        report["classes"][name] = entry
        medians_before[name] = entry["before"]["p50"]
        medians_after[name] = entry["after"]["p50"]

    names = [name for name in MASK_CHANNELS if name in medians_before]
    for first in names:
        for second in names:
            if first >= second:
                continue
            key = f"{first}-{second}"
            report["separation"][key] = {
                "median_gap_before": round(abs(medians_before[first] -
                                               medians_before[second]), 2),
                "median_gap_after": round(abs(medians_after[first] -
                                              medians_after[second]), 2)}

    # Paint highlight structure: the whole point of the revision.
    paint = masks["paint"]
    if paint.sum() > 50:
        report["paint_highlight_structure"] = {
            "before_spread": report["classes"]["paint"]["before"]["spread"],
            "after_spread": report["classes"]["paint"]["after"]["spread"],
            "note": "p90-p10 over the painted surface: broad transitions "
                    "across roof, hood and shoulders show up here",
        }

    # Side-by-side comparison sheet at 3x.
    scale = 3
    width, height = before.shape[1] * scale, before.shape[0] * scale
    sheet = Image.new("RGB", (width * 2 + 24, height + 46), (12, 16, 20))
    draw = ImageDraw.Draw(sheet)
    try:
        font = ImageFont.truetype(
            "/System/Library/Fonts/Supplemental/Arial Bold.ttf", 30)
    except OSError:  # pragma: no cover
        font = ImageFont.load_default()
    for index, (label, image) in enumerate(
            (("BEFORE - production master", before),
             ("AFTER - material candidate", after))):
        cell = Image.fromarray(image.astype("uint8")).resize(
            (width, height), Image.LANCZOS)
        sheet.paste(cell, (index * (width + 24), 46))
        draw.text((index * (width + 24) + 8, 10), label,
                  fill=(232, 238, 243), font=font)
    sheet_path = os.path.join(DIR, f"material_before_after{extra.tag}.png")
    sheet.save(sheet_path)
    report["comparison_sheet"] = os.path.relpath(sheet_path, REPO)

    # And the same two cars inside the real Horizon frame at 1920x480.
    horizon = {}
    for label, source in (("before", "material_before.png"),
                          ("after", AFTER_OVERRIDE)):
        name = f"horizon_material_{label}{extra.tag}"
        subprocess.run([sys.executable, PREVIEW, "--scene", SCENE,
                        "--state", "h2_neutral",
                        "--vehicle-image", os.path.join(DIR, source),
                        "--out", DIR, "--out-name", name],
                       check=True, capture_output=True)
        horizon[label] = os.path.relpath(os.path.join(DIR, name + ".png"), REPO)
    report["horizon_native"] = horizon

    report["after_render"] = AFTER_OVERRIDE
    with open(os.path.join(DIR, f"material_metrics{extra.tag}.json"), "w") as fh:
        json.dump(report, fh, indent=1)
        fh.write("\n")

    for name, entry in report["classes"].items():
        if "error" in entry:
            print(f"[material] {name:6s} {entry['error']}")
            continue
        print(f"[material] {name:6s} px {entry['pixels']:6d}  "
              f"before mean {entry['before']['mean']:6.1f} spread "
              f"{entry['before']['spread']:6.1f}  ->  after mean "
              f"{entry['after']['mean']:6.1f} spread {entry['after']['spread']:6.1f}")
    print(f"[material] sheet {report['comparison_sheet']}")
    print(f"[material] horizon native {horizon}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
