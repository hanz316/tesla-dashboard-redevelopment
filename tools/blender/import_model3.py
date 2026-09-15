#!/usr/bin/env python3
"""Import + normalize a Tesla Model 3 asset into model3_master.blend.

Accepts FBX / OBJ / GLB / GLTF / BLEND and performs deterministic
normalization so every downstream step (Camera_Horizon, actions, renders)
is repeatable:

* units    -> meters
* scale    -> real Model 3 length (4.694 m) unless --no-fit
* rotation -> nose along +X, up = +Z
* position -> centered on X/Y, wheels resting on Z = 0
* naming   -> canonical part names via tools/assets/part_mapping.json

It NEVER performs destructive mesh surgery. If parts (doors, frunk, trunk)
are not separate objects it writes a report and stops, so a human can decide.

Usage:
    blender -b -P tools/blender/import_model3.py -- --input model.glb
    blender -b -P tools/blender/import_model3.py -- --input model.fbx --no-fit
"""

import argparse
import json
import math
import os
import sys

try:
    import bpy
    from mathutils import Vector
except ImportError:  # pragma: no cover
    sys.exit("Run inside Blender: blender -b -P tools/blender/import_model3.py")

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
DEFAULT_OUT = os.path.join(REPO_ROOT, "assets", "source", "blender",
                           "model3_master.blend")
MAPPING_PATH = os.path.join(REPO_ROOT, "tools", "assets", "part_mapping.json")
REPORT_PATH = os.path.join(REPO_ROOT, "assets", "source", "blender",
                           "model3_import_report.json")

MODEL3_LENGTH_M = 4.694      # Tesla Model 3 overall length
MODEL3_WIDTH_M = 1.849


def parse_args():
    argv = sys.argv
    argv = argv[argv.index("--") + 1:] if "--" in argv else []
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True)
    ap.add_argument("--out", default=DEFAULT_OUT)
    ap.add_argument("--no-fit", action="store_true",
                    help="keep the source scale instead of fitting to 4.694 m")
    ap.add_argument("--no-rename", action="store_true")
    return ap.parse_args(argv)


def clear_scene():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    for block in (bpy.data.objects, bpy.data.materials, bpy.data.actions):
        for item in list(block):
            block.remove(item)


def import_asset(path):
    ext = os.path.splitext(path)[1].lower()
    if ext == ".fbx":
        bpy.ops.import_scene.fbx(filepath=path)
    elif ext == ".obj":
        try:
            bpy.ops.wm.obj_import(filepath=path)          # Blender 3.4+
        except AttributeError:
            bpy.ops.import_scene.obj(filepath=path)        # older
    elif ext in (".glb", ".gltf"):
        bpy.ops.import_scene.gltf(filepath=path)
    elif ext == ".blend":
        bpy.ops.wm.open_mainfile(filepath=path)
    else:
        sys.exit(f"unsupported input format: {ext}")
    return [o for o in bpy.data.objects if o.type == "MESH"]


def classify(name, mapping):
    low = name.lower()
    for canonical, tokens in mapping["mappings"].items():
        for token in tokens:
            if token in low:
                return canonical
    return None


def apply_naming(meshes, mapping):
    renamed, unmatched = {}, []
    used = set()
    for obj in meshes:
        canonical = classify(obj.name, mapping)
        if canonical and canonical not in used:
            renamed[obj.name] = canonical
            obj.name = canonical
            used.add(canonical)
        else:
            unmatched.append(obj.name)
    return renamed, unmatched, sorted(used)


def bounds(meshes):
    lo = Vector((1e9, 1e9, 1e9))
    hi = Vector((-1e9, -1e9, -1e9))
    for obj in meshes:
        for corner in obj.bound_box:
            world = obj.matrix_world @ Vector(corner)
            lo = Vector((min(lo.x, world.x), min(lo.y, world.y), min(lo.z, world.z)))
            hi = Vector((max(hi.x, world.x), max(hi.y, world.y), max(hi.z, world.z)))
    return lo, hi


def normalize(meshes, fit=True):
    """Scale to real size, center on X/Y, rest wheels on Z=0, nose along +X."""
    lo, hi = bounds(meshes)
    size = hi - lo
    longest = max(size.x, size.y, size.z)
    if longest <= 0:
        return {}

    # Orient: the longest horizontal axis should be X (vehicle length).
    rotated = False
    if size.y > size.x:
        for obj in meshes:
            obj.rotation_euler.rotate_axis("Z", math.radians(90.0))
        bpy.context.view_layer.update()
        lo, hi = bounds(meshes)
        size = hi - lo
        rotated = True

    scale = 1.0
    if fit:
        length = max(size.x, size.y)
        if length > 0:
            scale = MODEL3_LENGTH_M / length

    for obj in meshes:
        obj.scale = [s * scale for s in obj.scale]
        obj.location = [c * scale for c in obj.location]
    bpy.context.view_layer.update()

    lo, hi = bounds(meshes)
    center = (lo + hi) * 0.5
    for obj in meshes:
        obj.location.x -= center.x
        obj.location.y -= center.y
        obj.location.z -= lo.z          # wheels on the ground plane
    bpy.context.view_layer.update()

    lo, hi = bounds(meshes)
    return {
        "rotated_90z": rotated,
        "scale_applied": round(scale, 6),
        "final_length_m": round((hi - lo).x, 3),
        "final_width_m": round((hi - lo).y, 3),
        "final_height_m": round((hi - lo).z, 3),
        "ground_offset_m": round(lo.z, 4),
    }


def main():
    args = parse_args()
    mapping = json.load(open(MAPPING_PATH))

    clear_scene()
    meshes = import_asset(args.input)
    if not meshes:
        sys.exit("no mesh objects imported")

    source_names = [o.name for o in meshes]
    renamed, unmatched, canonical_found = ({}, [], [])
    if not args.no_rename:
        renamed, unmatched, canonical_found = apply_naming(meshes, mapping)

    norm = normalize(meshes, fit=not args.no_fit)

    required = ["Body", "Glass", "Interior",
                "Door_FL", "Door_FR", "Door_RL", "Door_RR",
                "Frunk", "Trunk",
                "Wheel_FL", "Wheel_FR", "Wheel_RL", "Wheel_RR",
                "Headlight_L", "Headlight_R", "Taillight_L", "Taillight_R"]
    missing = [r for r in required if r not in canonical_found]

    report = {
        "input": os.path.relpath(args.input, REPO_ROOT),
        "mesh_count": len(meshes),
        "source_names": source_names[:80],
        "renamed": renamed,
        "canonical_found": canonical_found,
        "missing_canonical": missing,
        "unmatched_objects": unmatched[:80],
        "normalization": norm,
        "doors_separated": all(
            d in canonical_found for d in ("Door_FL", "Door_FR", "Door_RL", "Door_RR")),
    }

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=args.out)
    with open(REPORT_PATH, "w") as fh:
        json.dump(report, fh, indent=2)

    print(f"[import] {report['input']} -> {os.path.relpath(args.out, REPO_ROOT)}")
    print(f"[import] meshes={len(meshes)} canonical={len(canonical_found)} "
          f"missing={len(missing)}")
    print(f"[import] normalization={norm}")
    if missing:
        print(f"[import] MISSING canonical parts: {', '.join(missing)}")
    if not report["doors_separated"]:
        print("[import] WARNING: doors are not separate objects. "
              "Do NOT auto-split; review the report first:")
        print(f"         {os.path.relpath(REPORT_PATH, REPO_ROOT)}")


if __name__ == "__main__":
    main()
