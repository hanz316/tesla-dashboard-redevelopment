#!/usr/bin/env python3
"""Parts L/M: four-column comparison, 600 px size check, Horizon check.

Columns: CURRENT / GEOMETRY-NORMAL FIX ONLY / MATERIAL FIX ONLY / BOTH.
Every column uses the same HDRI (Photo Studio 01), the same hybrid rig, the
same camera, exposure, resolution and sample count.

Each column is emitted at full size AND at the real dashboard size (car at
600 px wide), because an effect that only exists at full resolution has no
value for this project.
"""

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
M = os.path.join(REPO_ROOT, "assets", "rendered", "material_study")
OUT = os.path.join(M, "checks")
DASH = os.path.join(REPO_ROOT, "tools", "assets", "make_comparison_sheet.py")
SCENE = os.path.join(REPO_ROOT, "scenes", "horizon_redesign_a.scene")
BOX = "700x401@610,40"

COLUMNS = [
    ("baseline", "CURRENT"),
    ("geom", "GEOMETRY / NORMAL FIX ONLY"),
    ("material", "MATERIAL FIX ONLY"),
    ("both", "GEOMETRY + MATERIAL FIX"),
]


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


def horizon(src, key):
    name = f"horizon_{key}"
    subprocess.run(
        ["python3", os.path.join(REPO_ROOT, "tools", "preview",
                                 "scene_preview.py"),
         "--scene", SCENE, "--state", "normal_drive",
         "--vehicle-image", src, "--vehicle-crop", "--vehicle-box", BOX,
         "--out-name", name, "--out", OUT],
        check=True, capture_output=True)
    full = os.path.join(OUT, name + ".png")
    left = 510
    crop = os.path.join(OUT, f"{key}_horizon.png")
    Image.open(full).convert("RGB").crop((left, 0, left + 900, 480)).save(crop)
    return full, crop


def main():
    os.makedirs(OUT, exist_ok=True)
    full_entries, small_entries, horizon_entries = [], [], []
    for key, label in COLUMNS:
        src = os.path.join(M, f"final_{key}.png")
        small = to_600(src, os.path.join(OUT, f"final_{key}_600px.png"))
        _, hcrop = horizon(src, f"final_{key}")
        full_entries.append((label, src))
        small_entries.append((f"{label} - car at 600px", small))
        horizon_entries.append((f"{label} - Horizon 1:1", hcrop))
        print(f"[final] {key:9s} -> {os.path.basename(hcrop)}")

    def sheet(name, entries, cols, cell):
        cmd = ["python3", DASH, "--out", os.path.join(M, name),
               "--cols", str(cols), "--cell", cell]
        for label, path in entries:
            cmd += ["--image", f"{label}={path}"]
        print(subprocess.run(cmd, capture_output=True, text=True).stdout.strip())

    sheet("vehicle_material_diagnostic_4column.png", full_entries, 4, "460x318")
    sheet("vehicle_material_diagnostic_600px.png", small_entries, 4, "460x318")
    sheet("vehicle_material_diagnostic_horizon.png", horizon_entries, 2,
          "620x330")

    # The individual study sheets.
    paint_entries = [(f"PAINT {p.upper()}", os.path.join(M, f"paint_{p}.png"))
                     for p in ("a", "b", "c", "d")]
    sheet("paint_candidates.png", paint_entries, 4, "460x318")

    silver_entries = [(s.upper(), os.path.join(M, f"silver_{s}.png"))
                      for s in ("neutral", "cool", "graphite")]
    sheet("paint_colours.png", silver_entries, 3, "620x430")

    cc_entries = [("BASECOAT ONLY", os.path.join(M, "cc_basecoat.png")),
                  ("CLEARCOAT ONLY", os.path.join(M, "cc_clearcoat.png")),
                  ("COMBINED", os.path.join(M, "cc_combined.png"))]
    sheet("clearcoat_lobes.png", cc_entries, 3, "620x430")

    detail_entries = [
        ("glass CURRENT", os.path.join(M, "glass_baseline.png")),
        ("glass MATERIAL FIX", os.path.join(M, "glass_material.png")),
        ("taillight CURRENT", os.path.join(M, "tail_baseline.png")),
        ("taillight MATERIAL FIX", os.path.join(M, "tail_material.png")),
        ("wheel CURRENT", os.path.join(M, "wheel_baseline.png")),
        ("wheel MATERIAL FIX", os.path.join(M, "wheel_material.png")),
    ]
    sheet("detail_before_after.png", detail_entries, 3, "460x318")
    return 0


if __name__ == "__main__":
    sys.exit(main())
