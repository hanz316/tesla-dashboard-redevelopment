#!/usr/bin/env python3
"""Presentation-scale QA for the taillight freeze: 600 px and Horizon.

Runs on the host interpreter (Pillow + numpy), not inside Blender, following
the same split as the other asset builders: Blender renders, this composes and
measures.

Inputs : <out-dir>/state_<STATE>.png  (1100x760 RGBA, frozen camera/lighting)
         <out-dir>/freeze_render_manifest.json  (render paths + lamp bbox)
Outputs: state_<state>_600px.png, horizon_state_<state>.png,
         state_<state>_horizon1to1.png, presentation_report.json

The Horizon frame is the real 1920x480 composition with the vehicle at its
intended size (700x401 at 610,40), using a committed Horizon scene - the same
rule the rest of the asset pipeline uses.
"""

import json
import hashlib
import os
import subprocess
import sys

try:
    import numpy as np
    from PIL import Image
except ImportError:  # pragma: no cover
    sys.exit("Pillow and numpy are required")

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
HORIZON_SCENE = os.path.join(REPO_ROOT, "scenes", "horizon_redesign_a.scene")
HORIZON_STATE = "normal_drive"
HORIZON_BOX = "700x401@610,40"
HORIZON_CROP = (510, 0, 1410, 480)
PREVIEWER = os.path.join(REPO_ROOT, "tools", "preview", "scene_preview.py")
STATES = ["OFF", "BRAKE", "LEFT_INDICATOR", "RIGHT_INDICATOR", "HAZARD",
          "HEADLIGHT"]
# At production scale the lamps are a few dozen pixels: the criterion is the
# share of the lamp region that changes visibly, not a mean over the region
# (which is diluted by the reflector and housing that share the silhouette).
LIT_MIN = 0.05
VISIBLE_DELTA = 0.05
# A state must change at least this share of a lamp's own projected silhouette
# at the presentation scale to count as reading there.
MIN_CHANGE_FRACTION = 0.25
# A lamp that was not told to light up measures 0.0 changed pixels in a
# deterministic render, so "quiet" is a hard zero plus a small allowance for
# resampling at the composite scale.
QUIET_MAX = 0.01


def parse_args():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--manifest",
                    default=None,
                    help="defaults to <out-dir>/freeze_render_manifest.json")
    return ap.parse_args()


def to_vehicle_600(src, dst):
    img = Image.open(src).convert("RGBA")
    bbox = img.getchannel("A").getbbox()
    width = (bbox[2] - bbox[0]) if bbox else img.width
    scale = 600.0 / max(1, width)
    img.resize((max(1, int(img.width * scale)), max(1, int(img.height * scale))),
               Image.LANCZOS).save(dst)
    return dst


def horizon_composite(src, out_dir, key):
    name = f"horizon_state_{key}"
    subprocess.run(
        [sys.executable, PREVIEWER, "--scene", HORIZON_SCENE,
         "--state", HORIZON_STATE, "--vehicle-image", src, "--vehicle-crop",
         "--vehicle-box", HORIZON_BOX, "--out-name", name, "--out", out_dir],
        check=True, capture_output=True)
    full = os.path.join(out_dir, name + ".png")
    crop = os.path.join(out_dir, f"state_{key}_horizon1to1.png")
    Image.open(full).convert("RGB").crop(HORIZON_CROP).save(crop)
    return full, crop


def load_rgb(path):
    return np.asarray(Image.open(path).convert("RGB"),
                      dtype=np.float32) / 255.0


def digest(path):
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()[:16]


def project_bbox(lamp_bbox, render_size, render_alpha, target_alpha):
    """Map the render's lamp bbox into a composite through the vehicle bbox.

    The compositor scales the vehicle's alpha bounding box into a known box, so
    the mapping is a scale+translate between the two alpha boxes - no
    assumption about canvas sizes. A change-detection region was tried first
    and is contaminated by the light the lamps throw onto the bodywork: the
    changed-pixel bounding box grew to most of the car.

    `lamp_bbox` comes from Blender's pixel buffer, whose rows run bottom-up;
    both alpha boxes are in PIL's top-down coordinates.
    """
    rx0, ry0, rx1, ry1 = render_alpha          # top-down
    tx0, ty0, tx1, ty1 = target_alpha
    sx = (tx1 - tx0) / float(max(1, rx1 - rx0))
    sy = (ty1 - ty0) / float(max(1, ry1 - ry0))
    height = render_size[1]
    x0 = int(tx0 + (lamp_bbox[0] - rx0) * sx)
    x1 = int(tx0 + (lamp_bbox[2] - rx0) * sx)
    # Blender's rows run bottom-up, PIL's top-down.
    y0 = int(ty0 + ((height - lamp_bbox[3]) - ry0) * sy)
    y1 = int(ty0 + ((height - lamp_bbox[1]) - ry0) * sy)
    return [x0, y0, x1, y1]


def measure(path, region, baseline=None):
    """Red/amber energy over the taillight region at this scale.

    With a baseline (OFF) the same change-based metrics used inside Blender are
    produced here: the share of region pixels that changed visibly, and the
    mean signed change. Those survive downscaling; a whole-region mean does not.
    """
    img = load_rgb(path)
    if region is None:
        return {"pixels": 0, "red": 0.0, "amber": 0.0}
    x0, y0, x1, y1 = region
    sel = img[y0:y1, x0:x1, :]
    if sel.size == 0:
        return {"pixels": 0, "red": 0.0, "amber": 0.0}
    out = {"pixels": int(sel.shape[0] * sel.shape[1]),
           "red": round(float(sel[:, :, 0].mean()), 5),
           "amber": round(float((0.5 * sel[:, :, 0]
                                 + 0.5 * sel[:, :, 1]).mean()), 5),
           "region_xy": [x0, y0, x1, y1],
           "image": os.path.basename(path)}
    if baseline is not None:
        base = baseline[y0:y1, x0:x1, :]
        dr = sel[:, :, 0] - base[:, :, 0]
        da = (0.5 * (sel[:, :, 0] + sel[:, :, 1])
              - 0.5 * (base[:, :, 0] + base[:, :, 1]))
        out.update({
            "lit_fraction": round(float((dr > VISIBLE_DELTA).mean()), 5),
            "amber_lit_fraction": round(float((da > VISIBLE_DELTA).mean()), 5),
            "mean_delta_x": round(float(dr.mean()), 6),
            "p95_delta": round(float(np.percentile(dr, 95)), 5),
            "visible_delta_threshold": VISIBLE_DELTA})
    return out


def silhouette_px(render_mask_px, render_size, alpha_bbox, target_width):
    """A lamp's projected area at a composite scale, from its render mask."""
    ax0, _ay0, ax1, _ay1 = alpha_bbox
    scale = target_width / float(max(1, ax1 - ax0))
    return render_mask_px * scale * scale


def verdicts(per_state):
    by = {s["state"]: s for s in per_state}
    out = {}
    # A lamp's own area shrinks with the square of the composite scale, so the
    # criterion at production scale is an absolute pixel count derived from
    # that lamp's own silhouette at that scale - a fraction of a bounding box is
    # diluted by every part of the box the lamp does not occupy, which is why
    # the long thin brake lamp measured 2 % of its own box while a third of the
    # inner lamp changed.
    for scale, label in (("600px", "600px"), ("horizon", "horizon")):
        def changed(state, name, key="lit_fraction"):
            m = by[state]["lamp_measures"][scale].get(name, {})
            return m.get(key, 0.0) * m.get("pixels", 0)

        def area(name):
            return by["OFF"]["lamp_measures"][scale].get(name, {}).get(
                "lamp_silhouette_px", 0)

        def rule(min_fraction):
            return (f"at least {min_fraction:.0%} of that lamp's own projected "
                    f"silhouette changes at this scale")

        fl = MIN_CHANGE_FRACTION
        out[f"{label}_brake_lamp_lit"] = {
            "pass": (changed("BRAKE", "rear_lights") >= fl * area("rear_lights")
                     and changed("BRAKE", "light_breake")
                     >= fl * area("light_breake")),
            "outer_lamp_changed_px": round(changed("BRAKE", "rear_lights"), 1),
            "outer_lamp_silhouette_px": round(area("rear_lights"), 1),
            "brake_lamp_changed_px": round(changed("BRAKE", "light_breake"), 1),
            "brake_lamp_silhouette_px": round(area("light_breake"), 1),
            "rule": rule(fl)}
        out[f"{label}_indicator_one_sided"] = {
            "pass": (changed("LEFT_INDICATOR", "rear_lightsl",
                             "amber_lit_fraction")
                     >= fl * area("rear_lightsl")
                     and changed("LEFT_INDICATOR", "rear_lightsr",
                                 "amber_lit_fraction")
                     <= QUIET_MAX * area("rear_lightsr")
                     and changed("RIGHT_INDICATOR", "rear_lightsr",
                                 "amber_lit_fraction")
                     >= fl * area("rear_lightsr")
                     and changed("RIGHT_INDICATOR", "rear_lightsl",
                                 "amber_lit_fraction")
                     <= QUIET_MAX * area("rear_lightsl")),
            "left_lamp_in_LEFT_px": round(changed(
                "LEFT_INDICATOR", "rear_lightsl", "amber_lit_fraction"), 1),
            "right_lamp_in_LEFT_px": round(changed(
                "LEFT_INDICATOR", "rear_lightsr", "amber_lit_fraction"), 1),
            "right_lamp_in_RIGHT_px": round(changed(
                "RIGHT_INDICATOR", "rear_lightsr", "amber_lit_fraction"), 1),
            "left_lamp_in_RIGHT_px": round(changed(
                "RIGHT_INDICATOR", "rear_lightsl", "amber_lit_fraction"), 1),
            "rule": "each indicator changes its own inner lamp and leaves the "
                    "other side quiet"}
        out[f"{label}_hazard_both_sides"] = {
            "pass": (changed("HAZARD", "rear_lightsl", "amber_lit_fraction")
                     >= fl * area("rear_lightsl")
                     and changed("HAZARD", "rear_lightsr",
                                 "amber_lit_fraction")
                     >= fl * area("rear_lightsr")),
            "left_lamp_changed_px": round(changed(
                "HAZARD", "rear_lightsl", "amber_lit_fraction"), 1),
            "right_lamp_changed_px": round(changed(
                "HAZARD", "rear_lightsr", "amber_lit_fraction"), 1),
            "rule": "HAZARD changes both inner lamps"}
        out[f"{label}_off_shows_nothing"] = {
            "pass": (changed("OFF", "rear_lights") == 0
                     and by["OFF"]["lamp_measures"][scale]["rear_lights"][
                         "red"] > 0),
            "rule": "OFF is the baseline: no lamp changes relative to itself, "
                    "and the lamp region is not empty"}
    return out


def main():
    args = parse_args()
    manifest_path = args.manifest or os.path.join(args.out_dir,
                                                  "freeze_render_manifest.json")
    with open(manifest_path) as fh:
        manifest = json.load(fh)
    bbox = manifest["lamp_bbox_px_1100x760"]
    render_size = tuple(manifest.get("render_size", [1100, 760]))
    report = {"source_renders": manifest["renders"], "lamp_bbox": bbox,
              "render_manifest_digest": digest(manifest_path),
              "states": STATES, "per_state": []}
    paths_600, paths_horizon, meta = {}, {}, {}
    for state in STATES:
        src = manifest["renders"].get(state)
        if not src or not os.path.exists(src):
            continue
        key = state.lower()
        six = to_vehicle_600(src, os.path.join(args.out_dir,
                                               f"state_{key}_600px.png"))
        horizon, crop = horizon_composite(src, args.out_dir, key)
        paths_600[state], paths_horizon[state] = six, crop
        meta[state] = {"px_600": six, "horizon": horizon, "horizon_1to1": crop}
    with Image.open(manifest["renders"]["OFF"]) as im:
        render_alpha = im.getchannel("A").getbbox()
    report["render_alpha_bbox"] = list(render_alpha)
    with Image.open(paths_600["OFF"]) as im:
        six_alpha = im.getchannel("A").getbbox()
    report["regions"] = {
        "600px": project_bbox(bbox, render_size, render_alpha, six_alpha),
        # The previewer places the vehicle's box at 610,40 with size 700x401;
        # the 1:1 crop starts at x=510, so the vehicle box starts at x=100.
        "horizon": project_bbox(bbox, render_size, render_alpha,
                                (610 - HORIZON_CROP[0], 40,
                                 610 - HORIZON_CROP[0] + 700, 40 + 401))}
    lamp_boxes = manifest.get("lamp_bboxes_px_1100x760") or {}
    lamp_mask_px = manifest.get("lamp_mask_pixels") or {}
    report["lamp_regions"] = {
        scale: {lamp: project_bbox(b, render_size, render_alpha, target)
                for lamp, b in lamp_boxes.items()}
        for scale, target in (("600px", six_alpha),
                              ("horizon", (610 - HORIZON_CROP[0], 40,
                                           610 - HORIZON_CROP[0] + 700,
                                           40 + 401)))}
    for state in STATES:
        if state not in meta:
            continue
        base_600 = load_rgb(paths_600["OFF"]) if "OFF" in paths_600 else None
        base_horizon = (load_rgb(paths_horizon["OFF"])
                        if "OFF" in paths_horizon else None)
        report["per_state"].append({
            "state": state, **meta[state],
            "measure_600": measure(paths_600[state],
                                   report["regions"]["600px"], base_600),
            "measure_horizon": measure(paths_horizon[state],
                                       report["regions"]["horizon"],
                                       base_horizon),
            "lamp_measures": {
                scale: {lamp: measure(paths[state], region,
                                      load_rgb(paths["OFF"]))
                        for lamp, region in report["lamp_regions"][scale].items()}
                for scale, paths in (("600px", paths_600),
                                     ("horizon", paths_horizon))}})
    scale_targets = {"600px": 600.0, "horizon": 700.0}
    for entry in report["per_state"]:
        for scale, target in scale_targets.items():
            for lamp, m in entry["lamp_measures"][scale].items():
                m["lamp_silhouette_px"] = round(
                    silhouette_px(lamp_mask_px.get(lamp, 0), render_size,
                                  render_alpha, target), 1)
    missing = [lamp for lamp in lamp_boxes if not lamp_mask_px.get(lamp)]
    if missing:
        # Without the per-lamp areas every threshold below would be zero and
        # every verdict would pass vacuously. Fail rather than measure nothing.
        raise SystemExit(
            f"render manifest has no mask pixel counts for {missing}; re-run "
            f"the Blender states stage to regenerate freeze_render_manifest.json")
    report["verdicts"] = verdicts(report["per_state"])
    report["pass"] = all(v["pass"] for v in report["verdicts"].values())
    out = os.path.join(args.out_dir, "presentation_report.json")
    with open(out, "w") as fh:
        json.dump(report, fh, indent=2)
        fh.write("\n")
    for key, v in report["verdicts"].items():
        print(f"[presentation] {key}: {'PASS' if v['pass'] else 'FAIL'}")
    print(f"[presentation] -> {out}")
    return 0 if report["pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
