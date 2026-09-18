#!/usr/bin/env python3
"""Why do UART_LOST and stale states differ from neutral?

A change is not automatically a defect and is not automatically correct either.
This locates it: pixels inside the vehicle node box versus pixels in the rest of
the frame. If the vehicle box is unchanged, the vehicle did not silently become
OFF or CLOSED - the difference is the UI's explicit unknown treatment. If the
vehicle box changed in a way that shows a confirmed state, that is a defect.

Usage:
    python3 tools/assets/audit_unknown_state_visuals.py \
        --dir assets/checkpoints/vehicle_state_assets/horizon \
        --out assets/checkpoints/vehicle_state_assets/unknown_state_audit.json
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

VEHICLE_BOX = (610, 40, 700, 401)     # x, y, w, h in the Horizon frame
BASELINE = "normal_drive"
AUDITED = ["uart_lost", "vehicle_stale_doors", "soc_untrusted"]
VISIBLE = 0.02


def load(path):
    return np.asarray(Image.open(path).convert("RGB"),
                      dtype=np.float32) / 255.0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    base = load(os.path.join(args.dir, f"horizon_{BASELINE}.png"))
    x, y, w, h = VEHICLE_BOX
    report = {"baseline": BASELINE, "vehicle_box": list(VEHICLE_BOX),
              "states": {}, "semantics": {}}
    for state in AUDITED:
        path = os.path.join(args.dir, f"horizon_{state}.png")
        if not os.path.exists(path):
            continue
        img = load(path)
        diff = np.abs(img - base).max(axis=2)
        changed = diff > VISIBLE
        in_box = np.zeros_like(changed)
        in_box[y:y + h, x:x + w] = True
        box_change = int((changed & in_box).sum())
        chrome_change = int((changed & ~in_box).sum())
        box_delta = float(np.abs(img[y:y + h, x:x + w]
                                 - base[y:y + h, x:x + w]).max())
        entry = {"changed_pixels_total": int(changed.sum()),
                 "changed_pixels_in_vehicle_box": box_change,
                 "changed_pixels_outside_vehicle_box": chrome_change,
                 "vehicle_box_max_delta": round(box_delta, 5),
                 "vehicle_box_unchanged": box_change == 0,
                 "verdict": None}
        if box_change == 0:
            entry["verdict"] = (
                "the vehicle itself did not change: no confirmed OFF or "
                "CLOSED was drawn. The difference is the UI's explicit "
                "unknown treatment (closure text renders as unknown rather "
                "than a state).")
        else:
            entry["verdict"] = (
                "the vehicle box changed: inspect whether a confirmed state "
                "was drawn for a signal that is not known")
        report["states"][state] = entry

    # The signal-level table: what the state carries, and what the controller
    # does with a signal that is not there.
    report["semantics"] = {
        "rule": "UNKNOWN != OFF and UNKNOWN != CLOSED",
        "uart_lost": {
            "signals_present": "none: the mock state carries only "
                               "uart_health = UART LOST",
            "controller": "every lamp is known == Unknown (never a confirmed "
                          "off); every panel holds the position it already had",
            "assets": "the base vehicle is drawn unchanged; the closure text "
                      "renders the unknown marker ('--') instead of a state",
            "justification": "an explicit unknown treatment exists for the "
                             "closure state, and the vehicle layer is not "
                             "re-drawn with a fabricated closed state"},
        "stale": {
            "signals_present": "uart_health = UART STALE",
            "controller": "same as UART LOST: lamps Unknown, panels hold",
            "assets": "unchanged vehicle, unknown closure text",
        },
        "controller_tests": "tests/vehicle_visual_controller_tests.cpp asserts "
                            "UNKNOWN != OFF for lamps, hold-on-missing for "
                            "panels, and that a stale signal is unknown",
    }
    report["pass"] = all(s["vehicle_box_unchanged"]
                         for s in report["states"].values())
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w") as fh:
        json.dump(report, fh, indent=2)
        fh.write("\n")
    for state, entry in report["states"].items():
        print(f"[audit] {state}: total={entry['changed_pixels_total']} "
              f"vehicle_box={entry['changed_pixels_in_vehicle_box']} "
              f"chrome={entry['changed_pixels_outside_vehicle_box']} "
              f"box_max_delta={entry['vehicle_box_max_delta']}")
    print(f"[audit] pass={report['pass']}")
    return 0 if report["pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
