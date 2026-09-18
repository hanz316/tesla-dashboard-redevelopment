#!/usr/bin/env python3
"""Composite vs direct render: does an open trunk keep its indicator lamps right?

The inner indicator lamps belong to the trunk lid, so on an open trunk their
light must follow the lid. This compares the composited result (base + moving
panel layer + its own lighting variant) against a DIRECT render of the same
state, and measures pixel disagreement inside the lamp region - the region is
located from the disagreement between the lit and unlit direct renders, so it
cannot accidentally sample the body.

Usage:
    python3 tools/assets/verify_trunk_lighting_composite.py \
        --assets assets/rendered/vehicle \
        --reference assets/checkpoints/vehicle_state_assets/trunk_lighting_reference \
        --out assets/checkpoints/vehicle_state_assets/trunk_lighting_composite.json
"""

import argparse
import json
import os
import subprocess
import sys

try:
    import numpy as np
    from PIL import Image
except ImportError:  # pragma: no cover
    sys.exit("Pillow and numpy are required")

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
FRAMES = (0, 7, 13)
FRAME_COUNT = 14          # trunk sequence length, for t = frame / (n - 1)
TOLERANCE = 0.06          # per-pixel, 6 % of full scale: render noise + AA
FAIL_FRACTION = 0.02      # share of lamp-region pixels allowed outside it


def load(path):
    return np.asarray(Image.open(path).convert("RGBA"),
                      dtype=np.float32) / 255.0


CANVAS = (356, 236)
VEHICLE_BOX = (610, 40, 700, 401)      # the Horizon node box


def run_previewer(state, t, out_path):
    """Render the state through the runtime's own composition path."""
    cmd = [sys.executable, os.path.join(REPO_ROOT, "tools", "preview",
                                        "scene_preview.py"),
           "--scene", os.path.join(REPO_ROOT, "scenes",
                                   "horizon_redesign_a.scene"),
           "--state", state, "--require-model3", "--t", str(t),
           "--out", os.path.dirname(out_path),
           "--out-name", os.path.splitext(os.path.basename(out_path))[0]]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"previewer failed for {state}: {proc.stderr[-400:]}")
    return out_path


def preview_canvas(path):
    """The vehicle box from a composed Horizon frame, back in canvas space.

    The previewer scales the 356x236 canvas into the node box; downscaling the
    box back to the canvas cancels that resampling so the comparison is against
    the reference renders in their own space rather than against an upscaled
    approximation of them.
    """
    img = Image.open(path).convert("RGBA")
    x, y, w, h = VEHICLE_BOX
    crop = img.crop((x, y, x + w, y + h))
    return np.asarray(crop.resize(CANVAS, Image.LANCZOS),
                      dtype=np.float32) / 255.0


def lamp_mask(reference, frame):
    """Pixels any indicator channel lights up, from the reference renders.

    Measuring over the padded bounding box of both lamps dilutes the number:
    erasing an entire lamp came out as 1.3 % of the box. The measurement is
    therefore restricted to the pixels the lamps actually change, and a small
    tolerance band is grown around them for anti-aliasing.
    """
    off = load(os.path.join(reference, f"lamp_off_{frame:03d}.png"))
    diff = np.zeros(off.shape[:2], dtype=bool)
    for name in ("ind_left", "ind_right", "hazard"):
        other = load(os.path.join(reference, f"{name}_{frame:03d}.png"))
        diff |= np.abs(other[:, :, :3] - off[:, :, :3]).max(axis=2) > 0.05
    if not diff.any():
        return None
    grown = diff.copy()
    for _ in range(2):        # anti-aliasing band
        g = grown.copy()
        g[1:, :] |= grown[:-1, :]
        g[:-1, :] |= grown[1:, :]
        g[:, 1:] |= grown[:, :-1]
        g[:, :-1] |= grown[:, 1:]
        grown = g
    return grown


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--assets", required=True)
    ap.add_argument("--reference", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    report = {"frames": list(FRAMES), "per_pixel_tolerance": TOLERANCE,
              "fail_fraction": FAIL_FRACTION,
              "method": "the composed Horizon frame is downscaled back to the "
                        "356x236 canvas and compared against a direct render of "
                        "the same state",
              "states": {}}
    work = os.path.join(args.out.rsplit(os.sep, 1)[0], "trunk_composite_check")
    os.makedirs(work, exist_ok=True)
    for label, dev_state in (("ind_left", "vehicle_trunk_left"),
                             ("ind_right", "vehicle_trunk_right"),
                             ("hazard", "vehicle_trunk_hazard")):
        entry = {"preview_state": dev_state, "per_frame": []}
        for frame in FRAMES:
            reference = load(os.path.join(
                args.reference, f"{label}_{frame:03d}.png"))
            mask = lamp_mask(args.reference, frame)
            if mask is None:
                entry["per_frame"].append({"frame": frame,
                                           "error": "no lamp region"})
                continue
            t = frame / float(FRAME_COUNT - 1)
            composed = preview_canvas(run_previewer(
                dev_state, t, os.path.join(work, f"{label}_{frame:03d}.png")))
            diff = np.abs(composed[:, :, :3] - reference[:, :, :3]).max(axis=2)
            bad = (diff > TOLERANCE) & mask
            entry["per_frame"].append({
                "frame": frame, "lamp_pixels": int(mask.sum()),
                "disagreeing_pixels": int(bad.sum()),
                "disagreeing_fraction":
                    round(float(bad.sum()) / max(1, int(mask.sum())), 6),
                "max_delta": round(float(diff.max()), 4),
                "pass": (float(bad.sum()) / max(1, int(mask.sum())))
                        <= FAIL_FRACTION})
        entry["pass"] = all(f.get("pass", False) for f in entry["per_frame"])
        report["states"][label] = entry
    # A control: the same measurement with the overlay left at the closed
    # position, which is the defect this architecture removes. If the control
    # passed too, the measurement would not be discriminating.
    control = {}
    for frame in FRAMES:
        mask = lamp_mask(args.reference, frame)
        closed = load(os.path.join(args.assets, "indicator_left", "000.png"))
        trunk = load(os.path.join(args.assets, "trunk", f"{frame:03d}.png"))
        alpha = closed[:, :, 3:4]
        composed = closed * alpha + trunk * (1.0 - alpha)
        reference = load(os.path.join(args.reference,
                                      f"ind_left_{frame:03d}.png"))
        diff = np.abs(composed[:, :, :3] - reference[:, :, :3]).max(axis=2)
        bad = (diff > TOLERANCE) & mask
        control[frame] = {"disagreeing_fraction":
                          round(float(bad.sum()) / max(1, int(mask.sum())), 6)}
    report["control_closed_position_overlay"] = control
    report["control_is_discriminating"] = any(
        v["disagreeing_fraction"] > FAIL_FRACTION for v in control.values())
    report["pass"] = (all(s["pass"] for s in report["states"].values())
                      and report["control_is_discriminating"])
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w") as fh:
        json.dump(report, fh, indent=2)
        fh.write("\n")
    for state, entry in report["states"].items():
        print(f"[trunk-light] {state}: "
              f"{[(f['frame'], f.get('disagreeing_fraction')) for f in entry['per_frame']]}")
    print(f"[trunk-light] control (closed-position overlay): {control}")
    print(f"[trunk-light] pass={report['pass']}")
    return 0 if report["pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
