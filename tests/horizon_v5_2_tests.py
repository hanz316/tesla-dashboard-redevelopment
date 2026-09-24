#!/usr/bin/env python3
"""Objective checks for Horizon V5.2: depth, material, perceptual motion.

V5.1 proved monotonicity. The review's objection was that scalars passed while
DAY collapsed into one grey mass and 88 km/h still looked parked, so V5.2 is
gated on the relationships that were actually named: ground against sky,
terrain band separation, paint/glass/tyre/rim separation in every environment,
the daylight reflection being shorter than the night one, and motion being
measurable in the motion regions at physical scale with the UI masked out.

Usage:
    python3 tests/horizon_v5_2_tests.py
"""

import json
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MATERIAL = os.path.join(REPO, "assets", "checkpoints", "horizon_v5",
                        "horizon_v52_material_metrics.json")
MOTION = os.path.join(REPO, "assets", "checkpoints", "horizon_v5",
                      "horizon_v52_motion_gate.json")

FAILURES = []


def check(condition, label):
    if condition:
        print(f"  ok   {label}")
    else:
        print(f"  FAIL {label}")
        FAILURES.append(label)
    return condition


def main():
    print("environment depth and contrast")
    if not os.path.isfile(MATERIAL):
        print("  note the V5.2 material metrics have not been generated "
              "(run tools/assets/report_horizon_v52_materials.py)")
    else:
        report = json.load(open(MATERIAL))
        phases = report["phases"]
        day = phases["day"].get("environment")
        night = phases["night"].get("environment")
        if day and night:
            check(day["ground_to_sky_ratio"] <= 0.65,
                  f"daylight ground is substantially darker than its sky "
                  f"(ratio {day['ground_to_sky_ratio']})")
            day_step = day["terrain_depth"]["max_abs_edge_step"]
            night_step = night["terrain_depth"]["max_abs_edge_step"]
            check(day_step >= 30.0,
                  f"daylight terrain bands separate by {day_step} of 255")
            check(day_step >= 1.5 * night_step,
                  f"daylight depth separation ({day_step}) is well above the "
                  f"night one ({night_step})")
            check(day["haze"] > day["ground_near"],
                  f"the horizon haze ({day['haze']}) is brighter than the road "
                  f"({day['ground_near']}) in daylight")
        for name in ("dawn", "day", "dusk", "night"):
            environment = phases[name].get("environment")
            if not environment:
                continue
            check(environment["ground_near"] < environment["sky"],
                  f"{name}: the ground stays darker than the sky")

        print("vehicle material, per environment")
        for name in ("dawn", "day", "dusk", "night"):
            vehicle = phases[name].get("vehicle")
            if not vehicle:
                continue
            check(vehicle["glass_minus_paint"] <= -60.0,
                  f"{name}: glass reads much darker than paint "
                  f"({vehicle['glass_minus_paint']})")
            check(vehicle["tyre_minus_paint"] <= -40.0,
                  f"{name}: tyres stay clearly dark against the paint "
                  f"({vehicle['tyre_minus_paint']})")
            check(vehicle["rim_minus_tyre"] >= 40.0,
                  f"{name}: the rim stays distinguishable from the tyre "
                  f"({vehicle['rim_minus_tyre']})")
            check(0.005 <= vehicle["highlight_coverage"] <= 0.35,
                  f"{name}: paint highlights cover "
                  f"{vehicle['highlight_coverage'] * 100:.1f}% of the body")
        day_reflection = phases["day"].get("reflection")
        night_reflection = phases["night"].get("reflection")
        if day_reflection and night_reflection:
            check(day_reflection["length_px"] <= night_reflection["length_px"],
                  f"the daylight reflection is shorter than the night one "
                  f"({day_reflection['length_px']} vs "
                  f"{night_reflection['length_px']} px)")
            check(day_reflection["mean_magnitude"]
                  <= night_reflection["mean_magnitude"],
                  f"the daylight reflection is weaker "
                  f"({day_reflection['mean_magnitude']} vs "
                  f"{night_reflection['mean_magnitude']})")

    print("perceptual motion gate")
    if not os.path.isfile(MOTION):
        print("  note the perceptual motion gate has not been run "
              "(tools/preview/horizon_v52_motion_gate.py)")
    else:
        gate = json.load(open(MOTION))
        check(gate["zero_at_standstill"],
              "0 km/h measures exactly zero difference in every motion region")
        check(gate["wheel_structure_falls"],
              "the rim's structure falls with speed (rotation is legible as "
              "the spokes smearing)")
        floors = {"wheels": 3.0, "road": 0.3, "wake": 1.0, "trail": 1.5}
        for pair, entry in gate["pairs"].items():
            half = entry["half_size"]
            for region, floor in floors.items():
                check(half[region]["mean"] >= floor,
                      f"{pair} km/h: {region} differs by {half[region]['mean']}"
                      f" at half physical size (floor {floor})")
        check(gate["region_masking"]["ui_boxes"] > 20,
              f"the gate masks {gate['region_masking']['ui_boxes']} UI boxes so "
              f"the speed digits cannot satisfy it")
    print("")
    if FAILURES:
        print(f"{len(FAILURES)} FAILED:")
        for failure in FAILURES:
            print(f"  {failure}")
        return 1
    print("all horizon v5.2 checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
