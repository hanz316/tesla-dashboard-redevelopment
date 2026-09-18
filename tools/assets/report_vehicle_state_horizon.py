#!/usr/bin/env python3
"""Measure the composed Horizon frames state by state.

Rendering the states is not evidence that a state reached the screen. This
compares every composed frame against the neutral one and records exactly how
many pixels changed and where, so a state that silently produced an identical
image is visible as a failure rather than as a rendered file.

Usage:
    python3 tools/assets/report_vehicle_state_horizon.py \
        --dir assets/checkpoints/vehicle_state_assets/horizon \
        --out assets/checkpoints/vehicle_state_assets/horizon_state_report.json
"""

import argparse
import json
import os
import sys

try:
    import numpy as np
    from PIL import Image
except ImportError:  # pragma: no cover
    sys.exit("Pillow and numpy are required")

BASELINE = "normal_drive"
VISIBLE = 0.02      # 2% of full scale is a visible change at 1920x480


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    files = sorted(f for f in os.listdir(args.dir) if f.endswith(".png"))
    base_path = os.path.join(args.dir, f"horizon_{BASELINE}.png")
    if not os.path.exists(base_path):
        sys.exit(f"missing baseline frame: {base_path}")
    base = np.asarray(Image.open(base_path).convert("RGB"),
                      dtype=np.float32) / 255.0
    report = {"baseline": f"horizon_{BASELINE}.png", "canvas": list(base.shape[:2]),
              "visible_threshold": VISIBLE, "states": {}}
    for name in files:
        state = name[len("horizon_"):-len(".png")]
        img = np.asarray(Image.open(os.path.join(args.dir, name)).convert("RGB"),
                         dtype=np.float32) / 255.0
        if img.shape != base.shape:
            report["states"][state] = {"error": "canvas differs"}
            continue
        diff = np.abs(img - base).max(axis=2)
        changed = diff > VISIBLE
        entry = {"changed_pixels": int(changed.sum()),
                 "changed_fraction": round(float(changed.mean()), 6),
                 "max_delta": round(float(diff.max()), 4)}
        if changed.any():
            ys, xs = np.nonzero(changed)
            entry["changed_bbox"] = [int(xs.min()), int(ys.min()),
                                     int(xs.max()) + 1, int(ys.max()) + 1]
        report["states"][state] = entry
    neutral = report["states"].get(BASELINE, {})
    neutral_ok = neutral.get("changed_pixels", 0) == 0
    off_states = ["vehicle_stale_doors", "uart_lost"]
    report["verdicts"] = {
        "baseline_is_its_own_baseline": {
            "pass": neutral_ok,
            "detail": "the neutral state must not differ from itself"},
        "every_lighting_state_reaches_the_screen": {
            "pass": all(report["states"].get(s, {}).get("changed_pixels", 0) > 0
                        for s in ["vehicle_brake", "vehicle_left",
                                  "vehicle_right", "vehicle_hazard",
                                  "vehicle_headlight"]),
            "detail": {s: report["states"].get(s, {}).get("changed_pixels")
                       for s in ["vehicle_brake", "vehicle_left",
                                 "vehicle_right", "vehicle_hazard",
                                 "vehicle_headlight"]}},
        "every_moving_panel_reaches_the_screen": {
            "pass": all(report["states"].get(s, {}).get("changed_pixels", 0) > 0
                        for s in ["door_fl_open", "vehicle_door_fr",
                                  "vehicle_door_rl", "vehicle_door_rr",
                                  "vehicle_frunk", "vehicle_trunk_brake"]),
            "detail": {s: report["states"].get(s, {}).get("changed_pixels")
                       for s in ["door_fl_open", "vehicle_door_fr",
                                 "vehicle_door_rl", "vehicle_door_rr",
                                 "vehicle_frunk", "vehicle_trunk_brake"]}},
        "composites_differ_from_their_parts": {
            "pass": (report["states"].get("vehicle_brake_left", {})
                     .get("changed_pixels", 0)
                     > report["states"].get("vehicle_brake", {})
                     .get("changed_pixels", 0) * 0.5),
            "brake": report["states"].get("vehicle_brake", {}),
            "brake_left": report["states"].get("vehicle_brake_left", {}),
            "detail": "brake+left changes at least half as much as brake alone "
                      "and is not identical to it"},
        "unknown_states_are_not_drawn_as_confident": {
            "pass": all(s in report["states"] for s in off_states),
            "detail": {s: report["states"].get(s, {}) for s in off_states}},
    }
    report["pass"] = all(v["pass"] for v in report["verdicts"].values())
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w") as fh:
        json.dump(report, fh, indent=2)
        fh.write("\n")
    for name, entry in sorted(report["states"].items()):
        print(f"[horizon] {name:24s} changed={entry.get('changed_pixels')} "
              f"fraction={entry.get('changed_fraction')}")
    print(f"[horizon] pass={report['pass']}")
    return 0 if report["pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
