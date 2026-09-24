#!/usr/bin/env python3
"""Which objects are physically attached to the trunk lid?

The moving-panel contract needs an explicit TRUNK_MOVING list. Names alone are
not evidence: this reports, for every mesh object, where it sits in world space,
where it lands in the 356x236 asset canvas, and how far it is from the trunk
lid's own bounding box - so ownership can be argued from geometry and spatial
attachment.

Usage:
    blender -b -P tools/blender/report_trunk_ownership.py -- \
        --master assets/source/blender/model_a_production_master.blend \
        --out assets/checkpoints/vehicle_state_assets/trunk_ownership.json
"""

import argparse
import json
import os
import sys

import bpy
from mathutils.bvhtree import BVHTree
from bpy_extras.object_utils import world_to_camera_view
from mathutils import Vector

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))

HORIZON_CAMERA = {
    "name": "Camera_Horizon",
    "ortho_scale": 5.55,
    "location": (-5.30, -4.55, 3.85),
    "target": (0.0, 0.0, 0.62),
}
CANVAS = (356, 236)


def parse_args():
    argv = sys.argv
    argv = argv[argv.index("--") + 1:] if "--" in argv else []
    ap = argparse.ArgumentParser()
    ap.add_argument("--master", required=True)
    ap.add_argument("--out", required=True)
    return ap.parse_args(argv)


def world_corners(obj):
    return [obj.matrix_world @ Vector(corner) for corner in obj.bound_box]


def world_bounds(obj):
    corners = world_corners(obj)
    return (
        min(c.x for c in corners), min(c.y for c in corners), min(c.z for c in corners),
        max(c.x for c in corners), max(c.y for c in corners), max(c.z for c in corners),
    )


def bounds_distance(a, b):
    """Gap between two axis-aligned boxes; 0 when they touch or overlap."""
    gaps = []
    for index in range(3):
        lo_a, hi_a = a[index], a[index + 3]
        lo_b, hi_b = b[index], b[index + 3]
        if hi_a < lo_b:
            gaps.append(lo_b - hi_a)
        elif hi_b < lo_a:
            gaps.append(lo_a - hi_b)
        else:
            gaps.append(0.0)
    return max(gaps)


def project(scene, camera, points):
    xs, ys = [], []
    for point in points:
        co = world_to_camera_view(scene, camera, point)
        xs.append(co.x * CANVAS[0])
        ys.append((1.0 - co.y) * CANVAS[1])
    return [min(xs), min(ys), max(xs), max(ys)]


def boot_surface_tree(boot):
    """BVH of the trunk lid in world space, for attachment measurement."""
    mesh = boot.data
    matrix = boot.matrix_world
    vertices = [matrix @ vertex.co for vertex in mesh.vertices]
    polygons = [tuple(polygon.vertices) for polygon in mesh.polygons]
    return BVHTree.FromPolygons(vertices, polygons, all_triangles=False, epsilon=0.0)


def surface_distance(tree, obj, limit=4000):
    """Smallest distance from this object's vertices to the trunk surface."""
    matrix = obj.matrix_world
    vertices = [matrix @ vertex.co for vertex in obj.data.vertices]
    if not vertices:
        return None
    if len(vertices) > limit:
        step = max(1, len(vertices) // limit)
        vertices = vertices[::step]
    best = None
    for vertex in vertices:
        hit = tree.find_nearest(vertex)
        distance = hit[3] if hit and hit[3] is not None else None
        if distance is None:
            continue
        if best is None or distance < best:
            best = distance
    return best


def main():
    args = parse_args()
    bpy.ops.wm.open_mainfile(filepath=args.master)
    scene = bpy.context.scene
    camera = bpy.data.objects.get(HORIZON_CAMERA["name"])
    if camera is None:
        # The master is a car, not a render setup: the asset pipeline creates
        # the camera. Recreate exactly what build_vehicle_state_assets.py does,
        # so the projected boxes below are the ones the assets are rendered at.
        data = bpy.data.cameras.new(HORIZON_CAMERA["name"])
        camera = bpy.data.objects.new(HORIZON_CAMERA["name"], data)
        scene.collection.objects.link(camera)
        camera.data.type = "ORTHO"
        camera.data.ortho_scale = HORIZON_CAMERA["ortho_scale"]
        camera.location = HORIZON_CAMERA["location"]
        target = bpy.data.objects.new("Camera_Horizon_Target", None)
        scene.collection.objects.link(target)
        target.location = HORIZON_CAMERA["target"]
        con = camera.constraints.new("TRACK_TO")
        con.target = target
        con.track_axis = "TRACK_NEGATIVE_Z"
        con.up_axis = "UP_Y"
    scene.camera = camera
    bpy.context.view_layer.update()

    trunk = bpy.data.objects.get("boot")
    if trunk is None:
        sys.exit("the master has no boot object")
    trunk_bounds = world_bounds(trunk)
    tree = boot_surface_tree(trunk)

    report = {
        "schema": "trunk-ownership v1",
        "master": os.path.relpath(args.master, REPO_ROOT),
        "camera": HORIZON_CAMERA["name"],
        "canvas": list(CANVAS),
        "trunk_object": "boot",
        "trunk_world_bounds": [round(value, 4) for value in trunk_bounds],
        "objects": [],
    }

    for obj in sorted(bpy.data.objects, key=lambda item: item.name):
        if obj.type != "MESH":
            continue
        bounds = world_bounds(obj)
        entry = {
            "name": obj.name,
            "parent": obj.parent.name if obj.parent else None,
            "materials": [slot.material.name for slot in obj.material_slots
                          if slot.material],
            "world_bounds": [round(value, 4) for value in bounds],
            "gap_to_trunk": round(bounds_distance(bounds, trunk_bounds), 4),
            "surface_distance": (None if surface_distance(tree, obj) is None
                                 else round(surface_distance(tree, obj), 4)),
            "projected_bbox": [round(value, 1) for value in
                               project(scene, camera, world_corners(obj))],
        }
        report["objects"].append(entry)

    report["objects"].sort(key=lambda entry: entry["gap_to_trunk"])
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w") as fh:
        json.dump(report, fh, indent=1)
        fh.write("\n")

    print(f"[trunk] trunk bounds {report['trunk_world_bounds']}")
    for entry in report["objects"][:25]:
        print(f"[trunk] gap {entry['gap_to_trunk']:6.3f}  {entry['name']:28s} "
              f"px {entry['projected_bbox']}  mats {entry['materials']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
