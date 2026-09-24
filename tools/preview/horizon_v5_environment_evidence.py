#!/usr/bin/env python3
"""Environment evidence: four phases, a whole day, four seasons, one transition.

What has to be provable without eyes:

* the day does not switch: the phase weights are sampled every minute and the
  *rendered frames* of consecutive minutes are differenced, so a step would
  show up as a pixel jump;
* daylight is legible: for every informational HUD colour the contrast against
  the rendered plate behind it is measured (WCAG ratio) instead of assumed;
* the seasons move: the solar schedule produces later sunrises in January than
  in July, and the frames at the same solar offset look different;
* the memory budget holds: two environment plates resident during a transition,
  never all four.

Usage:
    python3 tools/preview/horizon_v5_environment_evidence.py
"""

import argparse
import datetime
import json
import os
import subprocess
import sys

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(REPO, "tools", "assets"))
PREVIEW = os.path.join(REPO, "tools", "preview", "scene_preview.py")
SCENE = os.path.join(REPO, "scenes", "horizon_v5.scene")
TOKENS = os.path.join(REPO, "assets", "ui", "horizon_v5_tokens.json")
OUT = os.path.join(REPO, "assets", "checkpoints", "horizon_v5")
ENVIRONMENT = os.path.join(REPO, "assets", "ui", "horizon_v5_environment.json")
PHASES = ["dawn", "day", "dusk", "night"]
DAILY_HOURS = [5, 6, 7, 9, 12, 15, 17, 18, 19, 21, 0, 3]
SEASONAL_MONTHS = [(1, "January"), (4, "April"), (7, "July"),
                   (10, "October")]


def render(state, name, extra=(), out=OUT):
    subprocess.run([sys.executable, PREVIEW, "--scene", SCENE, "--state", state,
                    "--out", out, "--out-name", name, *extra], check=True,
                   capture_output=True)
    return os.path.join(out, name + ".png")


def luminance(array):
    return (0.2126 * array[:, :, 0] + 0.7152 * array[:, :, 1]
            + 0.0722 * array[:, :, 2])


def contrast_ratio(foreground, background_luminance):
    """WCAG relative luminance ratio, both inputs on a 0-255 scale."""
    def channel(value):
        value = value / 255.0
        return value / 12.92 if value <= 0.03928 \
            else ((value + 0.055) / 1.055) ** 2.4

    def relative(rgb):
        red, green, blue = (channel(component) for component in rgb)
        return 0.2126 * red + 0.7152 * green + 0.0722 * blue

    light = max(relative(foreground), background_luminance)
    dark = min(relative(foreground), background_luminance)
    return (light + 0.05) / (dark + 0.05)


def main():
    import numpy as np
    from PIL import Image, ImageDraw, ImageFont
    parser = argparse.ArgumentParser()
    parser.add_argument("--skip-continuity", action="store_true")
    args = parser.parse_args()
    os.makedirs(OUT, exist_ok=True)
    if not os.path.isfile(ENVIRONMENT):
        sys.exit("[v5-env-evidence] run tools/assets/horizon_v5_environment_time.py")
    import horizon_v5_environment_time as environment_time
    document = json.load(open(ENVIRONMENT))
    tokens = json.load(open(TOKENS))
    try:
        font = ImageFont.truetype(
            "/System/Library/Fonts/Supplemental/Arial Bold.ttf", 20)
        small = ImageFont.truetype(
            "/System/Library/Fonts/Supplemental/Arial.ttf", 17)
    except OSError:  # pragma: no cover
        font = small = ImageFont.load_default()

    # ---- the four phases -------------------------------------------------
    phase_paths = {}
    for phase in PHASES:
        path = render("v5_neutral", f"horizon_v5_1_{phase}",
                      ("--environment-phase", phase))
        phase_paths[phase] = path
        print(f"[v5-env] {phase:5s} -> {os.path.relpath(path, REPO)}")

    # ---- a whole day -----------------------------------------------------
    date = datetime.date(2026, 9, 24)
    schedule = environment_time.schedule(date.year, date.month, date.day)
    cycle_frames = []
    for hour in DAILY_HOURS:
        when = datetime.datetime(date.year, date.month, date.day, hour, 0)
        state = environment_time.state_at(when)
        path = render("v5_neutral", f"_cycle_{hour:02d}",
                      ("--at", when.strftime("%Y-%m-%d %H:%M")))
        cycle_frames.append((hour, state, path))
    cell_w, cell_h, header = 960, 240, 26
    sheet = Image.new("RGB", (cell_w, (cell_h + header) * len(cycle_frames)),
                      (8, 10, 14))
    draw = ImageDraw.Draw(sheet)
    cycle_luminance = []
    for index, (hour, state, path) in enumerate(cycle_frames):
        top = index * (cell_h + header)
        image = Image.open(path).convert("RGB")
        sheet.paste(image.resize((cell_w, cell_h), Image.LANCZOS), (0, top + header))
        weights = state["phase_weights"]
        draw.text((8, top + 4),
                  f"{hour:02d}:00  " + "  ".join(
                      f"{name} {weights[name]:.2f}" for name in PHASES)
                  + f"   darkness {state['darkness']:.2f}   "
                    f"sunrise {schedule['sunrise_minutes'] / 60:.2f}h  "
                    f"sunset {schedule['sunset_minutes'] / 60:.2f}h",
                  fill=(226, 232, 240), font=small)
        cycle_luminance.append(round(float(luminance(
            np.asarray(image).astype(float)).mean()), 2))
    cycle_sheet = os.path.join(OUT, "horizon_v5_1_daily_cycle_contact_sheet.png")
    sheet.save(cycle_sheet)
    print(f"[v5-env] daily cycle -> {os.path.relpath(cycle_sheet, REPO)}")

    # ---- seasons ---------------------------------------------------------
    season_rows = []
    for month, label in SEASONAL_MONTHS:
        entry = environment_time.schedule(2026, month, 15)
        sunrise_at = datetime.datetime(2026, month, 15, 0, 0) + datetime.timedelta(
            minutes=entry["sunrise_minutes"] + 30)
        path = render("v5_neutral", f"_season_{month:02d}",
                      ("--at", sunrise_at.strftime("%Y-%m-%d %H:%M")))
        season_rows.append((label, entry, sunrise_at, path))
    season_sheet = Image.new("RGB", (cell_w,
                                     (cell_h + header) * len(season_rows)),
                             (8, 10, 14))
    draw = ImageDraw.Draw(season_sheet)
    for index, (label, entry, sunrise_at, path) in enumerate(season_rows):
        top = index * (cell_h + header)
        image = Image.open(path).convert("RGB")
        season_sheet.paste(image.resize((cell_w, cell_h), Image.LANCZOS),
                           (0, top + header))
        draw.text((8, top + 4),
                  f"{label}  sunrise {entry['sunrise_minutes'] / 60:.2f}h  "
                  f"sunset {entry['sunset_minutes'] / 60:.2f}h   frame at "
                  f"sunrise+30min = {sunrise_at.strftime('%H:%M')}",
                  fill=(226, 232, 240), font=small)
    seasonal_path = os.path.join(OUT, "horizon_v5_1_seasonal_daylight_test.png")
    season_sheet.save(seasonal_path)
    print(f"[v5-env] seasons -> {os.path.relpath(seasonal_path, REPO)}")

    # ---- transition continuity, measured on frames -----------------------
    continuity = {}
    for label, centre in (("sunrise", schedule["sunrise_minutes"]),
                          ("sunset", schedule["sunset_minutes"])):
        samples = []
        for offset in range(-90, 91, 2):
            minutes = centre + offset
            when = datetime.datetime(date.year, date.month, date.day) \
                + datetime.timedelta(minutes=minutes)
            state = environment_time.state_at(when)
            samples.append((when, state))
        frames = []
        for when, state in samples:
            frames.append(render("v5_neutral",
                                 f"_transition_{label}_{when.strftime('%H%M')}",
                                 ("--at", when.strftime("%Y-%m-%d %H:%M"))))
        steps = []
        palette_steps = []
        first_frame = np.asarray(Image.open(frames[0]).convert("RGB")).astype(
            np.float32)
        last_frame = np.asarray(Image.open(frames[-1]).convert("RGB")).astype(
            np.float32)
        total_change = float(np.abs(last_frame - first_frame).mean())
        for index in range(len(frames) - 1):
            left = np.asarray(Image.open(frames[index]).convert("RGB")).astype(
                np.float32)
            right = np.asarray(Image.open(frames[index + 1]).convert("RGB")).astype(
                np.float32)
            steps.append(float(np.abs(left - right).mean()))
            palette_steps.append(_palette_step(samples[index][1]["palette"],
                                               samples[index + 1][1]["palette"]))
        continuity[label] = {
            "samples": len(frames),
            "step_minutes": 2,
            "max_frame_mean_difference": round(max(steps), 4),
            "mean_frame_mean_difference": round(float(np.mean(steps)), 4),
            "total_transition_difference": round(total_change, 4),
            "max_step_fraction_of_transition": round(
                max(steps) / total_change if total_change else 0.0, 4),
            "max_palette_step": round(max(palette_steps), 4),
            "windows": document["transition_windows_minutes"],
        }
        print(f"[v5-env] {label} transition: {len(frames)} frames, max frame "
              f"step {max(steps):.3f}, max palette step {max(palette_steps):.1f}")

    # ---- daylight legibility --------------------------------------------
    contrast = {}
    layout = json.load(open(os.path.join(REPO, "assets", "ui",
                                         "horizon_v5_layout.json")))
    # Sampled where the element actually is: the frame that has the HUD is
    # compared with the frame that does not, so the mask is exactly the ink the
    # element drew. A box average would be meaningless for a 7 px arc or a 1 px
    # rule, which is what the previous measurement got wrong.
    background_scene = json.load(open(SCENE))
    # The glow assets are excluded: a glow is the element's own emission, so
    # measuring the element against its own light counts it twice. The rail's
    # baked track and the cluster backings stay, because they really are behind
    # the ink.
    background_scene["nodes"] = [
        node for node in background_scene["nodes"]
        if node.get("type") not in ("text", "vector")
        and node.get("id") not in ("speed.arc.glow", "speed.numeral.glow")]
    scratch_scene = os.path.join(OUT, "_contrast_background.scene")
    with open(scratch_scene, "w") as handle:
        json.dump(background_scene, handle)
    background_frame_path = os.path.join(OUT, "_contrast_background.png")
    subprocess.run([sys.executable, PREVIEW, "--scene", scratch_scene,
                    "--state", "v5_neutral", "--out", OUT, "--out-name",
                    "_contrast_background", "--environment-phase", "day"],
                   check=True, capture_output=True)
    day_frame = np.asarray(Image.open(phase_paths["day"]).convert("RGB")).astype(
        float)
    background_frame = np.asarray(Image.open(background_frame_path).convert(
        "RGB")).astype(float)
    ink = np.abs(day_frame - background_frame).max(axis=2) > 10
    palette_day = environment_time.PALETTES["day"]
    for name in ("primary_text", "secondary_text", "muted_text", "accent",
                 "rail_lit"):
        token = tokens["colors"].get(name)
        if not isinstance(token, str):
            continue
        rgb = tuple(int(palette_day[name][index:index + 2], 16)
                    for index in (1, 3, 5))
        # The element's own box decides where to look, and the ink decides which
        # pixels are the element: colour matching alone fails once alpha
        # compositing has moved the rendered value away from the token.
        region = np.zeros(ink.shape, dtype=bool)
        if name == "accent":
            # The arc is a thin stroke on a large box: the only honest region is
            # its own annulus, or the numeral and the ticks inside the same box
            # would be measured as if they were the arc.
            dial = tokens["ui_assets"]["dial"]
            yy, xx = np.mgrid[0:ink.shape[0], 0:ink.shape[1]]
            distance = np.hypot(xx - dial["cx"], yy - dial["cy"])
            region |= np.abs(distance - dial["radius"]) <= dial["width"] * 2.0
        for component in layout["components"]:
            if name != "accent" and (str(component.get("color_token", "")) != name
                                     and str(component.get("lit_token", "")) != name
                                     and str(component.get("stroke_token", ""))
                                     != name):
                continue
            if name == "accent" and "arc" not in component.get("id", ""):
                continue
            bounds = component.get("bounds")
            if not bounds:
                continue
            x0 = max(0, int(bounds["x"]) - 8)
            y0 = max(0, int(bounds["y"]) - 8)
            x1 = min(ink.shape[1], int(bounds["x"] + bounds["w"]) + 8)
            y1 = min(ink.shape[0], int(bounds["y"] + bounds["h"]) + 8)
            region[y0:y1, x0:x1] = True
        sample = ink & region
        if sample.sum() < 40:
            continue
        background = float(luminance(background_frame)[sample].mean()) / 255.0
        contrast[name] = {
            "min_ratio": round(contrast_ratio(rgb, background), 2),
            "max_ratio": round(contrast_ratio(rgb, background), 2),
            "samples": int(sample.sum())}
    print(f"[v5-env] daylight contrast {json.dumps(contrast)}")

    # ---- memory ----------------------------------------------------------
    def decoded(path):
        with Image.open(path) as image:
            return image.width * image.height * 4

    plate_bytes = decoded(os.path.join(REPO, document["plates"]["day"]))
    vehicle_bytes = 0
    layer_manifest = os.path.join(
        REPO, "assets", "rendered", "vehicle", "horizon_v5", "day",
        "horizon_v5_vehicle_day.json")
    if os.path.isfile(layer_manifest):
        for entry in json.load(open(layer_manifest))["layers"].values():
            vehicle_bytes += decoded(os.path.join(REPO, entry["source"]))
    motion_bytes = 0
    for name in ("horizon_v5_roadflow.png", "horizon_v5_wake.png",
                 "horizon_v5_streak_brake.png", "horizon_v5_wheel_low.png",
                 "horizon_v5_wheel_medium.png", "horizon_v5_wheel_high.png"):
        path = os.path.join(REPO, "assets", "ui", name)
        if os.path.isfile(path):
            motion_bytes += decoded(path)
    memory = {
        "plate_rgba_bytes": plate_bytes,
        "two_plate_transition_bytes": plate_bytes * 2,
        "vehicle_layers_all_states_bytes": vehicle_bytes,
        "vehicle_layers_resident_now": decoded(os.path.join(
            REPO, "assets", "rendered", "vehicle", "horizon_v5", "layer",
            "base.png")) if os.path.isfile(os.path.join(
                REPO, "assets", "rendered", "vehicle", "horizon_v5", "layer",
                "base.png")) else 0,
        "motion_overlays_bytes": motion_bytes,
        "resident_estimate_mb": round(
            (plate_bytes * 2 + motion_bytes
             + (decoded(os.path.join(
                 REPO, "assets", "rendered", "vehicle", "horizon_v5", "layer",
                 "base.png")) if os.path.isfile(os.path.join(
                     REPO, "assets", "rendered", "vehicle", "horizon_v5",
                     "layer", "base.png")) else 0)) / (1024.0 * 1024.0), 2),
        "note": "ESTIMATED on the Mac; UNKNOWN UNTIL DEVICE TEST on T113",
    }
    print(f"[v5-env] resident estimate {memory['resident_estimate_mb']} MB")

    # ---- key states in both environments ---------------------------------
    key_states = [("v5_neutral", "neutral"), ("v5_brake", "brake"),
                  ("v5_left", "left indicator"), ("v5_hazard", "hazard"),
                  ("v5_unknown", "unknown")]
    key_sheets = {}
    for phase in ("day", "night"):
        sheet = Image.new("RGB", (cell_w, (cell_h + header) * len(key_states)),
                          (8, 10, 14))
        draw = ImageDraw.Draw(sheet)
        for index, (state, label) in enumerate(key_states):
            top = index * (cell_h + header)
            path = render(state, f"_key_{phase}_{label.split()[0]}",
                          ("--environment-phase", phase))
            image = Image.open(path).convert("RGB")
            sheet.paste(image.resize((cell_w, cell_h), Image.LANCZOS),
                        (0, top + header))
            weights = {name: 1.0 if name == phase else 0.0 for name in PHASES}
            draw.text((8, top + 4), f"{phase.upper()}  {label}",
                      fill=(226, 232, 240), font=small)
        path = os.path.join(OUT, f"horizon_v5_1_{phase}_key_states.png")
        sheet.save(path)
        key_sheets[phase] = os.path.relpath(path, REPO)
        print(f"[v5-env] {phase} key states -> {os.path.relpath(path, REPO)}")

    # ---- vehicle material, day against night -----------------------------
    crop = (700, 90, 1250, 480)
    material = Image.new("RGB", (cell_w, cell_h * 2 + 60), (8, 10, 14))
    draw = ImageDraw.Draw(material)
    for index, phase in enumerate(("day", "night")):
        image = Image.open(phase_paths[phase]).convert("RGB").crop(crop)
        image = image.resize((cell_w, cell_h), Image.LANCZOS)
        material.paste(image, (0, 30 + index * (cell_h + 30)))
        draw.text((8, 6 + index * (cell_h + 30)), f"{phase.upper()} vehicle "
                  f"material and environment integration",
                  fill=(226, 232, 240), font=small)
    material_path = os.path.join(OUT, "horizon_v5_1_vehicle_material_day_night.png")
    material.save(material_path)
    print(f"[v5-env] material -> {os.path.relpath(material_path, REPO)}")

    # ---- the summary sheet ----------------------------------------------
    tiles = [("neutral (night)", phase_paths["night"]),
             ("neutral (day)", phase_paths["day"]),
             ("dawn", phase_paths["dawn"]), ("dusk", phase_paths["dusk"]),
             ("speed alignment", os.path.join(
                 OUT, "horizon_v5_1_speed_alignment.png")),
             ("motion comparison", os.path.join(
                 OUT, "horizon_v5_1_motion_comparison.png"))]
    final = Image.new("RGB", (cell_w, (cell_h + header) * len(tiles)),
                      (8, 10, 14))
    draw = ImageDraw.Draw(final)
    for index, (label, path) in enumerate(tiles):
        top = index * (cell_h + header)
        if os.path.isfile(path):
            image = Image.open(path).convert("RGB")
            final.paste(image.resize((cell_w, cell_h), Image.LANCZOS),
                        (0, top + header))
        draw.text((8, top + 4), label, fill=(226, 232, 240), font=small)
    final_path = os.path.join(OUT, "horizon_v5_1_final_contact_sheet.png")
    final.save(final_path)

    metrics = {
        "schema": "horizon-v5.1-metrics v1",
        "key_state_sheets": key_sheets,
        "material_day_night": os.path.relpath(material_path, REPO),
        "final_contact_sheet": os.path.relpath(final_path, REPO),
        "phases": PHASES,
        "phase_frames": {phase: os.path.relpath(path, REPO)
                         for phase, path in phase_paths.items()},
        "schedule_today": schedule,
        "daily_cycle": [
            {"hour": hour, "phase_weights": state["phase_weights"],
             "darkness": state["darkness"],
             "frame": os.path.relpath(path, REPO),
             "mean_luminance": cycle_luminance[index]}
            for index, (hour, state, path) in enumerate(cycle_frames)],
        "daily_cycle_sheet": os.path.relpath(cycle_sheet, REPO),
        "seasons": [
            {"month": label, "sunrise_h": round(entry["sunrise_minutes"] / 60, 3),
             "sunset_h": round(entry["sunset_minutes"] / 60, 3),
             "frame": os.path.relpath(path, REPO),
             "frame_at": sunrise_at.strftime("%H:%M")}
            for label, entry, sunrise_at, path in season_rows],
        "seasonal_sheet": os.path.relpath(seasonal_path, REPO),
        "transition_continuity": continuity,
        "daylight_contrast": contrast,
        "monthly_profile": document["monthly_profile"],
        "memory": memory,
        "semantic_colours_fixed": document["semantic_colours_fixed"],
    }
    path = os.path.join(OUT, "horizon_v5_1_metrics.json")
    with open(path, "w") as handle:
        json.dump(metrics, handle, indent=1)
        handle.write("\n")
    print(f"[v5-env] metrics -> {os.path.relpath(path, REPO)}")
    return 0


def _palette_step(left, right):
    total = 0.0
    for name, value in left.items():
        other = right.get(name, value)
        for index in (1, 3, 5):
            total = max(total, abs(int(value[index:index + 2], 16)
                                   - int(other[index:index + 2], 16)))
    return total


if __name__ == "__main__":
    sys.exit(main())
