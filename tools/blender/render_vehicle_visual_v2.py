#!/usr/bin/env python3
"""Vehicle Visual V2 render: layered paint + reflection studio.

Non-destructive. Reads the MODEL A FBX, normalises in memory, applies the
V2 material set and the virtual reflection studio, then renders with either
EEVEE Next or Cycles for an honest engine comparison.

Usage:
    blender -b -P tools/blender/render_vehicle_visual_v2.py -- \\
        --body silver01 --camera v2a --engine cycles --samples 128 \\
        --out out.png
"""

import argparse
import math
import os
import sys
import time

try:
    import bpy
    import addon_utils
    from mathutils import Matrix, Vector
except ImportError:  # pragma: no cover
    sys.exit("Run inside Blender")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import hmi_materials  # noqa: E402
import hmi_studio_v2  # noqa: E402

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
DEFAULT_INPUT = os.path.join(REPO_ROOT, "assets", "source", "download",
                             "model_a_ameer", "source", "tesla_car1.fbx")
MODEL3_LENGTH_M = 4.694

# Camera finalisation candidates: rear three-quarter, deliberately flatter
# than V1 (less top-down) to read as a premium cockpit 2.5D visualisation
# rather than a map pin or a game car-select shot.
#
# Negative azimuth puts the camera on the +Y side. After the model is
# normalised (nose -> +X, up -> +Z) the +Y side is the DRIVER's side, which is
# where door_lf lives. Measured cost of getting this wrong: with the camera on
# -Y the animated front-left door opens on the far side of the car and only
# 7.5% of the car's pixels change; on +Y it opens toward the viewer and 12.1%
# change. The dashboard has to animate doors the viewer can actually see.
CAMERA_PRESETS = {
    "v2a": {"label": "V2-A (balanced)",
            "azimuth_deg": -32.0, "elevation_deg": 22.0,
            "ortho_scale": 4.25, "look_at_z": 0.60},
    "v2b": {"label": "V2-B (lower, more mass)",
            "azimuth_deg": -36.0, "elevation_deg": 17.0,
            "ortho_scale": 4.15, "look_at_z": 0.56},
    "v2c": {"label": "V2-C (between, more rear)",
            "azimuth_deg": -26.0, "elevation_deg": 20.0,
            "ortho_scale": 4.20, "look_at_z": 0.58},
}


def parse_args():
    argv = sys.argv
    argv = argv[argv.index("--") + 1:] if "--" in argv else []
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", default=DEFAULT_INPUT)
    ap.add_argument("--body", default="silver01",
                    choices=sorted(hmi_studio_v2.BODY_PRESETS_V2))
    ap.add_argument("--camera", default="v2a", choices=sorted(CAMERA_PRESETS))
    ap.add_argument("--engine", default="eevee", choices=["eevee", "cycles"])
    ap.add_argument("--samples", type=int, default=0,
                    help="0 = engine default (eevee 192 / cycles 128)")
    ap.add_argument("--out", required=True)
    ap.add_argument("--canvas", default="1100x760")
    ap.add_argument("--supersample", type=int, default=2)
    ap.add_argument("--nose", default="+Y")
    ap.add_argument("--no-studio", action="store_true",
                    help="skip reflection cards (used to prove they matter)")
    ap.add_argument("--save-blend", default=None)
    return ap.parse_args(argv)


def import_and_normalise(path, nose_axis):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.fbx(filepath=path)
    meshes = [o for o in bpy.data.objects if o.type == "MESH"]
    if not meshes:
        sys.exit("no meshes imported")
    for obj in meshes:
        obj.hide_render = False
        obj.hide_viewport = False

    bpy.context.view_layer.update()
    roots = [o for o in bpy.data.objects if o.parent is None] or list(meshes)
    angle = {"+X": 0.0, "+Y": -90.0, "-Y": 90.0, "-X": 180.0}[nose_axis]
    if angle:
        rot = Matrix.Rotation(math.radians(angle), 4, "Z")
        for obj in roots:
            obj.matrix_world = rot @ obj.matrix_world
        bpy.context.view_layer.update()

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
    scale_m = Matrix.Scale(MODEL3_LENGTH_M / max((hi - lo).x, 1e-6), 4)
    for obj in roots:
        obj.matrix_world = scale_m @ obj.matrix_world
    bpy.context.view_layer.update()

    lo, hi = bounds()
    centre = (lo + hi) * 0.5
    shift = Matrix.Translation((-centre.x, -centre.y, -lo.z))
    for obj in roots:
        obj.matrix_world = shift @ obj.matrix_world
    bpy.context.view_layer.update()

    lo, hi = bounds()
    return meshes, [round((hi - lo).x, 3), round((hi - lo).y, 3),
                    round((hi - lo).z, 3)]


def setup_key_rig():
    """Much softer than V1: the reflection studio now does the shaping."""
    def area(name, loc, energy, size, rot):
        bpy.ops.object.light_add(type="AREA", location=loc)
        light = bpy.context.active_object
        light.name = name
        light.data.energy = energy
        light.data.size = size
        light.rotation_euler = rot
        return light

    area("HMI_Key", (5.0, -5.4, 5.4), 620.0, 8.0,
         (math.radians(46), 0, math.radians(50)))
    area("HMI_Fill", (-4.6, 6.0, 3.0), 190.0, 10.0,
         (math.radians(76), 0, math.radians(-140)))
    area("HMI_Rim", (-7.2, -3.2, 3.6), 420.0, 5.0,
         (math.radians(78), 0, math.radians(-66)))

    world = bpy.data.worlds.new("HMI_World_V2")
    bpy.context.scene.world = world
    world.use_nodes = True
    bg = world.node_tree.nodes.get("Background")
    if bg is not None:
        bg.inputs["Color"].default_value = (0.010, 0.013, 0.018, 1.0)
        if "Strength" in bg.inputs:
            bg.inputs["Strength"].default_value = 1.0


def setup_camera(preset, canvas_w, canvas_h):
    cfg = CAMERA_PRESETS[preset]
    az = math.radians(cfg["azimuth_deg"])
    el = math.radians(cfg["elevation_deg"])
    target = Vector((0.0, 0.0, cfg["look_at_z"]))
    direction = Vector((-math.cos(el) * math.cos(az),
                        -math.cos(el) * math.sin(az),
                        math.sin(el)))

    cam_data = bpy.data.cameras.new("Camera_Horizon")
    cam_data.type = "ORTHO"
    aspect = canvas_w / float(canvas_h)
    base = cfg["ortho_scale"]
    cam_data.ortho_scale = max(base, base / aspect)
    cam = bpy.data.objects.new("Camera_Horizon", cam_data)
    bpy.context.scene.collection.objects.link(cam)
    cam.location = target + direction * 14.0

    target_obj = bpy.data.objects.new("Camera_Horizon_Target", None)
    bpy.context.scene.collection.objects.link(target_obj)
    target_obj.location = target
    con = cam.constraints.new("TRACK_TO")
    con.target = target_obj
    con.track_axis = "TRACK_NEGATIVE_Z"
    con.up_axis = "UP_Y"
    bpy.context.scene.camera = cam
    return cfg


def setup_render(engine, samples, canvas_w, canvas_h, supersample, out_path):
    scene = bpy.context.scene
    if engine == "cycles":
        # Cycles ships as an add-on and is not enabled in a fresh headless
        # session; the engine enum will not even list it until we enable it.
        addon_utils.enable("cycles", default_set=True, persistent=True)
        scene.render.engine = "CYCLES"
        cycles = getattr(scene, "cycles", None)
        if cycles is not None:
            cycles.samples = samples or 128
            cycles.use_denoising = True
            cycles.max_bounces = 8
            cycles.glossy_bounces = 6
            cycles.transmission_bounces = 8
            cycles.transparent_max_bounces = 8
            cycles.use_adaptive_sampling = True
            cycles.adaptive_threshold = 0.01
            # Prefer the Metal GPU when the build exposes it; fall back to
            # CPU silently so the script works on any Mac.
            prefs = bpy.context.preferences.addons.get("cycles")
            if prefs is not None:
                try:
                    prefs.preferences.get_devices()
                    if any(d.type == "METAL" and d.use
                           for d in prefs.preferences.devices):
                        cycles.device = "GPU"
                        print("[v2] cycles device: Metal GPU")
                    else:
                        cycles.device = "CPU"
                        print("[v2] cycles device: CPU")
                except Exception:
                    cycles.device = "CPU"
    else:
        engines = [i.identifier for i in
                   scene.render.bl_rna.properties["engine"].enum_items]
        for candidate in ("BLENDER_EEVEE_NEXT", "BLENDER_EEVEE"):
            if candidate in engines:
                scene.render.engine = candidate
                break
        eevee = getattr(scene, "eevee", None)
        if eevee is not None:
            for attr, value in (("taa_render_samples", samples or 192),
                                ("use_raytracing", True),
                                ("use_shadows", True),
                                ("use_raytracing_options", True)):
                if hasattr(eevee, attr):
                    setattr(eevee, attr, value)
            rt = getattr(eevee, "ray_tracing_options", None)
            if rt is not None and hasattr(rt, "use_denoise"):
                rt.use_denoise = True

    scene.render.film_transparent = True
    scene.render.resolution_x = canvas_w * supersample
    scene.render.resolution_y = canvas_h * supersample
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGBA"
    scene.render.image_settings.compression = 90
    try:
        scene.view_settings.view_transform = "AgX"
    except Exception:
        pass
    scene.view_settings.exposure = 0.30
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    scene.render.filepath = out_path
    return scene


def main():
    args = parse_args()
    canvas_w, canvas_h = (int(v) for v in args.canvas.lower().split("x"))

    meshes, size = import_and_normalise(args.input, args.nose)
    hmi_studio_v2.apply_v2_materials(meshes, args.body)
    setup_key_rig()
    if not args.no_studio:
        cards = hmi_studio_v2.build_reflection_studio()
        print(f"[v2] reflection studio: {len(cards)} cards "
              f"(invisible to camera, visible to glossy rays)")
    cfg = setup_camera(args.camera, canvas_w, canvas_h)
    setup_render(args.engine, args.samples, canvas_w, canvas_h,
                 args.supersample, args.out)

    if args.save_blend:
        os.makedirs(os.path.dirname(args.save_blend), exist_ok=True)
        bpy.ops.wm.save_as_mainfile(filepath=args.save_blend)
        print(f"[v2] saved {args.save_blend}")

    print(f"[v2] body={args.body} camera={args.camera} ({cfg['label']}) "
          f"az={cfg['azimuth_deg']} el={cfg['elevation_deg']} "
          f"ortho={cfg['ortho_scale']}")
    print(f"[v2] engine={args.engine} samples={args.samples or 'default'} "
          f"res={canvas_w*args.supersample}x{canvas_h*args.supersample} "
          f"vehicle={size}")

    start = time.time()
    bpy.ops.render.render(write_still=True)
    elapsed = time.time() - start
    print(f"[v2] RENDER_TIME {elapsed:.1f}s -> {args.out}")


if __name__ == "__main__":
    main()
