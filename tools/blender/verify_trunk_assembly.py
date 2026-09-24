#!/usr/bin/env python3
"""Is the trunk a rigid assembly, in world space and on screen?

Two questions, both answered numerically:

1. rigidity - every child's transform relative to the lid stays constant at
   0/25/50/75/100 % (this is the same check the render script reports, run
   independently here);
2. screen space - where each tracked part lands in the 356x236 canvas at each
   step, so "the plate stayed behind" or "the lamp did not move" is a number
   rather than an opinion. Under the production camera the projection is
   orthographic, so a part that moves in world space moves on screen.

Usage:
    blender -b -P tools/blender/verify_trunk_assembly.py -- \
        --master assets/source/blender/model_a_production_master.blend \
        --out assets/checkpoints/vehicle_state_assets/trunk_assembly.json
"""

import argparse
import json
import math
import os
import sys

import bpy
from bpy_extras.object_utils import world_to_camera_view
from mathutils import Matrix, Vector

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import panel_assembly as assembly  # noqa: E402

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
CANVAS = (356, 236)
PROGRESS = (0.0, 0.25, 0.5, 0.75, 1.0)
OPEN_ANGLE_DEG = 55.0
CAMERA = {"name": "Camera_Horizon", "ortho_scale": 5.55,
          "location": (-5.30, -4.55, 3.85), "target": (0.0, 0.0, 0.62)}

# What the human review asked to be tracked, by the names this master uses.
TRACKED = {
    "trunk_panel": "boot",
    "inner_lamp_left": "rear_lightsl",
    "inner_lamp_right": "rear_lightsr",
    "license_plate": "platnomor",
    "plate_trim": "chrome_light",
    "brake_lamp": "light_breake",
    "reverse_lamp": "lightrevese_boot",
}


def parse_args():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    ap = argparse.ArgumentParser()
    ap.add_argument("--master", required=True)
    ap.add_argument("--out", required=True)
    return ap.parse_args(argv)


def ease_open(t):
    return 4.0 * t * t * t if t < 0.5 else 1.0 - pow(-2.0 * t + 2.0, 3) / 2.0


def rotate_about(pivot, angle_deg, axis="Y"):
    return (Matrix.Translation(pivot) @
            Matrix.Rotation(math.radians(angle_deg), 4, axis) @
            Matrix.Translation(-pivot))


def setup_camera(scene):
    camera = bpy.data.objects.get(CAMERA["name"])
    if camera is None:
        data = bpy.data.cameras.new(CAMERA["name"])
        camera = bpy.data.objects.new(CAMERA["name"], data)
        scene.collection.objects.link(camera)
        camera.data.type = "ORTHO"
        camera.data.ortho_scale = CAMERA["ortho_scale"]
        camera.location = CAMERA["location"]
        target = bpy.data.objects.new("Camera_Horizon_Target", None)
        scene.collection.objects.link(target)
        target.location = CAMERA["target"]
        con = camera.constraints.new("TRACK_TO")
        con.target = target
        con.track_axis = "TRACK_NEGATIVE_Z"
        con.up_axis = "UP_Y"
    scene.camera = camera
    bpy.context.view_layer.update()
    return camera


def projected(scene, camera, obj):
    points = [obj.matrix_world @ Vector(corner) for corner in obj.bound_box]
    xs, ys = [], []
    for point in points:
        co = world_to_camera_view(scene, camera, point)
        xs.append(co.x * CANVAS[0])
        ys.append((1.0 - co.y) * CANVAS[1])
    return {"bbox": [round(min(xs), 1), round(min(ys), 1),
                     round(max(xs), 1), round(max(ys), 1)],
            "centroid": [round(sum(xs) / len(xs), 1),
                         round(sum(ys) / len(ys), 1)]}


def main():
    args = parse_args()
    bpy.ops.wm.open_mainfile(filepath=args.master)
    scene = bpy.context.scene
    camera = setup_camera(scene)

    panel_object = "boot"
    rests = assembly.rest_matrices(bpy, "trunk", panel_object)
    missing = [name for name in TRACKED.values() if name not in rests]

    report = {
        "schema": "trunk-assembly v1",
        "master": os.path.relpath(args.master, REPO_ROOT),
        "canvas": list(CANVAS),
        "progress": list(PROGRESS),
        "open_angle_deg": OPEN_ANGLE_DEG,
        "assembly_members": sorted(rests),
        "tracked": TRACKED,
        "missing_tracked_objects": missing,
        "steps": [],
    }
    for step in PROGRESS:
        applied = ease_open(step) * OPEN_ANGLE_DEG
        transform = assembly.set_progress(bpy, "trunk", panel_object, rests,
                                          applied, "Y", rotate_about)
        worst, worst_name = assembly.rigidity_error(bpy, rests, panel_object,
                                                    transform)
        entry = {"progress": step, "applied_deg": round(applied, 3),
                 "rigidity_error": worst, "rigidity_worst_member": worst_name,
                 "parts": {}}
        for label, name in TRACKED.items():
            obj = bpy.data.objects.get(name)
            if obj is None:
                continue
            entry["parts"][label] = projected(scene, camera, obj)
        report["steps"].append(entry)
    assembly.restore(bpy, rests)

    # Screen-space statements, computed rather than eyeballed.
    first = report["steps"][0]["parts"]
    last = report["steps"][-1]["parts"]
    checks = {}
    for label in first:
        if label not in last:
            continue
        start = first[label]["centroid"]
        end = last[label]["centroid"]
        travel = math.hypot(end[0] - start[0], end[1] - start[1])
        lid_start = first["trunk_panel"]["centroid"]
        lid_end = last["trunk_panel"]["centroid"]
        lid_travel = math.hypot(lid_end[0] - lid_start[0], lid_end[1] - lid_start[1])
        # Consistent motion: same direction as the lid, and a travel in the same
        # order of magnitude (a part that stayed put would be near zero).
        direction = ((end[0] - start[0]) * (lid_end[0] - lid_start[0]) +
                     (end[1] - start[1]) * (lid_end[1] - lid_start[1]))
        checks[label] = {
            "travel_px": round(travel, 1),
            "lid_travel_px": round(lid_travel, 1),
            "travel_ratio": round(travel / lid_travel, 3) if lid_travel else None,
            "same_direction_as_lid": direction > 0,
            "left_the_closed_position": travel > 2.0,
        }
    report["screen_space"] = checks
    report["rigidity_max_error"] = max(step["rigidity_error"]
                                       for step in report["steps"])

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w") as fh:
        json.dump(report, fh, indent=1)
        fh.write("\n")

    print(f"[assembly] members {len(rests)}, max rigidity error "
          f"{report['rigidity_max_error']:.3e}")
    for label, data in checks.items():
        print(f"[assembly] {label:18s} travel {data['travel_px']:5.1f} px "
              f"(lid {data['lid_travel_px']:5.1f}), ratio "
              f"{data['travel_ratio']}, same direction "
              f"{data['same_direction_as_lid']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
