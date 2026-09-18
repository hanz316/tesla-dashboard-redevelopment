#!/usr/bin/env python3
"""Protect the trunk-attached lighting ownership rule.

The inner rear indicator lamps belong to the trunk lid. A lighting overlay left
at the closed-position screen location on an open trunk is wrong by 57 % of the
lamp's pixels, so the rule has to survive future edits to the compositor.

Checks: the contract exists and states the rule; the variants exist for every
frame when the generated assets are present in this checkout; the measured
composite-vs-direct comparison passes and its control is discriminating (a
control that did not fail would mean the measurement proves nothing).
"""

import json
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONTRACT = os.path.join(REPO, "assets", "vehicle_state_moving_lighting.json")
COMPOSITE = os.path.join(REPO, "assets", "checkpoints",
                         "vehicle_state_assets", "trunk_lighting_composite.json")
VARIANTS = os.path.join(REPO, "assets", "checkpoints", "vehicle_state_assets",
                        "trunk_lighting_variants.json")

FAILURES = []


def check(condition, label):
    if condition:
        print("  ok   %s" % label)
    else:
        print("  FAIL %s" % label)
        FAILURES.append(label)


def main():
    print("moving-lighting contract")
    check(os.path.exists(CONTRACT), "the contract file is committed")
    contract = {}
    if os.path.exists(CONTRACT):
        with open(CONTRACT) as fh:
            contract = json.load(fh)
        trunk = (contract.get("panels") or {}).get("trunk", {})
        check(trunk.get("ownership") == "TRUNK_MOVING",
              "the trunk panel is declared TRUNK_MOVING")
        carries = set(trunk.get("carries", []))
        check({"INDICATOR_LEFT", "INDICATOR_RIGHT"} <= carries,
              "the trunk is declared to carry both indicator channels")
        variants = trunk.get("variants") or {}
        check({"ind_left", "ind_right", "ind_both"} <= set(variants),
              "one variant per channel set, including hazard as its own render")
        check("2D affine warp" in (trunk.get("rejected_alternative") or ""),
              "the rejected 2D-warp alternative is recorded with its reason")
        check("FIXED_BODY" in contract.get("architecture", ""),
              "the architecture separates FIXED_BODY and TRUNK_MOVING "
              "contributions")

    print("variant assets")
    variants_report = {}
    if os.path.exists(VARIANTS):
        with open(VARIANTS) as fh:
            variants_report = json.load(fh)
    assets_root = os.path.join(REPO, "assets", "rendered", "vehicle")
    production_present = os.path.isfile(os.path.join(assets_root,
                                                     "MODEL3_SOURCE.json"))
    if production_present:
        for name, spec in (variants_report.get("variants") or {}).items():
            directory = os.path.join(assets_root, spec["dir"])
            frames = sorted(f for f in os.listdir(directory)
                            if f.endswith(".png")) if os.path.isdir(directory) \
                else []
            check(len(frames) == spec["frames"],
                  f"variant {name} has all {spec['frames']} frames")
    else:
        print("  skip variant asset check: the generated vehicle tree is not "
              "in this checkout (rebuild with "
              "tools/blender/build_trunk_lighting_variants.py)")
        check(bool(variants_report), "the recorded variant evidence is present")

    print("composite vs direct render")
    if os.path.exists(COMPOSITE):
        with open(COMPOSITE) as fh:
            report = json.load(fh)
        for state, entry in report["states"].items():
            worst = max((f.get("disagreeing_fraction", 1.0)
                         for f in entry["per_frame"]), default=1.0)
            check(entry["pass"] and worst <= report["fail_fraction"],
                  f"{state}: composed lamp pixels match the direct render "
                  f"(worst {worst:.4%})")
        check(report["control_is_discriminating"],
              "the control (closed-position overlay) is measurably wrong, so "
              "the comparison discriminates")
        worst_control = max(v["disagreeing_fraction"] for v in
                            report["control_closed_position_overlay"].values())
        check(worst_control > 0.25,
              "the control disagrees by more than a quarter of the lamp "
              f"({worst_control:.1%})")
    else:
        print("  skip composite check: no measured report in this checkout")

    print("")
    if FAILURES:
        print("%d FAILED: %s" % (len(FAILURES), "; ".join(FAILURES)))
        return 1
    print("all trunk lighting ownership checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
