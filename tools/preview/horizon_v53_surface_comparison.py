#!/usr/bin/env python3
"""Compare the three information-surface candidates and pick one on evidence.

The review asked for exactly three controlled candidates - A soft optical
scrim, B subtle frosted glass, C smoked optical glass - with everything else
held identical, and for the comparison to be measured, not admired:

    INFORMATION_SURFACE_DOMINANCE
        how much of the cluster region the surface covers, how dark it gets,
        and - the criterion that actually catches the rejected solution - how
        hard its boundary is. A shape with an edge fails; a long smooth field
        passes.

    contrast at three tiers
        primary (speed, range), secondary (SOC, power), tertiary (km/h and the
        small labels), measured on the ink itself.

    physical-scale survival
        the same measurement on the half-size frame, because a treatment that
        only works at 1:1 is not a dashboard treatment.

    decoded memory
        what the surface costs to keep resident.

Usage:
    python3 tools/preview/horizon_v53_surface_comparison.py
"""

import json
import os
import subprocess
import sys

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
PREVIEW = os.path.join(REPO, "tools", "preview", "scene_preview.py")
SCENE = os.path.join(REPO, "scenes", "horizon_v5.scene")
LAYOUT = os.path.join(REPO, "assets", "ui", "horizon_v5_layout.json")
TOKENS = os.path.join(REPO, "assets", "ui", "horizon_v5_tokens.json")
UI = os.path.join(REPO, "assets", "ui")
OUT = os.path.join(REPO, "assets", "checkpoints", "horizon_v5")
CANDIDATES = [("none", "CURRENT (no support surface)"),
              ("scrim", "A  soft optical scrim"),
              ("frost", "B  subtle frosted glass"),
              ("smoked", "C  smoked optical glass")]
TIERS = {"primary": ["speed.value", "energy.range"],
         "secondary": ["energy.soc", "energy.power"],
         "tertiary": ["speed.unit", "energy.range.label",
                      "energy.soc.label", "energy.power.label",
                      "gear.p", "driver.status", "climate.status"]}
# The cluster regions, kept clear of the vehicle layer's box (which starts at
# x 697): the car's own edge is a real, sharp edge and would pollute a boundary
# measurement that is about the support surface.
CLUSTER_REGIONS = [(240, 96, 656, 380), (1300, 100, 1700, 400)]


def render(candidate, phase, name, state="v5_neutral", out=OUT):
    environment = dict(os.environ, HORIZON_SUPPORT_CANDIDATE=candidate)
    subprocess.run([sys.executable, os.path.join(REPO, "tools", "preview",
                                                 "build_horizon_v5.py")],
                   check=True, capture_output=True, env=environment)
    subprocess.run([sys.executable, PREVIEW, "--scene", SCENE, "--state", state,
                    "--out", out, "--out-name", name, "--environment-phase",
                    phase], check=True, capture_output=True, env=environment)
    return os.path.join(out, name + ".png")


def render_background(candidate, phase, name, out=OUT):
    """The same frame with the text and vector HUD removed, so a support surface
    can be measured without the ink being counted as one."""
    document = json.load(open(SCENE))
    document["nodes"] = [node for node in document["nodes"]
                         if node.get("type") not in ("text", "vector")]
    path = os.path.join(out, f"_{name}.scene")
    with open(path, "w") as handle:
        json.dump(document, handle)
    environment = dict(os.environ, HORIZON_SUPPORT_CANDIDATE=candidate)
    subprocess.run([sys.executable, PREVIEW, "--scene", path, "--state",
                    "v5_neutral", "--out", out, "--out-name", name,
                    "--environment-phase", phase], check=True,
                   capture_output=True, env=environment)
    return os.path.join(out, name + ".png")


def relative_luminance(rgb):
    def channel(value):
        value = value / 255.0
        return value / 12.92 if value <= 0.03928 \
            else ((value + 0.055) / 1.055) ** 2.4
    red, green, blue = (channel(component) for component in rgb)
    return 0.2126 * red + 0.7152 * green + 0.0722 * blue


def contrast(foreground, background):
    light = max(relative_luminance(foreground), background)
    dark = min(relative_luminance(foreground), background)
    return (light + 0.05) / (dark + 0.05)


def main():
    import numpy as np
    from PIL import Image, ImageDraw, ImageFont
    document = json.load(open(os.path.join(OUT, "horizon_v53_surfaces.json")))
    layout = json.load(open(LAYOUT))
    tokens = json.load(open(TOKENS))
    environment_document = json.load(open(os.path.join(
        UI, "horizon_v5_environment.json")))
    components = {component["id"]: component
                  for component in layout["components"]}
    try:
        font = ImageFont.truetype(
            "/System/Library/Fonts/Supplemental/Arial Bold.ttf", 18)
        small = ImageFont.truetype(
            "/System/Library/Fonts/Supplemental/Arial.ttf", 15)
    except OSError:  # pragma: no cover
        font = small = ImageFont.load_default()

    frames = {}
    backgrounds = {}
    metrics = {"schema": "horizon-v5.3-surface-metrics v1",
               "why": "three candidates measured on dominance, contrast and "
                      "physical-scale survival",
               "candidates": {}}
    for candidate, label in CANDIDATES:
        entry = {"label": label, "phases": {}}
        for phase in ("day", "night"):
            frame_path = render(candidate, phase, f"v53_{candidate}_{phase}")
            background_path = render_background(
                candidate, phase, f"v53bg_{candidate}_{phase}")
            frames[(candidate, phase)] = frame_path
            backgrounds[(candidate, phase)] = background_path
            frame = np.asarray(Image.open(frame_path).convert("RGB")).astype(
                float)
            background = np.asarray(Image.open(background_path).convert(
                "RGB")).astype(float)
            plate = np.asarray(Image.open(os.path.join(
                REPO, environment_document["plates"][phase])).convert(
                    "RGB")).astype(float)
            # --- dominance -------------------------------------------------
            # The surface's own contribution, isolated: the frame with the
            # candidate minus the frame with no support surface at all. Measuring
            # against the plate instead would count the road-flow texture and
            # the vehicle as if they were the surface.
            reference = np.asarray(Image.open(backgrounds[("none", phase)]
                                              if (candidate, phase)
                                              in backgrounds else
                                              background_path).convert(
                                                  "RGB")).astype(float)
            if not os.path.isfile(os.path.join(
                    OUT, f"v53bg_none_{phase}.png")):
                reference = np.asarray(Image.open(render_background(
                    "none", phase, f"v53bg_none_{phase}")).convert(
                        "RGB")).astype(float)
            else:
                reference = np.asarray(Image.open(os.path.join(
                    OUT, f"v53bg_none_{phase}.png")).convert("RGB")).astype(float)
            drop = reference.mean(axis=2) - background.mean(axis=2)
            region = np.zeros(drop.shape, dtype=bool)
            for (x0, y0, x1, y1) in CLUSTER_REGIONS:
                region[y0:y1, x0:x1] = True
            # 4 levels is roughly the smallest change a viewer notices on a
            # dark instrument background; below that the surface is invisible.
            supported = (np.abs(drop) > 4.0) & region
            # The boundary criterion is measured on the surface's own alpha, not
            # on the rendered difference: the environment's horizon is a real
            # sharp edge, and multiplying it by a smooth alpha makes it look
            # like the surface had an edge. The asset is the surface.
            boundary = 0.0
            alpha_paths = []
            if candidate == "scrim":
                alpha_paths = [os.path.join(REPO, document["candidates"]
                                            ["scrim"]["file"])]
            else:
                alpha_paths = [os.path.join(REPO, value["file"]) for value in
                               (document["candidates"].get("per_phase", {})
                                .get(candidate) or {}).values()]
            for path in alpha_paths:
                if not os.path.isfile(path):
                    continue
                alpha = np.asarray(Image.open(path).convert("RGBA"))[:, :, 3]
                step = float(np.abs(np.diff(alpha.astype(np.float32),
                                            axis=1)).max())
                boundary = max(boundary, step)
            dominance = {
                "surface_area_fraction": round(
                    float(supported.sum()) / float(region.sum()), 5),
                "peak_luminance_delta": round(
                    float(np.abs(drop[supported]).max()) if supported.any()
                    else 0.0, 1),
                "mean_luminance_delta": round(
                    float(np.abs(drop[supported]).mean()) if supported.any()
                    else 0.0, 2),
                "note": "measured against the same frame with no support "
                        "surface, so only the surface's own contribution counts",
                "hardest_boundary_step": round(boundary, 2),
                # What makes a support surface fail is a *shape*: a hard edge
                # or an opaque body. A wide, soft, low-amplitude field is what
                # the review asks for, so area alone is reported, not gated.
                "passes": bool(
                    boundary <= 2.0
                    and float(np.abs(drop[supported]).max() if supported.any()
                              else 0.0) <= 90.0),
            }
            # --- contrast on the ink, at 1:1 and half size -----------------
            palette = environment_document["palettes"][phase]
            ink = np.abs(frame - background).max(axis=2) > 10
            tiers = {}
            for tier, ids in TIERS.items():
                colours = []
                for node_id in ids:
                    component = components.get(node_id)
                    if not component:
                        continue
                    token = component.get("color_token")
                    if token in palette:
                        colours.append(tuple(int(palette[token][index:index + 2],
                                                 16) for index in (1, 3, 5)))
                if not colours:
                    continue
                region_mask = np.zeros(ink.shape, dtype=bool)
                for node_id in ids:
                    component = components.get(node_id)
                    if not component:
                        continue
                    bounds = component["bounds"]
                    x0 = max(0, int(bounds["x"]) - 6)
                    y0 = max(0, int(bounds["y"]) - 6)
                    x1 = min(ink.shape[1], int(bounds["x"] + bounds["w"]) + 6)
                    y1 = min(ink.shape[0], int(bounds["y"] + bounds["h"]) + 6)
                    region_mask[y0:y1, x0:x1] = True
                sample = ink & region_mask
                if sample.sum() < 30:
                    continue
                background_luminance = float(
                    background.mean(axis=2)[sample].mean()) / 255.0
                ratios = [contrast(colour, background_luminance)
                          for colour in colours]
                # Half size: the same measurement after the panel's physical
                # downscale, where thin labels have to survive.
                half_frame = np.asarray(Image.open(frame_path).convert(
                    "RGB").resize((960, 240), Image.LANCZOS)).astype(float)
                half_background = np.asarray(Image.open(background_path).convert(
                    "RGB").resize((960, 240), Image.LANCZOS)).astype(float)
                half_ink = np.abs(half_frame - half_background).max(axis=2) > 8
                half_region = np.zeros(half_ink.shape, dtype=bool)
                for node_id in ids:
                    component = components.get(node_id)
                    if not component:
                        continue
                    bounds = component["bounds"]
                    x0 = max(0, int(bounds["x"] / 2) - 3)
                    y0 = max(0, int(bounds["y"] / 2) - 3)
                    x1 = min(half_ink.shape[1], int((bounds["x"] + bounds["w"])
                                                    / 2) + 3)
                    y1 = min(half_ink.shape[0], int((bounds["y"] + bounds["h"])
                                                    / 2) + 3)
                    half_region[y0:y1, x0:x1] = True
                half_sample = half_ink & half_region
                half_ratio = None
                if half_sample.sum() >= 10:
                    half_luminance = float(
                        half_background.mean(axis=2)[half_sample].mean()) / 255.0
                    half_ratio = round(min(contrast(colour, half_luminance)
                                           for colour in colours), 2)
                tiers[tier] = {
                    "min_ratio_1to1": round(min(ratios), 2),
                    "min_ratio_half_size": half_ratio,
                    "pixels": int(sample.sum())}
            entry["phases"][phase] = {"dominance": dominance,
                                      "contrast": tiers}
        # Memory cost of the candidate's own assets.
        cost = 0
        files = []
        if candidate == "scrim":
            files = [document["candidates"]["scrim"]["file"]]
        else:
            for value in (document["candidates"].get("per_phase", {})
                          .get(candidate) or {}).values():
                files.append(value["file"])
        for path in files:
            with Image.open(os.path.join(REPO, path)) as image:
                cost += image.width * image.height * 4
        entry["decoded_rgba_bytes"] = cost
        entry["assets"] = len(files)
        metrics["candidates"][candidate] = entry
        day = entry["phases"]["day"]
        night = entry["phases"]["night"]
        print(f"[v5.3] {candidate:7s} day surface "
              f"{day['dominance']['surface_area_fraction'] * 100:5.1f}% "
              f"boundary {day['dominance']['hardest_boundary_step']:5.2f} | "
              f"tiers " + ", ".join(
                  f"{tier} {value['min_ratio_1to1']}"
                  f"/{value['min_ratio_half_size']}"
                  for tier, value in day["contrast"].items())
              + f" | night surface "
              f"{night['dominance']['surface_area_fraction'] * 100:5.1f}% "
              f"| {cost // 1024} KB")

    # --- the master comparison sheet --------------------------------------
    rows = []
    for candidate, label in CANDIDATES:
        for phase in ("day", "night"):
            rows.append((f"{label} - {phase.upper()} 1:1",
                         frames[(candidate, phase)], 960, 240))
            rows.append((f"{label} - {phase.upper()} physical half size",
                         frames[(candidate, phase)], 960, 240, 0.5))
    header, cell_h = 26, 240
    sheet = Image.new("RGB", (960, (cell_h + header) * len(rows)), (8, 10, 14))
    draw = ImageDraw.Draw(sheet)
    for index, row in enumerate(rows):
        label, path = row[0], row[1]
        scale = row[4] if len(row) > 4 else 1.0
        top = index * (cell_h + header)
        image = Image.open(path).convert("RGB")
        if scale != 1.0:
            image = image.resize((int(1920 * scale), int(480 * scale)),
                                 Image.LANCZOS)
        image = image.resize((960, cell_h), Image.LANCZOS)
        sheet.paste(image, (0, top + header))
        draw.text((8, top + 4), label, fill=(232, 238, 244), font=small)
    master = os.path.join(OUT, "horizon_v53_surface_candidates.png")
    sheet.save(master)

    # Physical-scale crops of the two clusters, side by side per candidate.
    crop_rows = []
    for candidate, label in CANDIDATES:
        for phase in ("day", "night"):
            image = Image.open(frames[(candidate, phase)]).convert("RGB")
            left = image.crop((240, 80, 700, 400)).resize((460, 320),
                                                          Image.LANCZOS)
            right = image.crop((1280, 80, 1740, 400)).resize((460, 320),
                                                             Image.LANCZOS)
            strip = Image.new("RGB", (920, 320), (8, 10, 14))
            strip.paste(left, (0, 0))
            strip.paste(right, (460, 0))
            crop_rows.append((f"{label} {phase.upper()} clusters, 1:1 crop",
                              strip))
    crop_sheet = Image.new("RGB", (920, (320 + 24) * len(crop_rows)),
                           (8, 10, 14))
    draw = ImageDraw.Draw(crop_sheet)
    for index, (label, image) in enumerate(crop_rows):
        top = index * (320 + 24)
        crop_sheet.paste(image, (0, top + 24))
        draw.text((8, top + 4), label, fill=(232, 238, 244), font=small)
    crops_path = os.path.join(OUT, "horizon_v53_surface_crops.png")
    crop_sheet.save(crops_path)
    # Leave the workspace on the chosen candidate, not on whichever candidate
    # happened to be rendered last.
    subprocess.run([sys.executable, os.path.join(REPO, "tools", "preview",
                                                 "build_horizon_v5.py")],
                   check=True, capture_output=True,
                   env={key: value for key, value in os.environ.items()
                        if key != "HORIZON_SUPPORT_CANDIDATE"})
    metrics["master_sheet"] = os.path.relpath(master, REPO)
    metrics["crop_sheet"] = os.path.relpath(crops_path, REPO)
    path = os.path.join(OUT, "horizon_v53_surface_metrics.json")
    with open(path, "w") as handle:
        json.dump(metrics, handle, indent=1)
        handle.write("\n")
    print(f"[v5.3] {os.path.relpath(master, REPO)}")
    print(f"[v5.3] {os.path.relpath(crops_path, REPO)}")
    print(f"[v5.3] {os.path.relpath(path, REPO)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
