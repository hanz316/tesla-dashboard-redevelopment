#!/usr/bin/env python3
"""V5.2 evidence: old against new, phase against phase, at panel scale.

The review asks for the comparisons that make the change reviewable without
taking anyone's word for it:

    A  OLD DAY vs NEW DAY          (the V5.1 plate out of git, beside the new one)
    B  OLD NIGHT vs NEW NIGHT      (proof the accepted night look survived)
    C  DAWN / DAY / DUSK / NIGHT   (same state, same camera)
    D  physical scale              (half size, as the panel shows it)
    E  reflection response         (the wet-road answer per phase)

Old plates are read from git, not from a copy, so the comparison cannot drift.

Usage:
    python3 tools/preview/horizon_v52_evidence.py --old-ref aeeb770
"""

import argparse
import json
import os
import subprocess
import sys

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
PREVIEW = os.path.join(REPO, "tools", "preview", "scene_preview.py")
SCENE = os.path.join(REPO, "scenes", "horizon_v5.scene")
UI = os.path.join(REPO, "assets", "ui")
OUT = os.path.join(REPO, "assets", "checkpoints", "horizon_v5")
PHASES = ("dawn", "day", "dusk", "night")


def plate(phase):
    return os.path.join(UI, "horizon_v5_background.png" if phase == "night"
                        else f"horizon_v5_background_{phase}.png")


def old_plate(ref, phase, destination):
    relative = "assets/ui/horizon_v5_background.png" if phase == "night" \
        else f"assets/ui/horizon_v5_background_{phase}.png"
    result = subprocess.run(["git", "show", f"{ref}:{relative}"], cwd=REPO,
                            capture_output=True)
    if result.returncode != 0:
        return None
    with open(destination, "wb") as handle:
        handle.write(result.stdout)
    return destination


def main():
    from PIL import Image, ImageDraw, ImageFont
    parser = argparse.ArgumentParser()
    parser.add_argument("--old-ref", default="aeeb770")
    args = parser.parse_args()
    os.makedirs(OUT, exist_ok=True)
    try:
        font = ImageFont.truetype(
            "/System/Library/Fonts/Supplemental/Arial Bold.ttf", 18)
        small = ImageFont.truetype(
            "/System/Library/Fonts/Supplemental/Arial.ttf", 16)
    except OSError:  # pragma: no cover
        font = small = ImageFont.load_default()

    def stack(rows, path, width=960, height=240, header=26):
        sheet = Image.new("RGB", (width, (height + header) * len(rows)),
                          (8, 10, 14))
        draw = ImageDraw.Draw(sheet)
        for index, (label, source) in enumerate(rows):
            top = index * (height + header)
            if isinstance(source, str) and os.path.isfile(source):
                image = Image.open(source).convert("RGB")
                sheet.paste(image.resize((width, height), Image.LANCZOS),
                            (0, top + header))
            draw.text((8, top + 4), label, fill=(226, 232, 240), font=small)
        sheet.save(path)
        return path

    produced = {}
    for phase in ("day", "night"):
        old = old_plate(args.old_ref, phase,
                        os.path.join(OUT, f"horizon_v52_old_{phase}.png"))
        rows = [(f"OLD {phase.upper()} (V5.1, {args.old_ref})", old),
                (f"NEW {phase.upper()} (V5.2)", plate(phase))]
        produced[f"old_vs_new_{phase}"] = os.path.relpath(
            stack(rows, os.path.join(OUT,
                                     f"horizon_v52_old_vs_new_{phase}.png")),
            REPO)

    produced["phases"] = os.path.relpath(stack(
        [(f"{phase.upper()} - neutral, same camera and vehicle", plate(phase))
         for phase in PHASES],
        os.path.join(OUT, "horizon_v52_phases.png")), REPO)

    # Physical scale: half size, which is how the panel presents it.
    half = Image.new("RGB", (960, 240 * len(PHASES) + 30), (8, 10, 14))
    draw = ImageDraw.Draw(half)
    draw.text((8, 6), "physical half size, as seen on the panel",
              fill=(226, 232, 240), font=small)
    for index, phase in enumerate(PHASES):
        image = Image.open(plate(phase)).convert("RGB").resize(
            (960, 240), Image.LANCZOS)
        half.paste(image, (0, 30 + index * 240))
    physical_path = os.path.join(OUT, "horizon_v52_physical_scale.png")
    half.save(physical_path)
    produced["physical_scale"] = os.path.relpath(physical_path, REPO)

    # Reflection response per phase: the road region under the car, 1:1.
    crops = []
    for phase in PHASES:
        neutral = os.path.join(OUT, f"horizon_v5_1_{phase}.png")
        if os.path.isfile(neutral):
            crops.append((f"{phase.upper()} wet-road response",
                          Image.open(neutral).convert("RGB").crop(
                              (640, 240, 1280, 480))))
    if crops:
        sheet = Image.new("RGB", (640, 240 * len(crops) + 26 * len(crops)),
                          (8, 10, 14))
        draw = ImageDraw.Draw(sheet)
        for index, (label, image) in enumerate(crops):
            top = index * 266
            sheet.paste(image, (0, top + 26))
            draw.text((8, top + 4), label, fill=(226, 232, 240), font=small)
        reflection_path = os.path.join(OUT,
                                       "horizon_v52_reflection_phases.png")
        sheet.save(reflection_path)
        produced["reflection_phases"] = os.path.relpath(reflection_path, REPO)

    metrics = os.path.join(OUT, "horizon_v52_metrics.json")
    document = {
        "schema": "horizon-v5.2-metrics v1",
        "old_reference": args.old_ref,
        "evidence": produced,
        "material_metrics": json.load(open(os.path.join(
            OUT, "horizon_v52_material_metrics.json"))),
        "motion_gate": json.load(open(os.path.join(
            OUT, "horizon_v52_motion_gate.json"))),
    }
    with open(metrics, "w") as handle:
        json.dump(document, handle, indent=1)
        handle.write("\n")
    for key, path in produced.items():
        print(f"[v5.2] {key:22s} {path}")
    print(f"[v5.2] metrics {os.path.relpath(metrics, REPO)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
