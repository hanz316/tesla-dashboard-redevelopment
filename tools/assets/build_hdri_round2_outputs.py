#!/usr/bin/env python3
"""HDRI selection round 2: contact sheets, final comparison, Horizon checks.

Outputs:
  hdri_candidate_contact_sheet.png   candidates that passed the hard rules,
                                     600 px vehicle each
  hdri_eliminated_contact_sheet.png  what was thrown out and why, so the
                                     elimination can be audited
  hdri_final_3_comparison.png        3 HDRIs x 2 lighting modes
  horizon_<hdri>_<mode>.png          real 1920x480 composites
  <hdri>_<mode>_horizon.png          1:1 crop out of those composites

Usage:
    python3 tools/assets/build_hdri_round2_outputs.py
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
SCREEN = os.path.join(REPO_ROOT, "assets", "rendered", "hdri_round2")
OUT = os.path.join(SCREEN, "checks")
DASH = os.path.join(REPO_ROOT, "tools", "assets", "make_comparison_sheet.py")

# Background context for the size check. A Horizon redesign, NOT the old
# engineering page. The scene file is used exactly as committed.
CONTEXT_SCENE = os.path.join(REPO_ROOT, "scenes", "horizon_redesign_a.scene")
CONTEXT_STATE = "normal_drive"
CONTEXT_BOX = "700x401@610,40"

PASSED = [
    ("marry_hall", "Marry Hall"),
    ("photo_studio_01", "Photo Studio 01"),
    ("story_studio_02", "Story Studio 02"),
    ("monochrome_studio_01", "Monochrome Studio 01"),
    ("studio_kontrast_03", "Studio Kontrast 03"),
    ("pav_studio_01", "PAV Studio 01"),
]

ELIMINATED = [
    ("brown_photostudio_04", "Brown Photostudio 04",
     "5 roof stripes (>4) + clipped"),
    ("brown_photostudio_05", "Brown Photostudio 05", "clipped at common exposure"),
    ("monochrome_studio_03", "Monochrome Studio 03", "clipped at common exposure"),
    ("pav_studio_02", "PAV Studio 02", "clipped + roofHF 32.4"),
    ("CONTROL_kontrast_01_rejected", "Studio Kontrast 01 (control)",
     "rejected by human review; ranked 2nd worst roofHF"),
]

FINAL = [
    ("marry_hall", "HDRI A - Marry Hall"),
    ("photo_studio_01", "HDRI B - Photo Studio 01"),
    ("story_studio_02", "HDRI C - Story Studio 02"),
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


def horizon_check(vehicle_image, key):
    """Composite into the real Horizon and cut a 1:1 window out of it."""
    name = f"horizon_{key}"
    args = ["python3", os.path.join(REPO_ROOT, "tools", "preview",
                                    "scene_preview.py"),
            "--scene", CONTEXT_SCENE, "--state", CONTEXT_STATE,
            "--vehicle-image", vehicle_image, "--vehicle-crop",
            "--vehicle-box", CONTEXT_BOX, "--out-name", name, "--out", OUT]
    subprocess.run(args, check=True, capture_output=True)
    full = os.path.join(OUT, name + ".png")
    crop_w = 900
    left = max(0, min(1920 - crop_w, 960 - crop_w // 2))
    out = os.path.join(OUT, f"{key}_horizon.png")
    Image.open(full).convert("RGB").crop(
        (left, 0, left + crop_w, 480)).save(out)
    return full, out


def sheet(out_name, entries, cols, cell):
    cmd = ["python3", DASH, "--out", os.path.join(SCREEN, out_name),
           "--cols", str(cols), "--cell", cell]
    for label, path in entries:
        cmd += ["--image", f"{label}={path}"]
    print(subprocess.run(cmd, capture_output=True, text=True).stdout.strip())


def main():
    os.makedirs(OUT, exist_ok=True)

    # 1. contact sheet: every candidate that cleared the hard rules.
    entries = []
    for slug, label in PASSED:
        src = os.path.join(SCREEN, f"{slug}_only_600.png")
        entries.append((label, src))
    sheet("hdri_candidate_contact_sheet.png", entries, 3, "620x430")

    # 2. the rejections, so the elimination is auditable.
    entries = []
    for slug, label, reason in ELIMINATED:
        src = os.path.join(SCREEN, f"{slug}_only_600.png")
        entries.append((f"{label} - {reason}", src))
    sheet("hdri_eliminated_contact_sheet.png", entries, 3, "620x430")

    # 3. best three, both lighting modes, identical everything else.
    final_entries = []
    for slug, label in FINAL:
        for mode, mode_label in (("hdri", "ONLY"), ("hybrid", "HYBRID")):
            src = os.path.join(SCREEN, f"final_{slug}_{mode}.png")
            small = to_600(src, os.path.join(OUT, f"final_{slug}_{mode}_600.png"))
            full, _ = horizon_check(src, f"{slug}_{mode}")
            final_entries.append((f"{label} {mode_label}", small))
            print(f"[round2] {slug:18s} {mode:7s} -> {os.path.basename(full)}")
    sheet("hdri_final_3_comparison.png", final_entries, 2, "620x430")

    # 4. the six Horizon crops, shown as one more sheet so the size check is
    #    reviewable without opening six files.
    entries = []
    for slug, label in FINAL:
        for mode, mode_label in (("hdri", "ONLY"), ("hybrid", "HYBRID")):
            entries.append((f"{label} {mode_label} - Horizon 1:1",
                            os.path.join(OUT, f"{slug}_{mode}_horizon.png")))
    sheet("hdri_final_3_horizon.png", entries, 2, "620x330")
    return 0


if __name__ == "__main__":
    sys.exit(main())
