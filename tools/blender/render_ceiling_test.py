#!/usr/bin/env python3
"""Parts C, D, F, G, H, I, J: the MODEL A quality ceiling test renders.

One fixed environment throughout (Photo Studio 01, HDRI HYBRID, one rig,
exposure 0.10) and one fixed pair of materials except where the test is
specifically about materials.

    --treatment current      as imported, frozen photoreal materials
    --treatment cleaned      normal policy applied (weld/recalc/weighted)
    --treatment remesh       + local voxel retopology of the test panel
    --treatment reference    cleaned + reference paint/glass + light guide
    --treatment hero         the maximum-effort combination

Usage:
    blender -b -P tools/blender/render_ceiling_test.py -- \
        --treatment hero --view production --out hero.png
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
    from mathutils import Vector
except ImportError:  # pragma: no cover
    sys.exit("Run inside Blender")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import hmi_studio_photoreal as photoreal  # noqa: E402
import hmi_studio_reference as reference  # noqa: E402
import hmi_studio_v4 as v4  # noqa: E402
import render_vehicle_visual_v2 as vehicle_v2  # noqa: E402

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
FIXED_HDRI = os.path.join(REPO_ROOT, "assets", "source", "hdri",
                          "photo_studio_01_2k.hdr")

VIEWS = {
    "production": {"az": -32.0, "el": 22.0, "ortho": 4.25,
                   "look": (0.0, 0.0, 0.60)},
    "doors": {"az": -62.0, "el": 11.0, "ortho": 3.10,
              "look": (0.30, 0.0, 0.62)},
    "roof": {"az": -28.0, "el": 62.0, "ortho": 3.60,
             "look": (0.0, 0.0, 0.80)},
    "glass": {"az": -48.0, "el": 34.0, "ortho": 2.60,
              "look": (0.10, 0.0, 0.95)},
    "tail": {"az": -58.0, "el": 10.0, "ortho": 1.70,
             "look": (-2.05, 0.55, 0.75)},
    "seam": {"az": -74.0, "el": 14.0, "ortho": 1.30,
             "look": (0.55, 0.62, 0.85)},
}


def parse_args():
    argv = sys.argv
    argv = argv[argv.index("--") + 1:] if "--" in argv else []
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", default=vehicle_v2.DEFAULT_INPUT)
    ap.add_argument("--treatment", default="current",
                    choices=["current", "cleaned", "remesh", "reference",
                             "reference-nogeom", "hero"])
    ap.add_argument("--view", default="production", choices=sorted(VIEWS))
    ap.add_argument("--panel", default="door_lf")
    ap.add_argument("--voxel", type=float, default=0.008)
    ap.add_argument("--ao-only", action="store_true",
                    help="white diffuse + uniform world: the render becomes an "
                         "ambient-occlusion map of the geometry")
    ap.add_argument("--hdri", default=FIXED_HDRI)
    ap.add_argument("--samples", type=int, default=64)
    ap.add_argument("--canvas", default="1100x760")
    ap.add_argument("--supersample", type=int, default=2)
    ap.add_argument("--exposure", type=float, default=0.10)
    ap.add_argument("--device", default="cpu", choices=["gpu", "cpu"])
    ap.add_argument("--report", default=None)
    ap.add_argument("--out", required=True)
    return ap.parse_args(argv)


def apply_normals(meshes, weighted=True, weld=0.0002):
    welded = 0
    cleared = 0
    for obj in meshes:
        bpy.context.view_layer.objects.active = obj
        obj.select_set(True)
        mesh = obj.data
        if getattr(mesh, "has_custom_normals", False):
            try:
                bpy.ops.mesh.customdata_custom_splitnormals_clear()
                cleared += 1
            except Exception:
                pass
        bm = bmesh.new()
        bm.from_mesh(mesh)
        before = len(bm.verts)
        bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=weld)
        welded += before - len(bm.verts)
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
        bm.to_mesh(mesh)
        bm.free()
        mesh.update()
        for poly in mesh.polygons:
            poly.use_smooth = True
        if weighted:
            mod = obj.modifiers.new("HMI_WeightedNormal", "WEIGHTED_NORMAL")
            mod.keep_sharp = True
            mod.weight = 60
        obj.select_set(False)
    return {"welded": welded, "custom_normals_cleared": cleared}


def silhouette_deviation(obj, mesh_before, samples=1200):
    """How far the remeshed surface moved from the original, in metres.

    Measured against the FULL new vertex cloud, not a decimated sample:
    the first version compared against 400 points and reported a 3.6 cm
    median that was mostly sampling error, not surface movement.
    """
    import numpy as np
    old = np.array([v.co[:] for v in mesh_before.vertices], dtype=np.float32)
    new = np.array([v.co[:] for v in obj.data.vertices], dtype=np.float32)
    if old.size == 0 or new.size == 0:
        return None
    step = max(1, len(old) // samples)
    probe = old[::step]
    best = np.empty(len(probe), dtype=np.float32)
    chunk = 32
    for i in range(0, len(probe), chunk):
        part = probe[i:i + chunk]
        d = np.sqrt(((part[:, None, :] - new[None, :, :]) ** 2).sum(axis=2))
        best[i:i + chunk] = d.min(axis=1)
    devs = np.sort(best)
    return {"median_m": round(float(devs[len(devs) // 2]), 5),
            "p95_m": round(float(devs[int(len(devs) * 0.95)]), 5),
            "max_m": round(float(devs[-1]), 5),
            "probe_verts": int(len(probe)), "new_verts": int(len(new))}


def setup_camera(view, canvas_w, canvas_h):
    cfg = VIEWS[view]
    az, el = math.radians(cfg["az"]), math.radians(cfg["el"])
    target = Vector(cfg["look"])
    direction = Vector((-math.cos(el) * math.cos(az),
                        -math.cos(el) * math.sin(az), math.sin(el)))
    data = bpy.data.cameras.new("Cam_" + view)
    data.type = "ORTHO"
    aspect = canvas_w / float(canvas_h)
    data.ortho_scale = max(cfg["ortho"], cfg["ortho"] / aspect)
    cam = bpy.data.objects.new("Cam_" + view, data)
    bpy.context.scene.collection.objects.link(cam)
    cam.location = target + direction * 14.0
    empty = bpy.data.objects.new("Target_" + view, None)
    bpy.context.scene.collection.objects.link(empty)
    empty.location = target
    con = cam.constraints.new("TRACK_TO")
    con.target = empty
    con.track_axis = "TRACK_NEGATIVE_Z"
    con.up_axis = "UP_Y"
    return cam


def apply_ao_material(meshes):
    mat = bpy.data.materials.new("M_AO_Probe")
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    if bsdf is not None:
        for name in ("Base Color",):
            if name in bsdf.inputs:
                bsdf.inputs[name].default_value = (0.82, 0.82, 0.82, 1.0)
        for name in ("Metallic",):
            if name in bsdf.inputs:
                bsdf.inputs[name].default_value = 0.0
        for name in ("Roughness",):
            if name in bsdf.inputs:
                bsdf.inputs[name].default_value = 0.65
    for obj in meshes:
        obj.data.materials.clear()
        obj.data.materials.append(mat)


def main():
    args = parse_args()
    canvas_w, canvas_h = (int(v) for v in args.canvas.lower().split("x"))
    meshes, size = vehicle_v2.import_and_normalise(args.input, "+Y")
    report = {"treatment": args.treatment, "view": args.view,
              "panel": args.panel}

    if args.treatment in ("cleaned", "remesh", "reference", "hero",
                          "reference-nogeom"):
        report["normals"] = apply_normals(meshes)

    if args.treatment == "remesh":
        obj = bpy.data.objects.get(args.panel)
        if obj is not None:
            before = obj.data.copy()
            reference.local_remesh(obj, voxel_size=args.voxel)
            report["remesh"] = {
                "panel": args.panel,
                "voxel_size_m": args.voxel,
                "faces_before": len(before.polygons),
                "faces_after": len(obj.data.polygons),
            }
            dev = silhouette_deviation(obj, before)
            report["remesh"]["silhouette_deviation"] = dev
            print(f"[ceiling] remesh {args.panel}: "
                  f"{len(before.polygons)} -> {len(obj.data.polygons)} faces, "
                  f"silhouette deviation {dev}")

    # Materials
    if args.treatment in ("current", "cleaned", "remesh"):
        photoreal.apply_photoreal_materials(meshes, "silver_photoreal")
    else:
        # v4 structure, then overwrite paint + glass with the reference shaders
        v4.apply_v4_materials(meshes, paint="d", silver="neutral")
        paint = reference.build_reference_paint()
        glass = {k: reference.build_reference_glass(k)
                 for k in ("roof", "front", "side", "rear")}
        import hmi_materials
        for obj in meshes:
            for slot in obj.material_slots:
                original = slot.material
                if original is None:
                    continue
                role = hmi_materials.classify(original)
                name = original.name.lower()
                if role == "BODY":
                    slot.material = paint
                elif role == "GLASS":
                    if "glass.1" in name:
                        slot.material = glass["roof"]
                    elif "depan" in name:
                        slot.material = glass["front"]
                    elif "belakang" in name:
                        slot.material = glass["rear"]
                    else:
                        slot.material = glass["side"]

    if args.treatment in ("reference", "hero"):
        guides = reference.add_light_guide(
            ["rear_lights", "rear_lightsl", "rear_lightsr", "light_breake"])
        report["light_guides"] = len(guides)

    if args.ao_only:
        apply_ao_material(meshes)
        report["ao_only"] = True

    if args.ao_only:
        world = bpy.data.worlds.new("AO_World")
        bpy.context.scene.world = world
        world.use_nodes = True
        bg = world.node_tree.nodes.get("Background")
        if bg is not None:
            bg.inputs["Color"].default_value = (1.0, 1.0, 1.0, 1.0)
            bg.inputs["Strength"].default_value = 1.0
    else:
        if not os.path.isfile(args.hdri):
            sys.exit(f"HDRI not found: {args.hdri}")
        photoreal.build_hdri_world(args.hdri, 1.0, 0.0)
        photoreal.build_hybrid_lights(1.0, 2.0)

    cam = setup_camera(args.view, canvas_w, canvas_h)
    scene = vehicle_v2.setup_render("cycles", args.samples, canvas_w,
                                    canvas_h, args.supersample, args.out)
    scene.camera = cam
    scene.view_settings.exposure = 0.0 if args.ao_only else args.exposure
    scene.view_settings.gamma = 1.0
    if hasattr(scene, "cycles"):
        scene.cycles.sample_clamp_indirect = 4.0
        scene.cycles.sample_clamp_direct = 6.0
        if args.device == "cpu":
            scene.cycles.device = "CPU"

    print(f"[ceiling] treatment={args.treatment} view={args.view} "
          f"samples={args.samples} ao_only={args.ao_only} "
          f"res={canvas_w*args.supersample}x{canvas_h*args.supersample}")
    start = time.time()
    bpy.ops.render.render(write_still=True)
    elapsed = time.time() - start
    report["render_seconds"] = round(elapsed, 1)
    print(f"[ceiling] RENDER_TIME {elapsed:.1f}s -> {args.out}")
    if args.report:
        os.makedirs(os.path.dirname(args.report), exist_ok=True)
        with open(args.report, "w") as fh:
            json.dump(report, fh, indent=2)
            fh.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
