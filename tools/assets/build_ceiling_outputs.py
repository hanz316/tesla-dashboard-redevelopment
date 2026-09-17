#!/usr/bin/env python3
"""Build every review artefact for the MODEL A quality ceiling test."""

import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from build_photoreal_comparison import resize_rgba  # noqa: E402

try:
    from PIL import Image
except ImportError:  # pragma: no cover
    sys.exit("Pillow required")

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
C = os.path.join(REPO_ROOT, "assets", "rendered", "ceiling")
D = os.path.join(REPO_ROOT, "assets", "rendered", "diagnostic")
M = os.path.join(REPO_ROOT, "assets", "rendered", "material_study")
OUT = os.path.join(REPO_ROOT, "assets", "checkpoints",
                   "model_a_ceiling_2026-09-16")
DASH = os.path.join(REPO_ROOT, "tools", "assets", "make_comparison_sheet.py")
SCENE = os.path.join(REPO_ROOT, "scenes", "horizon_redesign_a.scene")


def car_width(path):
    img = Image.open(path)
    bbox = img.getchannel("A").getbbox()
    return (bbox[2] - bbox[0]) if bbox else img.width


def to_600(src, dst):
    img = Image.open(src).convert("RGBA")
    scale = 600.0 / car_width(src)
    resize_rgba(img, (max(1, int(img.width * scale)),
                      max(1, int(img.height * scale)))).save(dst)
    return dst


def horizon(src, key, out_dir, box="700x401@610,40"):
    name = f"horizon_{key}"
    subprocess.run(
        ["python3", os.path.join(REPO_ROOT, "tools", "preview",
                                 "scene_preview.py"),
         "--scene", SCENE, "--state", "normal_drive",
         "--vehicle-image", src, "--vehicle-crop", "--vehicle-box", box,
         "--out-name", name, "--out", out_dir],
        check=True, capture_output=True)
    full = os.path.join(out_dir, name + ".png")
    crop = os.path.join(out_dir, f"{key}_horizon1to1.png")
    Image.open(full).convert("RGB").crop((510, 0, 1410, 480)).save(crop)
    return full, crop


def sheet(name, entries, cols, cell="460x318"):
    cmd = ["python3", DASH, "--out", os.path.join(OUT, name),
           "--cols", str(cols), "--cell", cell]
    for label, path in entries:
        cmd += ["--image", f"{label}={path}"]
    r = subprocess.run(cmd, capture_output=True, text=True)
    print(r.stdout.strip() or r.stderr.strip())


def main():
    os.makedirs(OUT, exist_ok=True)

    # 1. panel-by-panel normal policy: 3 treatments x 4 views
    entries = []
    for treatment in ("original", "clean", "weighted"):
        for view in ("side", "rear_quarter", "roof", "doors"):
            entries.append((f"{treatment.upper()} {view.upper()}",
                            os.path.join(D, f"panel_{treatment}", f"{view}.png")))
    sheet("panel_normal_policy.png", entries, 4, "460x310")

    # 2. local remesh experiment
    sheet("local_remesh_test.png", [
        ("CURRENT (original topology)", os.path.join(C, "doors_current.png")),
        ("NORMAL FIX", os.path.join(C, "doors_cleaned.png")),
        ("LOCAL REMESH 4mm", os.path.join(C, "remesh_door_lf_0.004.png")),
        ("LOCAL REMESH 2.5mm", os.path.join(C, "remesh_door_lf_0.0025.png")),
    ], 4, "460x318")

    # 3. reference paint
    sheet("paint_reference_comparison.png", [
        ("CURRENT PAINT (v4 structure)", os.path.join(M, "paint_a.png")),
        ("REFERENCE PAINT (2 BSDFs + flake under coat)",
         os.path.join(C, "reference_paint.png")),
    ], 2, "620x430")

    # 4. reference glass
    sheet("glass_reference_comparison.png", [
        ("CURRENT GLASS", os.path.join(M, "glass_material.png")),
        ("REFERENCE GLASS (dielectric + coating layer)",
         os.path.join(C, "glass_reference.png")),
    ], 2, "620x430")

    # 5. taillight light-guide experiment
    sheet("taillight_lightguide_test.png", [
        ("CURRENT", os.path.join(M, "tail_baseline.png")),
        ("REFERENCE MATERIALS, NO LIGHT GUIDE",
         os.path.join(C, "tail_reference_nogeom.png")),
        ("+ TEMP LIGHT GUIDE GEOMETRY",
         os.path.join(C, "tail_reference_guide.png")),
    ], 3, "460x318")

    # 6. AO / contact shadow probe
    sheet("ao_contact_shadow.png", [
        ("AO PROBE - door seam / handle", os.path.join(C, "ao_seam.png")),
    ], 1, "620x430")

    # 7. hero at three sizes
    hero = os.path.join(C, "hero.png")
    hero600 = to_600(hero, os.path.join(C, "hero_600px.png"))
    _, hero_crop = horizon(hero, "hero", C)
    sheet("hero_max_quality.png", [
        ("MODEL A MAX QUALITY - full", hero),
        ("MODEL A MAX QUALITY - car at 600px", hero600),
        ("MODEL A MAX QUALITY - Horizon 1:1", hero_crop),
    ], 3, "620x430")

    # 8. MODEL A vs MODEL B
    sheet("model_a_vs_model_b.png", [
        ("MODEL A (cleaned, photoreal silver)", os.path.join(C, "model_a.png")),
        ("MODEL B (neutral silver, same rig)",
         os.path.join(C, "model_b.png")),
    ], 2, "620x430")

    # 9. copy the machine-readable reports next to the images
    for src in ("remesh_report_0.0025.json", "remesh_report.json",
                "hero_report.json", "tail_report.json"):
        p = os.path.join(C, src)
        if os.path.isfile(p):
            Image.open  # no-op to keep linters quiet about the unused import
            with open(p) as fh:
                data = json.load(fh)
            with open(os.path.join(OUT, src), "w") as fh:
                json.dump(data, fh, indent=2)
                fh.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
