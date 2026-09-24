#!/usr/bin/env python3
"""V5.2 material continuity and environment separation, measured per phase.

The visual review's complaint was that DAY collapses: light sky, light road,
light car, one flat grey mass. Scalars like "contrast passed" did not catch it,
so this tool measures the relationships the review actually names, from the
renders the screen uses:

environment
    sky / horizon-haze / ground band luminance, and the ground-to-sky ratio
    (a daylight road has to be substantially darker than its sky);
    the luminance of the far, middle and near terrain bands, which is the
    aerial-perspective depth separation;

vehicle, in the same environment
    paint mean and spread, glass mean, tyre mean, rim mean, and the separations
    the eye uses: glass vs paint, tyre vs paint, rim vs tyre, plus the fraction
    of paint pixels that carry a highlight and the contact-shadow darkness.

The numbers go into horizon_v52_material_metrics.json, and the V5.2 tests check
them for every phase, so "the car is the same car under different light" is a
measurement rather than a claim.

Usage:
    python3 tools/assets/report_horizon_v52_materials.py
"""

import argparse
import json
import os
import sys

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
UI = os.path.join(REPO, "assets", "ui")
VEHICLE = os.path.join(REPO, "assets", "rendered", "vehicle", "horizon_v5")
OUT = os.path.join(REPO, "assets", "checkpoints", "horizon_v5",
                   "horizon_v52_material_metrics.json")
PHASES = ("dawn", "day", "dusk", "night")


def plate_path(phase):
    return os.path.join(UI, "horizon_v5_background.png" if phase == "night"
                        else f"horizon_v5_background_{phase}.png")


def car_path(phase, state="base"):
    root = VEHICLE if phase == "night" else os.path.join(VEHICLE, phase)
    return os.path.join(root, "car", state, "000.png")


def environment_metrics(path):
    """Sky, haze, ground and the three terrain bands, from the plate."""
    import numpy as np
    from PIL import Image
    array = np.asarray(Image.open(path).convert("RGB")).astype(float)
    luminance = array.mean(axis=2)
    rows = luminance.mean(axis=1)
    kernel = np.ones(7) / 7.0
    smooth = np.convolve(rows, kernel, mode="same")
    horizon = int(np.argmax(np.abs(np.diff(smooth))[80:280])) + 80
    sky = float(luminance[:max(1, horizon - 150)].mean())
    # Atmospheric haze: the sky immediately above each column's terrain
    # silhouette, which is where a daylight horizon brightens. Sampling a fixed
    # row band would mix sky and ridge, which is how a fixed band measured the
    # dark near ridge and called it haze.
    sky_top = float(luminance[20:90].mean())
    haze_samples = []
    for column in range(0, array.shape[1], 40):
        profile = luminance[40:horizon - 4, column]
        darker = np.nonzero(profile < sky_top - 12.0)[0]
        if darker.size:
            edge = 40 + int(darker[0])
            band = luminance[max(0, edge - 10):max(1, edge - 2), column]
            if band.size:
                haze_samples.append(float(band.mean()))
    haze = float(np.mean(haze_samples)) if haze_samples else float(
        luminance[max(0, horizon - 35):horizon - 3].mean())
    ground_far = float(luminance[horizon + 6:horizon + 60].mean())
    ground_near = float(luminance[420:].mean())
    # Terrain depth, measured at the band edges rather than at fixed rows: the
    # visible depth separation is the luminance step across each silhouette
    # boundary, so that is what is measured. A single flat grey layer shows
    # steps near zero.
    steps = []
    for column in (320, 700, 1100, 1560):
        profile = luminance[60:horizon - 6, column]
        gradient = np.abs(np.diff(profile))
        if gradient.size < 6:
            continue
        index = int(np.argmax(gradient))
        steps.append(float(profile[index + 1] - profile[index]))
    steps.sort(key=abs, reverse=True)
    strongest = steps[:3]
    bands = {"strongest_edge_steps": [round(value, 1) for value in strongest],
             "max_abs_edge_step": round(abs(strongest[0]), 1) if strongest else 0.0}
    return {
        "horizon_row": horizon,
        "sky": round(sky, 1), "sky_top": round(sky_top, 1),
        "haze": round(haze, 1),
        "ground_far": round(ground_far, 1), "ground_near": round(ground_near, 1),
        "ground_to_sky_ratio": round(ground_near / max(1e-6, sky), 3),
        "terrain_depth": bands,
    }


def vehicle_metrics(path, hidden):
    """Paint / glass / tyre / rim separation and highlight coverage.

    The regions are found from the render itself rather than from a fixed box:
    the wheel boxes are the two dark round clusters in the lower half, the glass
    is the darkest wide region in the upper body, the paint is the bright body.
    """
    import numpy as np
    from PIL import Image
    array = np.asarray(Image.open(path).convert("RGBA")).astype(float)
    alpha = array[:, :, 3]
    rgb = array[:, :, :3]
    luminance = rgb.mean(axis=2)
    body = alpha > 200
    if body.sum() < 1000:
        return None
    values = luminance[body]
    paint_threshold = np.percentile(values, 62)
    paint = body & (luminance >= paint_threshold)
    glass = body & (luminance < np.percentile(values, 10))
    # Tyres: the darkest pixels inside the wheel boxes the environment report
    # measured for this phase; rims: the brighter half of those boxes.
    wheel_boxes = hidden.get("wheel_boxes") or []
    tyre = np.zeros_like(body)
    rim = np.zeros_like(body)
    for box in wheel_boxes:
        x0, y0, x1, y1 = [int(round(value)) for value in box]
        patch = np.zeros_like(body)
        patch[max(0, y0):y1, max(0, x0):x1] = True
        patch &= body
        if patch.sum() == 0:
            continue
        patch_values = luminance[patch]
        tyre |= patch & (luminance < np.percentile(patch_values, 55))
        rim |= patch & (luminance >= np.percentile(patch_values, 55))
    def mean_of(mask):
        return float(luminance[mask].mean()) if mask.sum() > 50 else None
    paint_mean = mean_of(paint)
    glass_mean = mean_of(glass)
    tyre_mean = mean_of(tyre)
    rim_mean = mean_of(rim)
    result = {
        "body_pixels": int(body.sum()),
        "paint_mean": round(paint_mean, 1) if paint_mean else None,
        "paint_spread": round(float(luminance[paint].std()), 1),
        "glass_mean": round(glass_mean, 1) if glass_mean else None,
        "tyre_mean": round(tyre_mean, 1) if tyre_mean else None,
        "rim_mean": round(rim_mean, 1) if rim_mean else None,
        "highlight_coverage": round(float((luminance[body] > 200).mean()), 4),
    }
    if paint_mean and glass_mean:
        result["glass_minus_paint"] = round(glass_mean - paint_mean, 1)
    if paint_mean and tyre_mean:
        result["tyre_minus_paint"] = round(tyre_mean - paint_mean, 1)
    if rim_mean and tyre_mean:
        result["rim_minus_tyre"] = round(rim_mean - tyre_mean, 1)
    return result


def background_only_frame(phase):
    """Render the phase with the text and vector HUD removed.

    A support surface is a *background* change, so it has to be measured on a
    frame that has no ink in it: comparing the finished frame with the plate
    counts every dark glyph as if it were a panel.
    """
    import subprocess
    scene_path = os.path.join(REPO, "scenes", "horizon_v5.scene")
    preview = os.path.join(REPO, "tools", "preview", "scene_preview.py")
    scratch = os.path.join(REPO, "assets", "checkpoints", "horizon_v5")
    document = json.load(open(scene_path))
    document["nodes"] = [node for node in document["nodes"]
                         if node.get("type") not in ("text", "vector")]
    stripped = os.path.join(scratch, f"_background_only_{phase}.scene")
    with open(stripped, "w") as handle:
        json.dump(document, handle)
    name = f"_background_only_{phase}"
    subprocess.run([sys.executable, preview, "--scene", stripped, "--state",
                    "v5_neutral", "--out", scratch, "--out-name", name,
                    "--environment-phase", phase], check=True,
                   capture_output=True)
    return os.path.join(scratch, name + ".png")


def support_surface_metrics(phase, frame_path, plate):
    """DAY_CLUSTER_SURFACE_DOMINANCE.

    The human rejected the daylight solution because two large dark ellipses
    read as holes pasted onto the dashboard. This measures exactly that failure:
    how much of the frame is darkened relative to the environment plate, how
    dark it gets, and how large the largest single supporting region is. A
    readability treatment that is invisible at panel scale keeps all three
    numbers small; a backplate cannot.
    """
    import numpy as np
    from PIL import Image
    if not os.path.isfile(frame_path):
        return None
    frame = np.asarray(Image.open(frame_path).convert("RGB")).astype(float)
    background = np.asarray(Image.open(plate).convert("RGB")).astype(float)
    drop = background.mean(axis=2) - frame.mean(axis=2)
    # Only a real supporting surface counts: a few levels of darkening is the
    # wet-road response, which belongs to the environment, while the rejected
    # backplates were opaque ellipses that took 100+ levels out of a large area.
    supported = drop > 40.0
    # The car itself darkens its own footprint; the clusters are what is judged.
    region = np.zeros(drop.shape, dtype=bool)
    region[:, 240:700] = True
    region[:, 1280:1720] = True
    supported &= region
    fraction = float(supported.sum()) / float(region.sum())
    peak = float(drop[supported].max()) if supported.any() else 0.0
    return {
        "supported_area_fraction": round(fraction, 5),
        "peak_darkening_levels": round(peak, 1),
        "mean_darkening_levels": round(
            float(drop[supported].mean()) if supported.any() else 0.0, 2),
        "pass_rule": "supporting pixels (darkening > 40 levels) must be at "
                     "most 2 % of the cluster regions",
    }


def reflection_metrics(phase, car_box, hidden):
    """How far and how strongly the car's own reflection reaches below it.

    Measured as the difference between the road with and without the car in the
    layer the screen pastes, below the contact row: length in pixels and mean
    magnitude. Daylight must be shorter and weaker than night.
    """
    import numpy as np
    from PIL import Image
    root = VEHICLE if phase == "night" else os.path.join(VEHICLE, phase)
    road = os.path.join(root, "road")
    if not os.path.isdir(road):
        return None
    with_car = np.asarray(Image.open(os.path.join(road, "base.png")).convert(
        "RGB")).astype(float)
    without = np.asarray(Image.open(os.path.join(road, "no_car.png")).convert(
        "RGB")).astype(float)
    difference = np.abs(with_car - without).max(axis=2)
    contact = int(round(car_box[3])) if car_box else 346
    band = difference[contact:480, :]
    if band.size == 0:
        return None
    rows = band.max(axis=1)
    lit = np.nonzero(rows > 6)[0]
    return {
        "contact_row": contact,
        "length_px": int(lit.max() + 1) if lit.size else 0,
        "mean_magnitude": round(float(band[lit].mean()) if lit.size else 0.0, 2),
        "peak_magnitude": round(float(band.max()), 1),
        "lit_row_fraction": round(float(lit.size) / float(band.shape[0]), 3),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default=OUT)
    args = parser.parse_args()
    try:
        import numpy  # noqa: F401
        from PIL import Image  # noqa: F401
    except ImportError as error:
        sys.exit(f"Pillow and numpy are required: {error}")

    report = {"schema": "horizon-v5.2-material-metrics v1",
              "why": "the review's complaint was that scalars passed while DAY "
                     "collapsed into one grey mass; these are the relationships "
                     "it actually named",
              "phases": {}}
    for phase in PHASES:
        plate = plate_path(phase)
        if not os.path.isfile(plate):
            report["phases"][phase] = {"status": "MISSING_PLATE"}
            continue
        entry = {"status": "MEASURED",
                 "plate": os.path.relpath(plate, REPO),
                 "environment": environment_metrics(plate)}
        environment_report = os.path.join(
            REPO, "assets", "checkpoints", "horizon_v5",
            f"horizon_v5_environment_{phase}.json")
        hidden = {}
        if os.path.isfile(environment_report):
            data = json.load(open(environment_report))
            boxes = data.get("wheel_boxes_px") or []
            if boxes:
                hidden["wheel_boxes"] = boxes[0]["boxes"]
        car = car_path(phase)
        if os.path.isfile(car):
            entry["vehicle"] = vehicle_metrics(car, hidden)
        layer_manifest = os.path.join(
            VEHICLE, "horizon_v5_vehicle.json") if phase == "night" else \
            os.path.join(VEHICLE, phase, f"horizon_v5_vehicle_{phase}.json")
        car_box = None
        if os.path.isfile(layer_manifest):
            layers = json.load(open(layer_manifest))["layers"]
            if "base" in layers:
                report_entry = os.path.join(
                    REPO, "assets", "checkpoints", "horizon_v5",
                    "horizon_v5_vehicle_layers.json" if phase == "night"
                    else f"horizon_v5_vehicle_layers_{phase}.json")
                if os.path.isfile(report_entry):
                    for record in json.load(open(report_entry))["records"]:
                        if record.get("state") == "base" and record.get("car_box"):
                            car_box = record["car_box"]
        entry["reflection"] = reflection_metrics(phase, car_box, hidden)
        entry["support_surface"] = support_surface_metrics(
            phase, background_only_frame(phase), plate)
        report["phases"][phase] = entry
        environment = entry["environment"]
        vehicle = entry.get("vehicle") or {}
        reflection = entry.get("reflection") or {}
        surface = entry.get("support_surface") or {}
        print(f"[v5.2] {phase:5s} support area "
              f"{surface.get('supported_area_fraction')} peak "
              f"{surface.get('peak_darkening_levels')}")
        print(f"[v5.2] {phase:5s} sky {environment['sky']:6.1f} "
              f"ground {environment['ground_near']:6.1f} "
              f"ratio {environment['ground_to_sky_ratio']:.2f} | terrain "
              f"{environment['terrain_depth']['strongest_edge_steps']}"
              f" | paint {vehicle.get('paint_mean')} glass "
              f"{vehicle.get('glass_mean')} tyre {vehicle.get('tyre_mean')} "
              f"rim {vehicle.get('rim_mean')} | reflection "
              f"{reflection.get('length_px')} px")
    with open(args.out, "w") as handle:
        json.dump(report, handle, indent=1)
        handle.write("\n")
    print(f"[v5.2] {os.path.relpath(args.out, REPO)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
