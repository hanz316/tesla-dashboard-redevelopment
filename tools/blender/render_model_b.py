#!/usr/bin/env python3
"""Part J: render MODEL B under the exact same conditions as MODEL A.

Deliberately the simplest possible material (one neutral automotive silver on
everything). The comparison is about the MODEL, not about our material work:
if MODEL B needs a better shader to win, it has not won on model quality.

Usage:
    blender -b -P tools/blender/render_model_b.py -- --out out.png
"""

import argparse
import math
import os
import sys
import time

try:
    import bpy
    from mathutils import Matrix, Vector
except ImportError:  # pragma: no cover
    sys.exit("Run inside Blender")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import hmi_studio_photoreal as photoreal  # noqa: E402
import render_vehicle_visual_v2 as vehicle_v2  # noqa: E402

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
DEFAULT_B = os.path.join(REPO_ROOT, "assets", "source", "download",
                         "model_b_wintrez", "teslaMSFullSketchfab001.blend")
FIXED_HDRI = os.path.join(REPO_ROOT, "assets", "source", "hdri",
                          "photo_studio_01_2k.hdr")
MODEL3_LENGTH_M = 4.694


def parse_args():
    argv = sys.argv
    argv = argv[argv.index("--") + 1:] if "--" in argv else []
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", default=DEFAULT_B)
    ap.add_argument("--hdri", default=FIXED_HDRI)
    ap.add_argument("--samples", type=int, default=64)
    ap.add_argument("--canvas", default="1100x760")
    ap.add_argument("--supersample", type=int, default=1)
    ap.add_argument("--exposure", type=float, default=0.10)
    ap.add_argument("--out", required=True)
    return ap.parse_args(argv)


def main():
    args = parse_args()
    canvas_w, canvas_h = (int(v) for v in args.canvas.lower().split("x"))

    bpy.ops.wm.open_mainfile(filepath=args.input)
    for obj in [o for o in bpy.data.objects if o.type in ("CAMERA", "LIGHT")]:
        bpy.data.objects.remove(obj, do_unlink=True)

    meshes = [o for o in bpy.data.objects if o.type == "MESH"]
    if not meshes:
        sys.exit("no meshes in MODEL B")
    for obj in meshes:
        obj.hide_render = False
        obj.hide_viewport = False
    bpy.context.view_layer.update()

    roots = [o for o in bpy.data.objects if o.parent is None] or list(meshes)

    def bounds():
        lo = Vector((1e9, 1e9, 1e9))
        hi = Vector((-1e9, -1e9, -1e9))
        for obj in meshes:
            for corner in obj.bound_box:
                w = obj.matrix_world @ Vector(corner)
                lo = Vector((min(lo.x, w.x), min(lo.y, w.y), min(lo.z, w.z)))
                hi = Vector((max(hi.x, w.x), max(hi.y, w.y), max(hi.z, w.z)))
        return lo, hi

    lo, hi = bounds()
    span = hi - lo
    # MODEL A is normalised with the nose along +X. MODEL B ships rotated, so
    # rotate it the same way or the camera would compare two different angles.
    if span.y > span.x:
        rot = Matrix.Rotation(math.radians(90.0), 4, "Z")
        for obj in roots:
            obj.matrix_world = rot @ obj.matrix_world
        bpy.context.view_layer.update()
        lo, hi = bounds()
        span = hi - lo
    # Longest horizontal axis becomes the car length; MODEL B ships in an
    # arbitrary orientation, so the same normalisation MODEL A gets is applied.
    length = max(span.x, span.y)
    scale = Matrix.Scale(MODEL3_LENGTH_M / max(length, 1e-6), 4)
    for obj in roots:
        obj.matrix_world = scale @ obj.matrix_world
    bpy.context.view_layer.update()

    lo, hi = bounds()
    centre = (lo + hi) * 0.5
    shift = Matrix.Translation((-centre.x, -centre.y, -lo.z))
    for obj in roots:
        obj.matrix_world = shift @ obj.matrix_world
    bpy.context.view_layer.update()
    lo, hi = bounds()
    print(f"[modelb] normalised size {[round(v, 3) for v in (hi - lo)]}, "
          f"{len(meshes)} meshes")

    # One neutral automotive silver on everything, so the comparison is about
    # geometry and surface, not about our material pipeline.
    silver = photoreal.build_paint("silver_photoreal")
    for obj in meshes:
        obj.data.materials.clear()
        obj.data.materials.append(silver)

    photoreal.build_hdri_world(args.hdri, 1.0, 0.0)
    photoreal.build_hybrid_lights(1.0, 2.0)

    cfg = vehicle_v2.CAMERA_PRESETS["v2a"]
    az, el = math.radians(cfg["azimuth_deg"]), math.radians(cfg["elevation_deg"])
    target = Vector((0.0, 0.0, cfg["look_at_z"]))
    direction = Vector((-math.cos(el) * math.cos(az),
                        -math.cos(el) * math.sin(az), math.sin(el)))
    data = bpy.data.cameras.new("Cam")
    data.type = "ORTHO"
    aspect = canvas_w / float(canvas_h)
    data.ortho_scale = max(cfg["ortho_scale"], cfg["ortho_scale"] / aspect)
    cam = bpy.data.objects.new("Cam", data)
    bpy.context.scene.collection.objects.link(cam)
    cam.location = target + direction * 14.0
    empty = bpy.data.objects.new("Target", None)
    bpy.context.scene.collection.objects.link(empty)
    empty.location = target
    con = cam.constraints.new("TRACK_TO")
    con.target = empty
    con.track_axis = "TRACK_NEGATIVE_Z"
    con.up_axis = "UP_Y"

    scene = bpy.context.scene
    scene.camera = cam
    scene.render.engine = "CYCLES"
    scene.cycles.samples = args.samples
    scene.cycles.use_denoising = True
    scene.cycles.device = "CPU"
    scene.cycles.sample_clamp_indirect = 4.0
    scene.cycles.sample_clamp_direct = 6.0
    scene.render.film_transparent = True
    scene.render.resolution_x = canvas_w * args.supersample
    scene.render.resolution_y = canvas_h * args.supersample
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGBA"
    scene.view_settings.exposure = args.exposure
    scene.view_settings.gamma = 1.0
    try:
        scene.view_settings.view_transform = "AgX"
    except Exception:
        pass
    scene.render.filepath = args.out

    print(f"[modelb] samples={args.samples} "
          f"res={canvas_w*args.supersample}x{canvas_h*args.supersample}")
    start = time.time()
    bpy.ops.render.render(write_still=True)
    print(f"[modelb] RENDER_TIME {time.time()-start:.1f}s -> {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
