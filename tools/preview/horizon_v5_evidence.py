#!/usr/bin/env python3
"""The review deliverables for Horizon V5.

The human review asked for four things and nothing else this round:

    A  the reference                        assets/ui/horizon_v5_reference.png
    B  the implementation, neutral          horizon_v5_neutral.png
    C  reference vs implementation          horizon_v5_reference_vs_implementation.png
    D  the neutral at physical size         horizon_v5_physical_scale.png

plus the numbers: the visible vehicle silhouette measured from the final
1920x480 render (not from a node box), both cluster boxes, and the decoded
memory estimate. Nothing here decides whether V5 looks right - that stays a
human decision, and the report says so.

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
REFERENCE = os.path.join(REPO, "assets", "ui", "horizon_v5_reference.png")
MEASUREMENTS = os.path.join(REPO, "assets", "ui",
                            "horizon_v5_reference_measurements.json")
OUT = os.path.join(REPO, "assets", "checkpoints", "horizon_v5")
CONTENT_SCALE = 480 / 724.0


def render(state, name, scene=SCENE, out=OUT, extra=()):
    subprocess.run([sys.executable, PREVIEW, "--scene", scene, "--state",
                    state, "--out", out, "--out-name", name, *extra],
                   check=True, capture_output=True)
    return os.path.join(out, name + ".png")


def union_box(components, roles):
    boxes = [c["bounds"] for c in components if c.get("role") in roles]
    if not boxes:
        return None
    x0 = min(b["x"] for b in boxes)
    y0 = min(b["y"] for b in boxes)
    x1 = max(b["x"] + b["w"] for b in boxes)
    y1 = max(b["y"] + b["h"] for b in boxes)
    return [round(x0, 1), round(y0, 1), round(x1 - x0, 1), round(y1 - y0, 1)]


def vehicle_bbox_from_render(neutral_path, layout):
    """Measure the vehicle's contribution from the final 1920x480 render: the
    same frame with the vehicle layers removed, differenced.

    The car and its ground response are separated by the ground contact row of
    the baked layer, so "visible silhouette" is the car itself and not the
    reflection underneath it."""
    import numpy as np
    from PIL import Image
    document = json.load(open(SCENE))
    document["nodes"] = [node for node in document["nodes"]
                         if not node["id"].startswith("vehicle.")]
    scratch = tempfile.mkdtemp(prefix="v5-evidence-")
    stripped_scene = os.path.join(scratch, "no_vehicle.scene")
    with open(stripped_scene, "w") as handle:
        json.dump(document, handle)
    without = render("v5_neutral", "no_vehicle", scene=stripped_scene,
                     out=scratch)
    a = np.asarray(Image.open(neutral_path).convert("RGB")).astype(int)
    b = np.asarray(Image.open(without).convert("RGB")).astype(int)
    difference = np.abs(a - b).max(axis=2)
    layer = next(c for c in layout["components"]
                 if c.get("role") == "vehicle")
    with Image.open(os.path.join(REPO, layer["src"])) as image:
        alpha = image.convert("RGBA").getchannel("A")
        solid = alpha.point(lambda value: 255 if value > 200 else 0).getbbox()
    contact = layer["bounds"]["y"] + (solid[3] if solid else layer["bounds"]["h"])
    mask = difference > 6
    ys, xs = np.nonzero(mask)
    if xs.size == 0:
        return None, 0, contact
    car_mask = mask.copy()
    car_mask[max(0, contact):, :] = False
    ys2, xs2 = np.nonzero(car_mask)
    # [x, y, w, h] like every other box in the report.
    car = ([int(xs2.min()), int(ys2.min()),
            int(xs2.max()) + 1 - int(xs2.min()),
            int(ys2.max()) + 1 - int(ys2.min())] if xs2.size else None)
    vehicle = [int(xs.min()), int(ys.min()),
               int(xs.max()) + 1 - int(xs.min()),
               int(ys.max()) + 1 - int(ys.min())]
    return {"visible_silhouette": car, "with_ground_response": vehicle}, \
        int(mask.sum()), int(car_mask.sum()), contact


def decoded_memory(layout):
    from PIL import Image
    total = 0
    entries = []
    for component in layout["components"]:
        if component.get("kind") != "image":
            continue
        path = os.path.join(REPO, component["src"])
        if not os.path.isfile(path):
            continue
        with Image.open(path) as image:
            width, height = image.size
        size = width * height * 4
        total += size
        entries.append({"id": component["id"], "size": [width, height],
                        "decoded_rgba_bytes": size})
    return {"assets": entries, "total_decoded_rgba_bytes": total,
            "total_decoded_mb": round(total / (1024.0 * 1024.0), 2),
            "note": "ESTIMATED on the Mac; UNKNOWN UNTIL DEVICE TEST on T113"}


def main():
    from PIL import Image, ImageDraw, ImageFont
    if not os.path.isfile(REFERENCE):
        print("[v5-evidence] HORIZON_V5_REFERENCE_MISSING")
        return 2
    os.makedirs(OUT, exist_ok=True)
    layout = json.load(open(LAYOUT))
    tokens = json.load(open(TOKENS))
    measurements = json.load(open(MEASUREMENTS))

    neutral = render("v5_neutral", "horizon_v5_neutral")
    if Image.open(neutral).size != (1920, 480):
        sys.exit("[v5-evidence] the neutral render is not 1920x480")
    states = []
    for state, name in zip(layout["screenshot_states"],
                           layout["screenshot_names"]):
        states.append(render(state, name[:-4]))

    # C: reference on the left, implementation on the right, both 1920x480.
    reference = Image.open(REFERENCE).convert("RGB")
    scaled = reference.resize((int(round(reference.width * CONTENT_SCALE)),
                               int(round(reference.height * CONTENT_SCALE))),
                              Image.LANCZOS)
    left = Image.new("RGB", (1920, 480), (6, 8, 12))
    left.paste(scaled, ((1920 - scaled.width) // 2, (480 - scaled.height) // 2))
    right = Image.open(neutral).convert("RGB")
    side_by_side = Image.new("RGB", (3840, 480), (6, 8, 12))
    side_by_side.paste(left, (0, 0))
    side_by_side.paste(right, (1920, 0))
    draw = ImageDraw.Draw(side_by_side)
    try:
        font = ImageFont.truetype(
            "/System/Library/Fonts/Supplemental/Arial.ttf", 18)
    except OSError:  # pragma: no cover
        font = ImageFont.load_default()
    for index, label in enumerate(("A  reference (mapped 1:1 by height)",
                                   "B  implementation, neutral")):
        draw.text((18 + index * 1920, 8), label, fill=(190, 200, 210), font=font)
    comparison = os.path.join(OUT, "horizon_v5_reference_vs_implementation.png")
    side_by_side.save(comparison)

    # D: the neutral at physical size - half scale, as the panel shows it.
    physical = Image.new("RGB", (960, 270), (6, 8, 12))
    physical.paste(right.resize((960, 240), Image.LANCZOS), (0, 30))
    draw = ImageDraw.Draw(physical)
    draw.text((10, 6), "D  neutral at half size (as seen on the panel), "
                       "1:1 pixels otherwise", fill=(190, 200, 210), font=font)
    physical_path = os.path.join(OUT, "horizon_v5_physical_scale.png")
    physical.save(physical_path)

    vehicle, changed, car_pixels, contact = vehicle_bbox_from_render(
        neutral, layout)
    report = {
        "schema": "horizon-v5-evidence v2",
        "status": "HORIZON_V5_NEUTRAL = AWAITING HUMAN VISUAL APPROVAL",
        "why": "IMPLEMENT, MEASURE, RENDER, REPORT - no visual claim is made "
               "here. Only a human decides whether this matches the reference.",
        "reference": {
            "file": os.path.relpath(REFERENCE, REPO),
            "size": list(reference.size),
            "status": "PRESENT",
            "mapping": tokens["reference"]["mapping"],
        },
        "deliverables": {
            "A_reference": os.path.relpath(REFERENCE, REPO),
            "B_implementation_neutral": os.path.relpath(neutral, REPO),
            "C_reference_vs_implementation": os.path.relpath(comparison, REPO),
            "D_physical_scale": os.path.relpath(physical_path, REPO),
        },
        "other_screenshots": {os.path.basename(path): os.path.relpath(path, REPO)
                              for path in states},
        "vehicle_bbox_from_final_render": vehicle,
        "vehicle_pixels_changed": changed,
        "vehicle_pixels_solid": car_pixels,
        "ground_contact_row": contact,
        "speed_cluster_bbox": union_box(layout["components"], {"speed"}),
        "energy_cluster_bbox": union_box(layout["components"], {"energy"}),
        "driver_cluster_bbox": union_box(layout["components"], {"driver"}),
        "navigation_hidden_pixels": navigation_probe(),
        "reference_measurements": {
            "canvas": measurements["canvas"],
            "horizon_row": measurements["horizon"]["horizon_row"],
            "horizon_fraction": measurements["horizon"]["horizon_fraction"],
            "vehicle": measurements["vehicle"],
            "accent": measurements["accent"],
            "thirds": measurements["thirds"],
            "bands": {
                "top": measurements["luminance"]["top_band_mean"],
                "middle": measurements["luminance"]["middle_band_mean"],
                "bottom": measurements["luminance"]["bottom_band_mean"],
            },
        },
        "decoded_memory": decoded_memory(layout),
        "background_asset": tokens["cost_model"]["baked_background"],
        "runtime_blur": "none",
    }
    report_path = os.path.join(OUT, "horizon_v5_report.json")
    with open(report_path, "w") as handle:
        json.dump(report, handle, indent=1)
        handle.write("\n")
    print(f"[v5-evidence] neutral            {os.path.relpath(neutral, REPO)}")
    print(f"[v5-evidence] reference vs impl  {os.path.relpath(comparison, REPO)}")
    print(f"[v5-evidence] physical size      {os.path.relpath(physical_path, REPO)}")
    print(f"[v5-evidence] vehicle bbox       {vehicle}")
    print(f"[v5-evidence] decoded memory     "
          f"{report['decoded_memory']['total_decoded_mb']} MB")
    print(f"[v5-evidence] report             {os.path.relpath(report_path, REPO)}")
    return 0


def navigation_probe():
    """A hidden navigation must draw zero pixels."""
    import numpy as np
    from PIL import Image
    import tempfile
    document = json.load(open(SCENE))
    directory = tempfile.mkdtemp()

    def render_without(name, predicate):
        doc = json.loads(json.dumps(document))
        doc["nodes"] = [node for node in doc["nodes"] if not predicate(node)]
        scene_path = os.path.join(directory, name + ".scene")
        with open(scene_path, "w") as handle:
            json.dump(doc, handle)
        return render("v5_neutral", name, scene=scene_path, out=directory)

    # Both renders drop the clock; the only difference between them is the
    # navigation itself, so any pixel difference is navigation ink.
    without = render_without("no_nav", lambda node:
                             node["id"].startswith("nav.")
                             or node.get("source") == "clock")
    with_nav = render_without("with_nav", lambda node:
                              node.get("source") == "clock")
    a = np.asarray(Image.open(without).convert("RGB")).astype(int)
    b = np.asarray(Image.open(with_nav).convert("RGB")).astype(int)
    return int((np.abs(a - b).max(axis=2) > 2).sum())


if __name__ == "__main__":
    sys.exit(main())
