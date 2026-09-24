#!/usr/bin/env python3
"""Render the Horizon V2 screenshot set.

Twelve states, each exactly 1920x480, produced by the same previewer a human
would run by hand. Nothing is scaled up from a smaller render: the canvas size
is asserted after every render.

The states live in the previewer's mock table and are developer fixtures. They
are the only place these screens get values; the production path projects real
VehicleState and has no fixtures at all.

Usage:
    python3 tools/preview/horizon_v2_shots.py
"""

import json
import os
import subprocess
import sys

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
SCENE = os.path.join(REPO, "scenes", "horizon_v2.scene")
LAYOUT = os.path.join(REPO, "assets", "ui", "horizon_v2_layout.json")
OUT = os.path.join(REPO, "assets", "checkpoints", "horizon_v2")
PREVIEW = os.path.join(REPO, "tools", "preview", "scene_preview.py")

LABELS = {
    "h2_neutral": "neutral",
    "h2_door_fl": "door FL open",
    "h2_door_fr": "door FR open",
    "h2_door_rl": "door RL open",
    "h2_door_rr": "door RR open",
    "h2_all_doors": "all doors open",
    "h2_frunk": "frunk open",
    "h2_trunk": "trunk open",
    "h2_trunk_left": "trunk open + left indicator",
    "h2_trunk_hazard": "trunk open + hazard",
    "h2_brake": "brake",
    "h2_left": "left indicator",
    "h2_right": "right indicator",
    "h2_hazard": "hazard",
    "h2_mixed": "mixed: brake + FL + frunk + trunk + left",
    "h2_low_soc": "low SOC",
    "h2_unknown": "unknown (no data)",
    "h2_navigation": "navigation",
}


def main():
    with open(LAYOUT) as fh:
        layout = json.load(fh)
    states = layout["screenshot_states"]
    names = layout["screenshot_names"]
    if len(states) != len(names):
        sys.exit("[shots] layout lists a different number of states and names")

    os.makedirs(OUT, exist_ok=True)
    from PIL import Image

    rendered = []
    for state, name in zip(states, names):
        result = subprocess.run(
            [sys.executable, PREVIEW, "--scene", SCENE, "--state", state,
             "--out", OUT, "--out-name", name[:-len(".png")]],
            capture_output=True, text=True)
        path = os.path.join(OUT, name)
        if result.returncode != 0 or not os.path.exists(path):
            sys.exit(f"[shots] {state} failed:\n{result.stdout}\n{result.stderr}")
        image = Image.open(path)
        if image.size != (1920, 480):
            sys.exit(f"[shots] {name} is {image.size}, not 1920x480")
        rendered.append(path)
        print(f"[shots] {name:32s} {image.size[0]}x{image.size[1]}")

    # Contact sheet: the states a human needs to judge the moving panels, in
    # the order the layout lists, then everything else. Review aid only.
    order = layout.get("contact_sheet_order") or states
    sheet_states = [s for s in order if s in states] + \
                   [s for s in states if s not in order]
    from PIL import ImageDraw
    cell_w, cell_h, label_h = 960, 240, 26
    sheet = Image.new("RGB", (cell_w, (cell_h + label_h) * len(sheet_states)),
                      (10, 14, 18))
    draw = ImageDraw.Draw(sheet)
    by_state = dict(zip(states, rendered))
    for index, state in enumerate(sheet_states):
        path = by_state[state]
        image = Image.open(path).convert("RGB").resize((cell_w, cell_h),
                                                       Image.LANCZOS)
        y = index * (cell_h + label_h)
        sheet.paste(image, (0, y + label_h))
        draw.text((10, y + 6), LABELS[state], fill=(220, 228, 235))
    sheet_path = os.path.join(OUT, "horizon_v2_contact_sheet.png")
    sheet.save(sheet_path)
    print(f"[shots] contact sheet -> {os.path.relpath(sheet_path, REPO)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
