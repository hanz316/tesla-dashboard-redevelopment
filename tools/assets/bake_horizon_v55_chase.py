#!/usr/bin/env python3
"""Bake the chase-camera vehicle layers, one yaw variant at a time.

The Horizon car is a real 3D render behind a frozen orthographic camera, so a
chase camera is a camera orbit, not a 2D rotation of the parked car. This
driver orbits the camera towards the car's rear (negative degrees: measured,
not assumed - the positive direction swings towards the car's side), renders
the same lighting states, and composes them with the same compositor the
accepted V5.4 layers came from.

Layered on purpose: yaw is its own asset dimension, so the runtime blends
between two neighbouring baked angles and never needs the full
speed x phase x state product pre-baked.

Usage:
    python3 tools/assets/bake_horizon_v55_chase.py --angles 4,7,10,13,16 \
        --states base --phases night,day
    python3 tools/assets/bake_horizon_v55_chase.py --angles 5,10 \
        --phases night,day,dawn,dusk
"""

import argparse
import json
import os
import subprocess
import sys
import time

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
CHASE = os.path.join(REPO, "assets", "rendered", "vehicle", "horizon_v5",
                     "chase")
MASTER = os.path.join(REPO, "assets", "source", "blender",
                      "model_a_material_candidate.blend")
BLENDER = "/Applications/Blender.app/Contents/MacOS/Blender"
ENVIRONMENT = os.path.join(REPO, "tools", "blender",
                           "build_horizon_v5_environment.py")
COMPOSE = os.path.join(REPO, "tools", "assets",
                       "compose_horizon_v5_vehicle.py")
DEFAULT_REPORT = os.path.join(REPO, "assets", "checkpoints", "horizon_v5",
                              "horizon_v55_chase_render.json")

STATES = "base,running,brake,headlight,indicator_left,indicator_right,hazard"


def angle_dir(magnitude):
    return os.path.join(CHASE, f"yaw{int(round(magnitude)):02d}")


def render(args, magnitude, phase):
    """Render one yaw variant for one phase; returns its report path."""
    root = os.path.join(angle_dir(magnitude), phase)
    # The environment builder appends a non-night phase to its output root, so
    # for those phases the argument is the parent directory.
    out = root if phase == "night" else angle_dir(magnitude)
    report = os.path.join(root, "render_report.json")
    states = [value for value in args.states.split(",") if value]
    expected = [os.path.join(root, "road", "no_car.png")]
    expected += [os.path.join(root, "car", state, "000.png")
                 for state in states]
    expected += [os.path.join(root, "road", f"{state}.png")
                 for state in states]
    if not args.force and os.path.isfile(report) \
            and all(os.path.isfile(path) for path in expected):
        print(f"[v5.5-chase] keep yaw {magnitude} {phase}")
        return report
    os.makedirs(out, exist_ok=True)
    # The camera orbits towards the car's rear; the runtime quotes the
    # magnitude and this sign convention stays inside the baker.
    command = [args.blender, "-b", "-P", ENVIRONMENT, "--",
               "--master", args.master, "--phase", phase,
               "--stages", "road,car", "--states", args.states,
               "--samples", str(args.samples),
               "--yaw-deg", str(-abs(magnitude)),
               "--out", out, "--report", report]
    started = time.time()
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode != 0:
        sys.stderr.write(result.stdout[-4000:] + result.stderr[-4000:])
        raise SystemExit(f"render failed: yaw {magnitude} {phase}")
    print(f"[v5.5-chase] rendered yaw {magnitude} {phase} "
          f"in {round(time.time() - started, 1)} s")
    return report


def compose(args, magnitude, phase):
    """Compose the rendered passes into one baked layer per lighting state."""
    command = [sys.executable, COMPOSE,
               "--dir", angle_dir(magnitude), "--phase", phase,
               "--states", args.states]
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode != 0:
        sys.stderr.write(result.stdout[-4000:] + result.stderr[-4000:])
        raise SystemExit(f"compose failed: yaw {magnitude} {phase}")
    print(f"[v5.5-chase] composed yaw {magnitude} {phase}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--angles", default="4,7,10,13,16",
                        help="chase yaw magnitudes in degrees; baked as the "
                             "camera orbiting that far towards the car's rear")
    parser.add_argument("--phases", default="night,day")
    parser.add_argument("--states", default=STATES)
    parser.add_argument("--samples", type=int, default=96)
    parser.add_argument("--blender", default=BLENDER)
    parser.add_argument("--master", default=MASTER)
    parser.add_argument("--report", default=DEFAULT_REPORT)
    parser.add_argument("--force", action="store_true",
                        help="re-render variants that already exist")
    args = parser.parse_args()

    if not os.path.isfile(args.blender):
        sys.exit(f"Blender not found at {args.blender}")
    angles = [float(value) for value in args.angles.split(",") if value]
    phases = [value for value in args.phases.split(",") if value]
    report = {"schema": "horizon-v5.5-chase-render v1",
              "measurement_platform": "MAC MEASURED",
              "device": "UNKNOWN_UNTIL_DEVICE_TEST",
              "blender": os.path.relpath(args.blender, "/"),
              "master": os.path.relpath(args.master, REPO),
              "samples": args.samples,
              "states": args.states.split(","),
              "sign_convention": "the baked --yaw-deg is negative: the camera "
                                 "orbits towards the car's rear. The runtime "
                                 "quotes the magnitude.",
              "variants": {}}
    for magnitude in angles:
        for phase in phases:
            render_report = render(args, magnitude, phase)
            compose(args, magnitude, phase)
            document = json.load(open(render_report))
            key = f"yaw{magnitude:g}_{phase}"
            report["variants"][key] = {
                "yaw_deg": document.get("yaw_deg"),
                "phase": document.get("phase"),
                "samples": document.get("samples"),
                "car_framing": document.get("car_framing"),
                "timings_s": document.get("timings_s"),
                "layer_manifest": os.path.relpath(
                    os.path.join(angle_dir(magnitude),
                                 f"horizon_v5_vehicle_{phase}.json"), REPO)}
    os.makedirs(os.path.dirname(args.report), exist_ok=True)
    if os.path.isfile(args.report):
        previous = json.load(open(args.report))
        merged = previous.get("variants", {})
        merged.update(report["variants"])
        report["variants"] = merged
    with open(args.report, "w") as handle:
        json.dump(report, handle, indent=1)
        handle.write("\n")
    print(f"[v5.5-chase] {os.path.relpath(args.report, REPO)} "
          f"({len(report['variants'])} variants)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
