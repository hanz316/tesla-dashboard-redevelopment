#!/usr/bin/env python3
"""V5 evidence: 20 states, sheets, the navigation probe and the cost report.

The screenshots are for human review. Nothing in here decides whether V5 looks
right; the objective checks live in the layout QA and in the probe below.

Usage:
    python3 tools/preview/horizon_v5_evidence.py
"""

import json
import os
import subprocess
import sys
import tempfile

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
PREVIEW = os.path.join(REPO, "tools", "preview", "scene_preview.py")
LAYOUT = os.path.join(REPO, "assets", "ui", "horizon_v5_layout.json")
TOKENS = os.path.join(REPO, "assets", "ui", "horizon_v5_tokens.json")
SCENE = os.path.join(REPO, "scenes", "horizon_v5.scene")
OUT = os.path.join(REPO, "assets", "checkpoints", "horizon_v5")
CANVAS_PIXELS = 1920 * 480


def cost(layout):
    components = layout["components"]
    static_bg = [c for c in components if c.get("layer") == "static"
                 and c.get("kind") == "vector"
                 and c.get("exempt_from_safe_area")]
    state_layers = [c for c in components if c.get("visibility")]
    dynamic_text = [c for c in components if c.get("kind") == "text"
                    and c.get("layer") == "dynamic"]
    return {
        "static_background_layers": len(static_bg),
        "baked_background_assets": 1,
        "persistent_decoded_assets": 5,
        "estimated_rgba_resident_kb": round(
            (CANVAS_PIXELS * 4 + 260 * 179 * 4 * 4) / 1024.0, 1),
        "cropped_vehicle_frame": [260, 179],
        "state_overlays": len(state_layers),
        "maximum_simultaneous_state_overlays": 3,
        "dynamic_text_nodes": len(dynamic_text),
        "maximum_simultaneous_animation_sequences": 2,
        "per_frame_bitmaps_beyond_vehicle": 0,
        "notes": [
            "ESTIMATED on the Mac; UNKNOWN UNTIL DEVICE TEST on T113",
            "the background is one baked 1920x480 bitmap, the vehicle is the "
            "only per-frame bitmap, decoration is static or opacity-only",
        ],
    }


def navigation_probe(scene_doc):
    """How many pixels a hidden navigation contributes (must be zero)."""
    import numpy as np
    from PIL import Image
    directory = tempfile.mkdtemp()

    def render(predicate, name):
        doc = json.loads(json.dumps(scene_doc))
        doc["nodes"] = [node for node in doc["nodes"] if not predicate(node)]
        path = os.path.join(directory, name + ".scene")
        with open(path, "w") as fh:
            json.dump(doc, fh)
        subprocess.run([sys.executable, PREVIEW, "--scene", path, "--state",
                        "v5_neutral", "--out", directory, "--out-name", name],
                       check=True, capture_output=True)
        return os.path.join(directory, name + ".png")

    without = render(lambda node: node["id"].startswith("nav.")
                     or node.get("source") == "clock", "no_nav")
    with_nav = render(lambda node: node.get("source") == "clock", "with_nav")
    a = np.asarray(Image.open(without).convert("RGB")).astype(int)
    b = np.asarray(Image.open(with_nav).convert("RGB")).astype(int)
    return int((np.abs(a - b).max(axis=2) > 2).sum())


def main():
    from PIL import Image, ImageDraw, ImageFont
    layout = json.load(open(LAYOUT))
    tokens = json.load(open(TOKENS))
    scene_doc = json.load(open(SCENE))
    states = layout["screenshot_states"]
    names = layout["screenshot_names"]
    os.makedirs(OUT, exist_ok=True)
    rendered = []
    for state, name in zip(states, names):
        subprocess.run([sys.executable, PREVIEW, "--scene", SCENE, "--state",
                        state, "--out", OUT, "--out-name", name[:-4]],
                       check=True, capture_output=True)
        path = os.path.join(OUT, name)
        if Image.open(path).size != (1920, 480):
            sys.exit(f"[v5] {name} is not 1920x480")
        rendered.append(path)
    try:
        font = ImageFont.truetype(
            "/System/Library/Fonts/Supplemental/Arial Bold.ttf", 22)
        big = ImageFont.truetype(
            "/System/Library/Fonts/Supplemental/Arial Bold.ttf", 28)
    except OSError:  # pragma: no cover
        font = big = ImageFont.load_default()

    cell_w, cell_h, label_h = 960, 240, 26
    sheet = Image.new("RGB", (cell_w, (cell_h + label_h) * len(rendered)),
                      (10, 14, 18))
    draw = ImageDraw.Draw(sheet)
    for index, path in enumerate(rendered):
        image = Image.open(path).convert("RGB").resize((cell_w, cell_h),
                                                       Image.LANCZOS)
        top = index * (cell_h + label_h)
        sheet.paste(image, (0, top + label_h))
        draw.text((10, top + 4), os.path.basename(path)[:-4],
                  fill=(220, 228, 235), font=font)
    contact = os.path.join(OUT, "horizon_v5_contact_sheet.png")
    sheet.save(contact)

    key = ["horizon_v5_01_neutral.png", "horizon_v5_02_left_indicator.png",
           "horizon_v5_05_brake.png", "horizon_v5_10_door_fl.png",
           "horizon_v5_20_navigation.png"]
    physical = Image.new("RGB", (960 * 2, 240 * len(key) + 30), (10, 14, 18))
    draw = ImageDraw.Draw(physical)
    draw.text((10, 4), "physical scale: half size, as seen on the panel",
              fill=(220, 228, 235), font=font)
    for index, name in enumerate(key):
        image = Image.open(os.path.join(OUT, name)).convert("RGB").resize(
            (960, 240), Image.LANCZOS)
        physical.paste(image, (0, 30 + index * 240))
    physical_path = os.path.join(OUT, "horizon_v5_physical_scale.png")
    physical.save(physical_path)

    hidden = navigation_probe(scene_doc)
    vehicle = next(c for c in layout["components"] if c["id"] == "vehicle")
    report = {
        "schema": "horizon-v5-evidence v1",
        "status": "HORIZON_V5_VISUAL = AWAITING HUMAN VISUAL APPROVAL",
        "reference": {
            "expected_image": tokens["reference"]["image"],
            "state": tokens["reference"]["state"],
            "background_art": ("BACKGROUND_ART_REQUIRED"
                               if tokens["reference"]["state"] !=
                               "MEASURED_FROM_REFERENCE" else "MEASURED"),
        },
        "vehicle_bounds": vehicle["bounds"],
        "vehicle_visible_bounds_closed": vehicle["visible_bounds_closed"],
        "navigation_hidden_pixels": hidden,
        "screenshots": {name: os.path.relpath(path, REPO)
                        for name, path in zip(names, rendered)},
        "contact_sheet": os.path.relpath(contact, REPO),
        "physical_scale": os.path.relpath(physical_path, REPO),
        "cost": cost(layout),
    }
    with open(os.path.join(OUT, "horizon_v5_report.json"), "w") as fh:
        json.dump(report, fh, indent=1)
        fh.write("\n")
    print(f"[v5] {len(rendered)} states, contact {os.path.relpath(contact, REPO)}")
    print(f"[v5] physical scale {os.path.relpath(physical_path, REPO)}")
    print(f"[v5] navigation hidden pixels: {hidden}")
    print(f"[v5] reference state {tokens['reference']['state']}, "
          f"background {report['reference']['background_art']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
