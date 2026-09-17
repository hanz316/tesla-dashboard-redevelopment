#!/usr/bin/env python3
"""Material / geometry diagnostic renders (Parts D-L).

One fixed environment for the whole round: Photo Studio 01, HDRI HYBRID, one
shared rig, exposure 0.10. The point is to compare MATERIAL and GEOMETRY, not
environments, so nothing else is allowed to vary between the columns.

Usage:
    blender -b -P tools/blender/render_material_study.py -- \
        --setup both --out out.png
"""

import argparse
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
import hmi_studio_v4 as v4  # noqa: E402
import render_vehicle_visual_v2 as vehicle_v2  # noqa: E402
import render_vehicle_visual_v3 as vehicle_v3  # noqa: E402

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
FIXED_HDRI = os.path.join(REPO_ROOT, "assets", "source", "hdri",
                          "photo_studio_01_2k.hdr")

VIEWS = {
    "production": {"az": -32.0, "el": 22.0, "ortho": 4.25,
                   "look": (0.0, 0.0, 0.60)},
    "glass": {"az": -48.0, "el": 34.0, "ortho": 2.60,
              "look": (0.10, 0.0, 0.95)},
    "tail": {"az": -58.0, "el": 10.0, "ortho": 1.70,
             "look": (-2.05, 0.55, 0.75)},
    "wheel": {"az": -76.0, "el": 8.0, "ortho": 1.45,
              "look": (1.42, 0.72, 0.36)},
}


def parse_args():
    argv = sys.argv
    argv = argv[argv.index("--") + 1:] if "--" in argv else []
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", default=vehicle_v2.DEFAULT_INPUT)
    ap.add_argument("--setup", default="baseline",
                    choices=["baseline", "geom", "material", "both"])
    ap.add_argument("--paint", default="d", choices=sorted(v4.PAINTS))
    ap.add_argument("--silver", default="neutral", choices=sorted(v4.SILVERS))
    ap.add_argument("--clearcoat-mode", default="combined",
                    choices=["combined", "basecoat", "clearcoat"])
    ap.add_argument("--view", default="production", choices=sorted(VIEWS))
    ap.add_argument("--hdri", default=FIXED_HDRI)
    ap.add_argument("--samples", type=int, default=64)
    ap.add_argument("--canvas", default="1100x760")
    ap.add_argument("--supersample", type=int, default=2)
    ap.add_argument("--exposure", type=float, default=0.10)
    ap.add_argument("--fill-scale", type=float, default=2.0)
    ap.add_argument("--device", default="gpu", choices=["gpu", "cpu"])
    ap.add_argument("--format", default="png", choices=["png", "exr"],
                    help="exr writes the linear values BEFORE the display "
                         "transform, for the Part K colour-management audit")
    ap.add_argument("--out", required=True)
    return ap.parse_args(argv)


def clean_geometry(meshes, weld=0.0002):
    """The ORIGINAL side of the Part C A/B: welds, recalculates and replaces
    the importer's custom split normals with weighted normals. In-memory only;
    the FBX and the master .blend are never written."""
    stats = {"welded": 0, "custom_normals_cleared": 0, "weighted": 0}
    for obj in meshes:
        bpy.context.view_layer.objects.active = obj
        obj.select_set(True)
        mesh = obj.data
        if getattr(mesh, "has_custom_normals", False):
            try:
                bpy.ops.mesh.customdata_custom_splitnormals_clear()
                stats["custom_normals_cleared"] += 1
            except Exception:
                pass
        bm = bmesh.new()
        bm.from_mesh(mesh)
        before = len(bm.verts)
        bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=weld)
        stats["welded"] += before - len(bm.verts)
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
        bm.to_mesh(mesh)
        bm.free()
        mesh.update()
        for poly in mesh.polygons:
            poly.use_smooth = True
        mod = obj.modifiers.new("HMI_WeightedNormal", "WEIGHTED_NORMAL")
        mod.keep_sharp = True
        mod.weight = 60
        stats["weighted"] += 1
        obj.select_set(False)
    print(f"[study] geometry clean: {stats}")
    return stats


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


def main():
    args = parse_args()
    canvas_w, canvas_h = (int(v) for v in args.canvas.lower().split("x"))
    meshes, size = vehicle_v2.import_and_normalise(args.input, "+Y")

    if args.setup in ("geom", "both"):
        clean_geometry(meshes)

    if args.setup in ("material", "both"):
        v4.apply_v4_materials(meshes, paint=args.paint, silver=args.silver,
                              mode=args.clearcoat_mode)
    else:
        import hmi_studio_photoreal
        hmi_studio_photoreal.apply_photoreal_materials(meshes,
                                                       "silver_photoreal")

    if not os.path.isfile(args.hdri):
        sys.exit(f"HDRI not found: {args.hdri}")
    photoreal.build_hdri_world(args.hdri, 1.0, 0.0)
    photoreal.build_hybrid_lights(1.0, args.fill_scale)

    cam = setup_camera(args.view, canvas_w, canvas_h)
    scene = vehicle_v2.setup_render("cycles", args.samples, canvas_w,
                                    canvas_h, args.supersample, args.out)
    scene.camera = cam
    scene.view_settings.exposure = args.exposure
    scene.view_settings.gamma = 1.0
    if hasattr(scene, "cycles"):
        scene.cycles.sample_clamp_indirect = 4.0
        scene.cycles.sample_clamp_direct = 6.0
        if args.device == "cpu":
            scene.cycles.device = "CPU"
    if args.format == "exr":
        scene.render.image_settings.file_format = "OPEN_EXR"
        scene.render.image_settings.color_depth = "32"
        scene.render.image_settings.color_mode = "RGBA"

    print(f"[study] setup={args.setup} paint={args.paint} "
          f"silver={args.silver} clearcoat={args.clearcoat_mode} "
          f"view={args.view} samples={args.samples} "
          f"res={canvas_w*args.supersample}x{canvas_h*args.supersample} "
          f"exposure={args.exposure}")
    start = time.time()
    bpy.ops.render.render(write_still=True)
    print(f"[study] RENDER_TIME {time.time() - start:.1f}s -> {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
