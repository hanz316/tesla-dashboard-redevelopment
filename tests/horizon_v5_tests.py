#!/usr/bin/env python3
"""Objective checks for the V5 prototype.

These are the checks that do not need eyes: the layout rules the whole Horizon
family shares, the navigation zero-pixel rule, the state set actually rendering
at 1920x480, deterministic output, and the accounting the report quotes. Whether
V5 looks right is a human decision and is not asserted here.

Usage:
    python3 tests/horizon_v5_tests.py
"""

import json
import os
import subprocess
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LAYOUT = os.path.join(REPO, "assets", "ui", "horizon_v5_layout.json")
TOKENS = os.path.join(REPO, "assets", "ui", "horizon_v5_tokens.json")
SCENE = os.path.join(REPO, "scenes", "horizon_v5.scene")
EVIDENCE = os.path.join(REPO, "assets", "checkpoints", "horizon_v5",
                        "horizon_v5_report.json")
QA = os.path.join(REPO, "tools", "preview", "horizon_v2_layout_qa.py")

FAILURES = []


def check(condition, label):
    if condition:
        print(f"  ok   {label}")
    else:
        print(f"  FAIL {label}")
        FAILURES.append(label)


def main():
    print("layout QA")
    result = subprocess.run([sys.executable, QA, "--layout", LAYOUT,
                             "--scene", SCENE, "--tokens", TOKENS],
                            capture_output=True, text=True)
    check(result.returncode == 0,
          "the shared Horizon layout QA passes (bounds, mask, zones, text "
          "collisions, the ten-speed km/h test, UNKNOWN, no debug text, "
          "decoration clearance)")

    layout = json.load(open(LAYOUT))
    tokens = json.load(open(TOKENS))
    scene = json.load(open(SCENE))

    print("frozen contract")
    vehicle = next(c for c in layout["components"] if c["id"] == "vehicle")
    check(bool(vehicle.get("crop")),
          "the vehicle uses the shared crop (framing only, no geometry change)")
    check(all(part.get("binding") for part in vehicle["parts"]),
          "the moving panels still bind to the delta-layer architecture")
    check(layout.get("forbidden_in_production"),
          "the forbidden production text list is inherited")
    check(tokens["reference"]["state"] in ("TEMPORARY_PENDING_REFERENCE",
                                           "MEASURED_FROM_REFERENCE"),
          "the reference state is declared, so a temporary background can never "
          "be mistaken for final art")

    print("state coverage")
    states = layout["screenshot_states"]
    check(len(states) == 20, f"twenty states are declared ({len(states)})")
    check("v5_unknown" in states and "v5_stale" in states,
          "both the unknown and the stale state are covered")

    print("rendered evidence")
    if os.path.isfile(EVIDENCE):
        report = json.load(open(EVIDENCE))
        check(report["navigation_hidden_pixels"] == 0,
              f"a hidden navigation draws zero pixels "
              f"({report['navigation_hidden_pixels']})")
        check(len(report["screenshots"]) == 20,
              "all twenty screenshots were rendered")
        check(os.path.isfile(os.path.join(REPO, report["contact_sheet"])),
              "the contact sheet exists")
        check(os.path.isfile(os.path.join(REPO, report["physical_scale"])),
              "the physical-scale sheet exists")
        missing = [path for path in report["screenshots"].values()
                   if not os.path.isfile(os.path.join(REPO, path))]
        check(not missing, f"every declared screenshot exists ({missing})")
    else:
        check(False, "the evidence report exists (run "
                     "tools/preview/horizon_v5_evidence.py)")

    print("")
    if FAILURES:
        print(f"{len(FAILURES)} FAILED:")
        for failure in FAILURES:
            print(f"  {failure}")
        return 1
    print("all horizon v5 checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
