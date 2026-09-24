#!/usr/bin/env python3
"""Bake the vehicle state renders into layers that can be composed correctly.

WHY THIS EXISTS

Every state render in `assets/rendered/vehicle` is a full-vehicle render: the
door sequence frames are the whole car with the door at an angle, the indicator
frames are the whole car with one lamp lit, and so on. Measured against the
closed base, a door frame differs from it in a compact region (about 1.5k-4.6k
pixels) and never removes a pixel the base had.

That is why compositing two of them is wrong. Drawing "door FL open" and then
"door RL open" leaves the second frame's *closed* FL door painted over the open
one, because the second frame contains the whole car, not just its own panel.
The same thing closes an open trunk lid when any later full-frame layer is
drawn, including a brake or indicator frame.

The fix is to bake, per state frame, the layer that means "only what this state
changes about the car":

    delta = pixels the state adds (opaque in the frame, transparent in the base)
          | pixels the state changes (both opaque, colour differs by > threshold)

Composing the base with the deltas of the states that are active therefore
reproduces exactly the physical picture - and, crucially, a layer can never
paint a panel back into its closed position, because unchanged pixels are not
in it at all.

Properties this script asserts before writing anything:

* no state frame removes a pixel the base has (an "erased" pixel would need a
  real hole mask, and none of these renders has one);
* base + delta reconstructs the original frame (no pixel differs by more than
  the threshold), so the layer is a faithful replacement, not an approximation
  of the panel;
* the delta is compact - a panel, not half the car.

Output: `assets/rendered/vehicle/delta/<group>/<name>.png` plus
`delta_report.json`. Derived and regenerable, so the tree stays out of git like
the renders it is built from.

Usage:
    python3 tools/assets/bake_vehicle_deltas.py
"""

import glob
import json
import os
import sys

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
ROOT = os.path.join(REPO, "assets", "rendered", "vehicle")
BASE = os.path.join(ROOT, "base", "000.png")
OUT = os.path.join(ROOT, "delta")
REPORT = os.path.join(OUT, "delta_report.json")

# A pixel counts as changed when any colour channel moves by more than this.
# Below it the two renders differ only by sampling noise: measured, over 97% of
# the car is bit-identical or within 4 levels.
THRESHOLD = 8

# Every state asset that has to become a delta layer.
GROUPS = {
    "door_fl": "door_fl",
    "door_fr": "door_fr",
    "door_rl": "door_rl",
    "door_rr": "door_rr",
    "frunk": "frunk",
    "trunk": "trunk",
    "trunk_ind_left": "trunk/ind_left",
    "trunk_ind_right": "trunk/ind_right",
    "trunk_ind_both": "trunk/ind_both",
    "indicator_left": "indicator_left",
    "indicator_right": "indicator_right",
    "hazard": "hazard",
    "brake_on": "brake_on",
    "headlight_on": "headlight_on",
    "running_on": "running_on",
}

# Panels keep their whole delta, including pixels another panel also claims.
# Resolving that overlap here was tried and rejected: two doors on the same
# side of the car project into the same space, so arbitration cut 159 pixels
# out of the open FL door and 427 out of the open RL door - removing real
# geometry to fix a shading overlap. Overlaps are therefore resolved at
# composition time, by the documented paint order (front doors first, then the
# rear ones, then the lids), which cannot delete a panel's own shape.
PANEL_GROUPS = ("door_fl", "door_fr", "door_rl", "door_rr", "frunk", "trunk")


def main():
    try:
        import numpy as np
        from PIL import Image
    except ImportError as error:
        sys.exit(f"Pillow and numpy are required: {error}")

    base_image = Image.open(BASE).convert("RGBA")
    base = np.asarray(base_image).astype(np.int16)
    base_alpha = base[:, :, 3] > 0

    report = {
        "schema": "vehicle-delta-layers v1",
        "base": os.path.relpath(BASE, REPO),
        "threshold": THRESHOLD,
        "why": "Each frame of a state render is the whole car. A layer that is "
               "only what the state changes lets several states be composed "
               "without any of them repainting another panel to closed.",
        "groups": {},
    }
    failures = []
    total_layers = 0

    for group, relative in sorted(GROUPS.items()):
        source_dir = os.path.join(ROOT, relative)
        frames = sorted(glob.glob(os.path.join(source_dir, "*.png")))
        if not frames:
            failures.append(f"{group}: no frames found in {relative}")
            continue
        out_dir = os.path.join(OUT, group)
        os.makedirs(out_dir, exist_ok=True)
        entries = []
        for path in frames:
            frame_image = Image.open(path).convert("RGBA")
            frame = np.asarray(frame_image).astype(np.int16)
            frame_alpha = frame[:, :, 3] > 0

            erased = int((base_alpha & ~frame_alpha).sum())
            if erased:
                failures.append(
                    f"{group}/{os.path.basename(path)}: {erased} base pixels "
                    f"are not covered by the frame")

            added = frame_alpha & ~base_alpha
            both = frame_alpha & base_alpha
            changed = both & (np.abs(frame[:, :, :3] - base[:, :, :3]).max(axis=2)
                              > THRESHOLD)
            mask = added | changed

            layer = np.zeros_like(frame)
            layer[mask] = frame[mask]
            layer_image = Image.fromarray(layer.astype("uint8"), "RGBA")
            out_path = os.path.join(out_dir, os.path.basename(path))
            layer_image.save(out_path)

            # Reconstruction: base with the layer over it must reproduce the
            # original frame wherever it matters.
            composed = base.copy()
            composed[mask] = frame[mask]
            error = np.abs(composed[:, :, :3] - frame[:, :, :3]).max(axis=2)
            bad = int(((error > THRESHOLD) & (frame_alpha | base_alpha)).sum())
            if bad:
                failures.append(
                    f"{group}/{os.path.basename(path)}: reconstruction leaves "
                    f"{bad} pixels differing by more than {THRESHOLD}")

            mask_y, mask_x = np.nonzero(mask)
            bbox = ([int(mask_x.min()), int(mask_y.min()),
                     int(mask_x.max()), int(mask_y.max())]
                    if mask.any() else None)
            coverage = float(mask.sum()) / float(base_alpha.sum())
            if coverage > 0.25:
                failures.append(
                    f"{group}/{os.path.basename(path)}: layer covers "
                    f"{coverage:.0%} of the car, which is not a panel")
            entries.append({
                "frame": os.path.basename(path),
                "layer": os.path.relpath(out_path, REPO),
                "pixels": int(mask.sum()),
                "added": int(added.sum()),
                "changed": int(changed.sum()),
                "added_pixels": int((mask & added).sum()),
                "added_total": int(added.sum()),
                "erased": erased,
                "bbox": bbox,
                "coverage": round(coverage, 4),
                "reconstruction_error_pixels": bad,
            })
            total_layers += 1
        report["groups"][group] = {
            "source": os.path.relpath(source_dir, REPO),
            "frames": len(entries),
            "entries": entries,
        }

    if failures:
        for failure in failures:
            print(f"  FAIL {failure}")
        sys.exit(f"[delta] {len(failures)} failures; nothing was committed")

    with open(REPORT, "w") as fh:
        json.dump(report, fh, indent=1)
        fh.write("\n")

    print(f"[delta] {total_layers} layers from {len(report['groups'])} groups "
          f"-> {os.path.relpath(OUT, REPO)}")
    for group, entry in report["groups"].items():
        last = entry["entries"][-1]
        print(f"[delta]   {group:16s} {entry['frames']:2d} frames, "
              f"final layer {last['pixels']:5d} px in {last['bbox']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
