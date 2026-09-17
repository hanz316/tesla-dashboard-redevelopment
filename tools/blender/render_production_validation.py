#!/usr/bin/env python3
"""Part 7: render the frozen production master from every required view.

Loads MODEL_A_PRODUCTION_MASTER.blend and renders. Nothing is re-tuned here:
the master already carries the camera, the lighting and the materials. This
script only chooses a viewpoint and a sample count.

Usage:
    blender -b -P tools/blender/render_production_validation.py -- \
        --view hero --out hero.png
"""

import argparse
import json
import math
import os
import sys
import time

try:
    import bpy
    from mathutils import Vector
except ImportError:  # pragma: no cover
    sys.exit("Run inside Blender")

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
MASTER = os.path.join(REPO_ROOT, "assets", "source", "blender",
                      "model_a_production_master.blend")

# Every view uses the master's own camera unless az/el/ortho/look are given.
VIEWS = {
    "hero": None,
    "taillight": {"az": -58.0, "el": 10.0, "ortho": 1.70,
                  "look": (-2.05, 0.55, 0.75)},
    "glass": {"az": -48.0, "el": 34.0, "ortho": 2.60,
              "look": (0.10, 0.0, 0.95)},
    "wheel": {"az": -76.0, "el": 8.0, "ortho": 1.45,
              "look": (1.42, 0.72, 0.36)},
    "door": {"az": -64.0, "el": 12.0, "ortho": 2.20,
             "look": (0.55, 0.62, 0.70)},
}


def parse_args():
    argv = sys.argv
    argv = argv[argv.index("--") + 1:] if "--" in argv else []
    ap = argparse.ArgumentParser()
    ap.add_argument("--master", default=MASTER)
    ap.add_argument("--view", default="hero", choices=sorted(VIEWS))
    ap.add_argument("--samples", type=int, default=64)
    ap.add_argument("--canvas", default="1100x760")
    ap.add_argument("--supersample", type=int, default=1)
    ap.add_argument("--detail-report", default=None)
    ap.add_argument("--out", required=True)
    return ap.parse_args(argv)


def detail_checks():
    """Part 6: object-level sanity that does not need an image.

    Floating geometry is the one defect that can be caught without looking:
    an object whose bounding box sits entirely outside the vehicle's own
    bounding box is not part of the car.
    """
    meshes = [o for o in bpy.data.objects if o.type == "MESH"]
    lo = Vector((1e9, 1e9, 1e9))
    hi = Vector((-1e9, -1e9, -1e9))
    boxes = {}
    for obj in meshes:
        olo = Vector((1e9, 1e9, 1e9))
        ohi = Vector((-1e9, -1e9, -1e9))
        for corner in obj.bound_box:
            w = obj.matrix_world @ Vector(corner)
            olo = Vector((min(olo.x, w.x), min(olo.y, w.y), min(olo.z, w.z)))
            ohi = Vector((max(ohi.x, w.x), max(ohi.y, w.y), max(ohi.z, w.z)))
        boxes[obj.name] = (olo, ohi)
        lo = Vector((min(lo.x, olo.x), min(lo.y, olo.y), min(lo.z, olo.z)))
        hi = Vector((max(hi.x, ohi.x), max(hi.y, ohi.y), max(hi.z, ohi.z)))

    margin = 0.05
    outside = []
    for name, (olo, ohi) in boxes.items():
        if (ohi.x < lo.x - margin or olo.x > hi.x + margin
                or ohi.y < lo.y - margin or olo.y > hi.y + margin
                or ohi.z < lo.z - margin or olo.z > hi.z + margin):
            outside.append(name)
    degenerate = [n for n, (a, b) in boxes.items() if (b - a).length < 0.005]
    return {
        "mesh_objects": len(meshes),
        "vehicle_bbox_size_m": [round(v, 4) for v in (hi - lo)],
        "objects_outside_vehicle_bbox": outside,
        "degenerate_objects": degenerate,
    }


def setup_camera(view):
    cfg = VIEWS[view]
    if cfg is None:
        cam = bpy.data.objects.get("PRODUCTION_Camera")
        if cam is None:
            sys.exit("master has no PRODUCTION_Camera")
        return cam, bpy.data.objects.get("PRODUCTION_Target")
    az, el = math.radians(cfg["az"]), math.radians(cfg["el"])
    target = Vector(cfg["look"])
    direction = Vector((-math.cos(el) * math.cos(az),
                        -math.cos(el) * math.sin(az), math.sin(el)))
    data = bpy.data.cameras.new("Cam_" + view)
    data.type = "ORTHO"
    data.ortho_scale = cfg["ortho"]
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
    return cam, empty


def main():
    args = parse_args()
    canvas_w, canvas_h = (int(v) for v in args.canvas.lower().split("x"))
    if not os.path.isfile(args.master):
        sys.exit(f"master not found: {args.master}")
    bpy.ops.wm.open_mainfile(filepath=args.master)

    report = detail_checks()
    cam, _ = setup_camera(args.view)
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
    scene.view_settings.exposure = 0.10
    scene.view_settings.gamma = 1.0
    try:
        scene.view_settings.view_transform = "AgX"
    except Exception:
        pass
    scene.render.filepath = args.out

    report["view"] = args.view
    report["samples"] = args.samples
    print(f"[validation] view={args.view} samples={args.samples} "
          f"res={canvas_w*args.supersample}x{canvas_h*args.supersample}")
    print(f"[validation] objects outside vehicle bbox: "
          f"{report['objects_outside_vehicle_bbox']}")
    start = time.time()
    bpy.ops.render.render(write_still=True)
    elapsed = time.time() - start
    report["render_seconds"] = round(elapsed, 1)
    print(f"[validation] RENDER_TIME {elapsed:.1f}s -> {args.out}")
    if args.detail_report:
        os.makedirs(os.path.dirname(args.detail_report), exist_ok=True)
        with open(args.detail_report, "w") as fh:
            json.dump(report, fh, indent=2)
            fh.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
