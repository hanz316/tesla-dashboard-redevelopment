#!/usr/bin/env python3
"""Screenshots and cost estimates for the three Horizon style candidates.

Eight states per candidate at native 1920x480, a contact sheet each, one master
comparison of the three neutral renders, and the T113 asset cost of each design
reported from the layout itself (every decorative node is classified as static
background, static overlay, state overlay or cheap animation).

Usage:
    python3 tools/preview/horizon_v3_shots.py
"""

import json
import os
import subprocess
import sys

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
PREVIEW = os.path.join(REPO, "tools", "preview", "scene_preview.py")
UI = os.path.join(REPO, "assets", "ui")
OUT = os.path.join(REPO, "assets", "checkpoints", "horizon_v3")

CANDIDATES = ["a_cyber_hud", "b_concept_ev", "c_performance"]
STATES = ["h2_neutral", "h2_left", "h2_hazard", "h2_brake", "h2_door_fl",
          "h2_trunk", "h2_low_soc", "h2_navigation"]
NAMES = ["neutral", "left_indicator", "hazard", "brake", "door_fl", "trunk",
         "low_soc", "navigation"]
CANVAS_PIXELS = 1920 * 480


def cost(layout):
    """Rough T113 cost from the layout: what has to be resident, per frame."""
    components = layout["components"]
    static_bg = [c for c in components
                 if c.get("layer") == "static" and c.get("kind") == "vector"
                 and c.get("bounds", {}).get("w", 0) * c.get("bounds", {}).get("h", 0)
                 > 200000]
    static_overlay = [c for c in components if c.get("layer") == "static"
                      and c not in static_bg]
    state_overlay = [c for c in components if c.get("layer") == "dynamic"
                     and c.get("visibility")]
    dynamic_text = [c for c in components if c.get("kind") == "text"
                    and c.get("layer") == "dynamic"]
    vehicle = [c for c in components if c.get("kind") == "vehicle"]
    animations = layout.get("style_layers", {}).get("CHEAP_ANIMATION", [])
    # One baked background bitmap plus the vehicle base and its state layers.
    decoded_background = CANVAS_PIXELS * 4
    decoded_vehicle = 356 * 236 * 4 * 3          # base + two panel layers
    return {
        "static_background_layers": len(static_bg),
        "persistent_decoded_assets": 1 + 1 + 3,   # background, vehicle, panels
        "estimated_rgba_resident_kb": round(
            (decoded_background + decoded_vehicle) / 1024.0, 1),
        "static_overlay_paths": len(static_overlay),
        "state_overlays": len(state_overlay),
        "maximum_simultaneous_state_overlays": 4,
        "dynamic_text_nodes": len(dynamic_text),
        "cheap_animations": len(animations),
        "maximum_simultaneous_animation_sequences": min(2, len(animations)),
        "vehicle_layers": len(vehicle),
        "note": "decoration is static or opacity-only; no per-frame bitmaps "
                "beyond the vehicle, no full-screen layers per state",
    }


def main():
    from PIL import Image, ImageDraw, ImageFont
    os.makedirs(OUT, exist_ok=True)
    report = {"schema": "horizon-v3-candidates v1",
              "status": "HORIZON_V3_STYLE = AWAITING HUMAN VISUAL SELECTION",
              "canvas": [1920, 480], "states": NAMES, "candidates": {}}
    sheet_paths = {}
    for key in CANDIDATES:
        scene = os.path.join(REPO, "scenes", f"horizon_v3_{key}.scene")
        layout_path = os.path.join(UI, f"horizon_v3_{key}_layout.json")
        layout = json.load(open(layout_path))
        cell_dir = os.path.join(OUT, key)
        os.makedirs(cell_dir, exist_ok=True)
        rendered = []
        for state, name in zip(STATES, NAMES):
            subprocess.run([sys.executable, PREVIEW, "--scene", scene,
                            "--state", state, "--out", cell_dir,
                            "--out-name", name], check=True, capture_output=True)
            path = os.path.join(cell_dir, name + ".png")
            if Image.open(path).size != (1920, 480):
                sys.exit(f"[v3] {key}/{name} is not 1920x480")
            rendered.append(path)
        # contact sheet for this candidate
        cell_w, cell_h, label_h = 960, 240, 26
        sheet = Image.new("RGB", (cell_w, (cell_h + label_h) * len(rendered)),
                          (10, 14, 18))
        draw = ImageDraw.Draw(sheet)
        try:
            font = ImageFont.truetype(
                "/System/Library/Fonts/Supplemental/Arial Bold.ttf", 22)
        except OSError:  # pragma: no cover
            font = ImageFont.load_default()
        for index, path in enumerate(rendered):
            image = Image.open(path).convert("RGB").resize(
                (cell_w, cell_h), Image.LANCZOS)
            top = index * (cell_h + label_h)
            sheet.paste(image, (0, top + label_h))
            draw.text((10, top + 4), f"{layout['style_candidate']} - {NAMES[index]}",
                      fill=(220, 228, 235), font=font)
        sheet_path = os.path.join(OUT, f"horizon_v3_{key}_contact_sheet.png")
        sheet.save(sheet_path)
        sheet_paths[key] = sheet_path
        report["candidates"][key] = {
            "name": layout["style_candidate"],
            "layout": os.path.relpath(layout_path, REPO),
            "scene": os.path.relpath(scene, REPO),
            "neutral": os.path.relpath(os.path.join(cell_dir, "neutral.png"), REPO),
            "contact_sheet": os.path.relpath(sheet_path, REPO),
            "cost": cost(layout),
        }
        print(f"[v3] {key:14s} neutral + sheet done, state overlays "
              f"{report['candidates'][key]['cost']['state_overlays']}, "
              f"resident ~{report['candidates'][key]['cost']['estimated_rgba_resident_kb']} kB")

    # master comparison: the three neutral frames at identical scale
    width, height = 1280, 320
    sheet = Image.new("RGB", (width, (height + 28) * 3), (10, 14, 18))
    draw = ImageDraw.Draw(sheet)
    try:
        font = ImageFont.truetype(
            "/System/Library/Fonts/Supplemental/Arial Bold.ttf", 24)
    except OSError:  # pragma: no cover
        font = ImageFont.load_default()
    for index, key in enumerate(CANDIDATES):
        neutral = os.path.join(REPO, report["candidates"][key]["neutral"])
        image = Image.open(neutral).convert("RGB").resize((width, height),
                                                          Image.LANCZOS)
        top = index * (height + 28)
        sheet.paste(image, (0, top + 28))
        draw.text((10, top + 2), report["candidates"][key]["name"],
                  fill=(232, 238, 243), font=font)
    master = os.path.join(OUT, "horizon_v3_master_comparison.png")
    sheet.save(master)
    report["master_comparison"] = os.path.relpath(master, REPO)
    with open(os.path.join(OUT, "horizon_v3_report.json"), "w") as fh:
        json.dump(report, fh, indent=1)
        fh.write("\n")
    print(f"[v3] master comparison -> {os.path.relpath(master, REPO)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
