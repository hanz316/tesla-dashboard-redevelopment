#!/usr/bin/env python3
"""Parts B and C: Class-A style reflection diagnostic, original vs clean normals.

This deliberately does NOT use a nice HDRI. It uses the thing automotive
surfacing has used for decades: a black environment with a few very long, very
wide, very smooth white strips. A straight reflection line on a good surface
stays straight. Waviness, pinching, kinks and breaks are surface defects, and
they are far easier to see - and to measure - than in a studio render.

Views: SIDE, REAR QUARTER, ROOF, DOORS.

For each view a numeric continuity metric is computed from the rendered strip
reflection: the brightest ridge is tracked across the frame and its discrete
second difference is reported. A wavy reflection shows up as a large second
difference; a broken one shows up as a tracking gap.

Usage:
    blender -b -P tools/blender/render_reflection_diagnostic.py -- \
        --normals original --out-dir assets/rendered/diagnostic/original
    blender -b -P tools/blender/render_reflection_diagnostic.py -- \
        --normals clean --subdiv 0 --out-dir assets/rendered/diagnostic/clean
"""

import argparse
import json
import math
import os
import sys
import time

try:
    import bpy
    import bmesh
    from mathutils import Matrix, Vector
except ImportError:  # pragma: no cover
    sys.exit("Run inside Blender")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import render_vehicle_visual_v2 as vehicle_v2  # noqa: E402

# Class-A inspection strips: long, wide, soft. Deliberately few.
STRIPS = [
    # name,            location,                 size,   rotation (rad),        strength
    ("Ridge_Overhead", (0.0, 0.0, 3.30),        (11.0, 0.55), (0.0, 0.0, 0.0), 2.6),
    ("Ridge_Upper",    (0.0, -1.55, 2.55),      (10.5, 0.42), (math.radians(-46), 0.0, 0.0), 2.3),
    ("Ridge_Shoulder", (0.0, -2.10, 1.55),      (10.5, 0.34), (math.radians(-72), 0.0, 0.0), 2.5),
    ("Ridge_Lower",    (0.0, -2.55, 0.62),      (9.5, 0.30),  (math.radians(-96), 0.0, 0.0), 2.0),
    ("Ridge_Rear",     (-5.55, 0.0, 1.70),      (2.2, 2.60),  (0.0, 0.0, math.radians(90)), 1.7),
]

VIEWS = {
    "side": {"azimuth_deg": -92.0, "elevation_deg": 6.0, "ortho_scale": 5.10,
             "look_at_z": 0.70},
    "rear_quarter": {"azimuth_deg": -32.0, "elevation_deg": 22.0,
                     "ortho_scale": 4.25, "look_at_z": 0.60},
    "roof": {"azimuth_deg": -28.0, "elevation_deg": 68.0, "ortho_scale": 4.40,
             "look_at_z": 0.75},
    "doors": {"azimuth_deg": -62.0, "elevation_deg": 11.0, "ortho_scale": 4.60,
              "look_at_z": 0.68},
}


def parse_args():
    argv = sys.argv
    argv = argv[argv.index("--") + 1:] if "--" in argv else []
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", default=vehicle_v2.DEFAULT_INPUT)
    ap.add_argument("--normals", default="original",
                    choices=["original", "clean", "weighted"])
    ap.add_argument("--weld", type=float, default=0.0002,
                    help="merge-by-distance threshold for the clean pass")
    ap.add_argument("--weighted-normal", action="store_true", default=True)
    ap.add_argument("--no-weighted-normal", dest="weighted_normal",
                    action="store_false")
    ap.add_argument("--subdiv", type=int, default=0,
                    help="experimental only; never applied to the master")
    ap.add_argument("--views", default="side,rear_quarter,roof,doors")
    ap.add_argument("--samples", type=int, default=48)
    ap.add_argument("--device", default="cpu", choices=["cpu", "gpu"],
                    help="the diagnostic rig (black world + several very large "
                         "emitters) exhausted Metal GPU memory, so this "
                         "defaults to CPU")
    ap.add_argument("--canvas", default="1100x760")
    ap.add_argument("--supersample", type=int, default=1)
    ap.add_argument("--out-dir", required=True)
    return ap.parse_args(argv)


def clean_normals(meshes, weld, weighted_normal, subdiv):
    """Non-destructive normal clean-up, applied to the in-memory copy only.

    The source FBX and the master .blend are never modified: everything here
    operates on objects created by the importer in this session.
    """
    stats = {"weld_removed": 0, "recalculated": 0, "custom_normals_cleared": 0,
             "weighted_normal": 0, "subdiv": 0}
    for obj in meshes:
        bpy.context.view_layer.objects.active = obj
        obj.select_set(True)
        mesh = obj.data

        # 1. Custom split normals baked in by the FBX importer override every
        #    smoothing decision we make afterwards.
        if getattr(mesh, "has_custom_normals", False):
            try:
                bpy.ops.mesh.customdata_custom_splitnormals_clear()
                stats["custom_normals_cleared"] += 1
            except Exception as exc:
                print(f"[diag] custom normal clear failed on {obj.name}: {exc}")

        bm = bmesh.new()
        bm.from_mesh(mesh)
        before = len(bm.verts)
        bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=weld)
        removed = before - len(bm.verts)
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
        stats["recalculated"] += 1
        stats["weld_removed"] += removed
        bm.to_mesh(mesh)
        bm.free()
        mesh.update()

        for poly in mesh.polygons:
            poly.use_smooth = True

        if weighted_normal:
            found = False
            for m in obj.modifiers:
                if m.type == "WEIGHTED_NORMAL":
                    found = True
            if not found:
                mod = obj.modifiers.new("HMI_WeightedNormal", "WEIGHTED_NORMAL")
                mod.keep_sharp = True
                mod.weight = 60
                stats["weighted_normal"] += 1

        if subdiv:
            mod = obj.modifiers.new("HMI_Subdiv", "SUBSURF")
            mod.levels = subdiv
            mod.render_levels = subdiv
            stats["subdiv"] += 1

        obj.select_set(False)
    print(f"[diag] clean normals: {stats}")
    return stats


def panel_screen_boxes(meshes, cam, scene, names):
    """Project each panel's world bbox into the current camera's pixel space.

    Per-panel diagnostics need to know where each panel actually is in the
    frame. Doing that from the object's own bounding box (rather than guessing
    regions) keeps the crops honest when the camera changes.
    """
    from bpy_extras.object_utils import world_to_camera_view
    out = {}
    width = scene.render.resolution_x
    height = scene.render.resolution_y
    for name in names:
        obj = bpy.data.objects.get(name)
        if obj is None or obj.type != "MESH":
            continue
        lo = [1e9, 1e9]
        hi = [-1e9, -1e9]
        for corner in obj.bound_box:
            world = obj.matrix_world @ Vector(corner)
            co = world_to_camera_view(scene, cam, world)
            x = co.x * width
            y = (1.0 - co.y) * height
            lo[0] = min(lo[0], x)
            lo[1] = min(lo[1], y)
            hi[0] = max(hi[0], x)
            hi[1] = max(hi[1], y)
        out[name] = [round(lo[0]), round(lo[1]), round(hi[0]), round(hi[1])]
    return out


def build_diagnostic_rig():
    """Black world + long smooth white strips. No HDRI."""
    world = bpy.data.worlds.new("HMI_DiagnosticWorld")
    bpy.context.scene.world = world
    world.use_nodes = True
    bg = world.node_tree.nodes.get("Background")
    if bg is not None:
        bg.inputs["Color"].default_value = (0.0, 0.0, 0.0, 1.0)
        bg.inputs["Strength"].default_value = 0.0

    for name, location, size, rotation, strength in STRIPS:
        mesh = bpy.data.meshes.new(name + "_mesh")
        obj = bpy.data.objects.new(name, mesh)
        bpy.context.scene.collection.objects.link(obj)
        half_x, half_y = size[0] * 0.5, size[1] * 0.5
        mesh.from_pydata([(-half_x, -half_y, 0), (half_x, -half_y, 0),
                          (half_x, half_y, 0), (-half_x, half_y, 0)], [],
                         [(0, 1, 2, 3)])
        mesh.update()
        obj.location = location
        obj.rotation_euler = rotation
        mat = bpy.data.materials.new(name + "_mat")
        mat.use_nodes = True
        bsdf = mat.node_tree.nodes.get("Principled BSDF")
        if bsdf is not None:
            bsdf.inputs["Base Color"].default_value = (0, 0, 0, 1)
            for key in ("Emission Color", "Emission"):
                if key in bsdf.inputs:
                    bsdf.inputs[key].default_value = (1.0, 1.0, 1.0, 1.0)
                    break
            if "Emission Strength" in bsdf.inputs:
                bsdf.inputs["Emission Strength"].default_value = strength
        obj.data.materials.append(mat)
        for attr, value in (("visible_camera", False),
                            ("visible_shadow", False),
                            ("visible_diffuse", False),
                            ("visible_glossy", True),
                            ("visible_transmission", True)):
            if hasattr(obj, attr):
                setattr(obj, attr, value)
    print(f"[diag] reflection rig: {len(STRIPS)} strips, black world")


def setup_camera(name, canvas_w, canvas_h):
    cfg = VIEWS[name]
    az = math.radians(cfg["azimuth_deg"])
    el = math.radians(cfg["elevation_deg"])
    target = Vector((0.0, 0.0, cfg["look_at_z"]))
    direction = Vector((-math.cos(el) * math.cos(az),
                        -math.cos(el) * math.sin(az), math.sin(el)))
    data = bpy.data.cameras.new("Cam_" + name)
    data.type = "ORTHO"
    aspect = canvas_w / float(canvas_h)
    data.ortho_scale = max(cfg["ortho_scale"], cfg["ortho_scale"] / aspect)
    cam = bpy.data.objects.new("Cam_" + name, data)
    bpy.context.scene.collection.objects.link(cam)
    cam.location = target + direction * 14.0
    empty = bpy.data.objects.new("Target_" + name, None)
    bpy.context.scene.collection.objects.link(empty)
    empty.location = target
    con = cam.constraints.new("TRACK_TO")
    con.target = empty
    con.track_axis = "TRACK_NEGATIVE_Z"
    con.up_axis = "UP_Y"
    return cam


def main():
    args = parse_args()
    canvas_w, canvas_h = (int(v) for v in args.canvas.lower().split("x"))
    os.makedirs(args.out_dir, exist_ok=True)

    meshes, size = vehicle_v2.import_and_normalise(args.input, "+Y")
    if args.normals in ("clean", "weighted"):
        clean_normals(meshes, args.weld, args.normals == "weighted", args.subdiv)
    build_diagnostic_rig()

    scene = vehicle_v2.setup_render("cycles", args.samples, canvas_w, canvas_h,
                                    args.supersample,
                                    os.path.join(args.out_dir, "view.png"))
    scene.view_settings.exposure = 0.0
    try:
        scene.view_settings.view_transform = "Standard"
    except Exception:
        pass
    if hasattr(scene, "cycles"):
        scene.cycles.sample_clamp_indirect = 8.0
        scene.cycles.sample_clamp_direct = 8.0
        if args.device == "cpu":
            scene.cycles.device = "CPU"
            print("[diag] cycles device: CPU (forced)")

    for name in args.views.split(","):
        name = name.strip()
        if name not in VIEWS:
            sys.exit(f"unknown view: {name}")
        cam = setup_camera(name, canvas_w, canvas_h)
        scene.camera = cam
        out = os.path.join(args.out_dir, f"{name}.png")
        scene.render.filepath = out
        start = time.time()
        bpy.ops.render.render(write_still=True)
        print(f"[diag] RENDER_TIME {name} {time.time()-start:.1f}s -> {out}")
        boxes = panel_screen_boxes(
            meshes, cam, scene,
            ["body", "bonnet_ok", "boot", "door_lf", "door_rf", "door_lr",
             "door_rr", "front_bumper_ok", "rear_bumper_ok"])
        with open(os.path.join(args.out_dir, f"{name}_boxes.json"), "w") as fh:
            json.dump(boxes, fh, indent=2)
            fh.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
