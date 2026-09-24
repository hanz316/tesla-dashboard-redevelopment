#!/usr/bin/env python3
"""Render the Mono page against the shared Horizon environment palette.

This is a small host-side checkpoint, not a production renderer.  It proves
that the low-cost page can follow the same day/night palette and still keep
invalid VehicleState values visibly unknown.
"""

import json
import subprocess
import sys
from pathlib import Path

from PIL import Image


ROOT = Path(__file__).resolve().parents[2]
SCENE = ROOT / "scenes" / "v6_mono.scene"
OUT = ROOT / "assets" / "checkpoints" / "v6_pages" / "mono"
PREVIEW = ROOT / "tools" / "preview" / "scene_preview.py"


def render(name, phase, state):
    OUT.mkdir(parents=True, exist_ok=True)
    prefix = OUT / name
    command = [sys.executable, str(PREVIEW), "--scene", str(SCENE),
               "--state", state, "--environment-phase", phase,
               "--out", str(OUT), "--out-name", name,
               "--allow-placeholder"]
    subprocess.run(command, cwd=ROOT, check=True, stdout=subprocess.PIPE,
                   stderr=subprocess.STDOUT, text=True)
    image = Image.open(str(prefix) + ".png").convert("RGB")
    half = image.resize((960, 240), Image.Resampling.LANCZOS)
    half.save(str(prefix) + "_half.png")
    pixels = list(image.getdata())
    bright = sum(1 for pixel in pixels if max(pixel) > 150)
    unknown = sum(1 for pixel in pixels if 65 <= pixel[0] <= 145 and
                  abs(pixel[0] - pixel[1]) < 18 and
                  abs(pixel[1] - pixel[2]) < 18)
    return {"phase": phase, "state": state, "size": list(image.size),
            "bright_pixels": bright, "neutral_mid_pixels": unknown,
            "output": str(prefix.relative_to(ROOT)) + ".png"}


def main():
    records = [
        render("mono_day_normal", "day", "driving"),
        render("mono_night_normal", "night", "driving"),
        render("mono_day_lost", "day", "lost"),
        render("mono_day_door", "day", "door_open"),
    ]
    report = {
        "page": "v6_mono",
        "source": "VehicleState + shared EnvironmentTimeSystem palette",
        "device_validation": "UNKNOWN_UNTIL_DEVICE_TEST",
        "records": records,
        "status": "HOST_BASELINE_PASS",
    }
    report_path = ROOT / "assets" / "checkpoints" / "v6_pages" / "mono_evidence.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
