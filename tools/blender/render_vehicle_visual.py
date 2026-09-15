#!/usr/bin/env python3
"""Render the MODEL A master as a high-quality static HMI vehicle visual.

NON-DESTRUCTIVE: the source FBX is only read. Normalisation and material
replacement happen in memory; nothing is written back to the model.

Produces a transparent RGBA render of the car on the HMI lighting rig with
a selectable body-colour preset and camera preset, for contact-sheet
comparison.

Usage:
    blender -b -P tools/blender/render_vehicle_visual.py -- \\
        --body silver01 --camera camA --out render.png
"""

import argparse
import math
import os
import sys

try:
    import bpy
    from mathutils import Matrix, Vector
except ImportError:  # pragma: no cover
    sys.exit("Run inside Blender")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import hmi_materials  # noqa: E402

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
DEFAULT_INPUT = os.path.join(REPO_ROOT, "assets", "source", "download",
                             "model_a_ameer", "source", "tesla_car1.fbx")

MODEL3_LENGTH_M = 4.694

# --- camera presets ---------------------------------------------------------
# azimuth: degrees from the rear axis (0 = directly behind), toward the
#          visible flank. elevation: degrees above horizontal.
CAMERA_PRESETS = {
    "camA": {
        "label": "CAM A (baseline angle)",
        "azimuth_deg": 34.0, "elevation_deg": 29.0,
        "ortho_scale": 4.30, "look_at_z": 0.62, "distance": 14.0,
    },
    "camB": {
        "label": "CAM B (lower, more mass)",
        "azimuth_deg": 38.0, "elevation_deg": 19.0,
        "ortho_scale": 4.15, "look_at_z": 0.58, "distance": 14.0,
    },
    "camC": {
        "label": "CAM C (between, more rear)",
        "azimuth_deg": 27.0, "elevation_deg": 24.0,
        "ortho_scale": 4.25, "look_at_z": 0.60, "distance": 14.0,
    },
}


def parse_args():
    argv = sys.argv
    argv = argv[argv.index("--") + 1:] if "--" in argv else []
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", default=DEFAULT_INPUT)
    ap.add_argument("--body", default="silver01",
                    choices=sorted(hmi_materials.BODY_PRESETS))
    ap.add_argument("--camera", default="camA",
                    choices=sorted(CAMERA_PRESETS))
    ap.add_argument("--out", required=True)
    ap.add_argument("--canvas", default="1100x760")
    ap.add_argument("--supersample", type=int, default=2)
    ap.add_argument("--samples", type=int, default=96)
    ap.add_argument("--nose", default="+Y")
    ap.add_argument("--save-blend", default=None,
                    help="also save the prepared scene as a .blend master "
                         "(normalised + HMI materials + rig). Kept local: the "
                         "source model's licence does not allow redistribution.")
    return ap.parse_args(argv)


def import_and_normalise(path, nose_axis):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.fbx(filepath=path)
    meshes = [o for o in bpy.data.objects if o.type == "MESH"]
    if not meshes:
        sys.exit("no meshes imported")

    # Imported assets may arrive hidden (see docs/MODEL3_AB_EVALUATION.md §15).
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
    scale = MODEL3_LENGTH_M / max((hi - lo).x, 1e-6)
    scale_m = Matrix.Scale(scale, 4)
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


def setup_hmi_lighting():
    """HMI_Studio_Lighting: key / fill / rim / top strip + dark world.

    Tuned so the roofline, shoulder line, rear quarter, door contour and
    wheel arches read against a #080D12 dashboard background. Deliberately
    few lights and almost no environment texture.
    """

    def area(name, location, energy, size, rot, shape="SQUARE"):
        bpy.ops.object.light_add(type="AREA", location=location)
        light = bpy.context.active_object
        light.name = name
        light.data.energy = energy
        light.data.size = size
        light.data.shape = shape
        if shape == "RECTANGLE":
            light.data.size_y = size * 0.22
        light.rotation_euler = rot
        return light

    # Key: broad soft source above/front-left of the visible flank.
    area("HMI_Key", (5.0, -5.2, 6.2), 1500.0, 7.0,
         (math.radians(42), 0, math.radians(52)))
    # Fill: dim, opposite side, keeps the dark side readable without flattening.
    area("HMI_Fill", (-4.2, 6.4, 3.2), 420.0, 9.0,
         (math.radians(74), 0, math.radians(-142)))
    # Rim: from behind/above to outline the roofline and rear quarter.
    area("HMI_Rim", (-7.4, -3.4, 4.0), 1100.0, 5.0,
         (math.radians(78), 0, math.radians(-64)))
    # Top strip: long thin source that draws the shoulder/roof highlight line.
    area("HMI_Top", (0.2, -0.6, 7.4), 900.0, 9.0,
         (0, 0, 0), shape="RECTANGLE")

    world = bpy.data.worlds.new("HMI_World")
    bpy.context.scene.world = world
    world.use_nodes = True
    bg = world.node_tree.nodes.get("Background")
    if bg is not None:
        bg.inputs["Color"].default_value = (0.012, 0.016, 0.021, 1.0)
        if "Strength" in bg.inputs:
            bg.inputs["Strength"].default_value = 1.0


def setup_camera(preset, canvas_w, canvas_h):
    cfg = CAMERA_PRESETS[preset]
    az = math.radians(cfg["azimuth_deg"])
    el = math.radians(cfg["elevation_deg"])
    target = Vector((0.0, 0.0, cfg["look_at_z"]))

    direction = Vector((
        -math.cos(el) * math.cos(az),
        -math.cos(el) * math.sin(az),
        math.sin(el),
    ))

    cam_data = bpy.data.cameras.new("Camera_Horizon")
    cam_data.type = "ORTHO"
    aspect = canvas_w / float(canvas_h)
    base = cfg["ortho_scale"]
    cam_data.ortho_scale = max(base, base / aspect)
    cam = bpy.data.objects.new("Camera_Horizon", cam_data)
    bpy.context.scene.collection.objects.link(cam)
    cam.location = target + direction * cfg["distance"]

    target_obj = bpy.data.objects.new("Camera_Horizon_Target", None)
    bpy.context.scene.collection.objects.link(target_obj)
    target_obj.location = target
    con = cam.constraints.new("TRACK_TO")
    con.target = target_obj
    con.track_axis = "TRACK_NEGATIVE_Z"
    con.up_axis = "UP_Y"
    bpy.context.scene.camera = cam
    return cfg


def setup_render(canvas_w, canvas_h, supersample, samples, out_path):
    scene = bpy.context.scene
    engines = [i.identifier for i in
               scene.render.bl_rna.properties["engine"].enum_items]
    for candidate in ("BLENDER_EEVEE_NEXT", "BLENDER_EEVEE"):
        if candidate in engines:
            scene.render.engine = candidate
            break
    eevee = getattr(scene, "eevee", None)
    if eevee is not None:
        for attr, value in (("taa_render_samples", samples),
                            ("use_raytracing", True),
                            ("use_shadows", True),
                            ("use_volumetric_shadows", False)):
            if hasattr(eevee, attr):
                setattr(eevee, attr, value)

    scene.render.film_transparent = True
    scene.render.resolution_x = canvas_w * supersample
    scene.render.resolution_y = canvas_h * supersample
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGBA"
    scene.render.image_settings.color_depth = "8"
    scene.render.image_settings.compression = 90
    try:
        scene.view_settings.view_transform = "AgX"
    except Exception:
        pass
    scene.view_settings.look = "AgX - Medium High Contrast" \
        if "AgX - Medium High Contrast" in [
            v.name for v in scene.view_settings.bl_rna.properties["look"].enum_items
        ] else scene.view_settings.look
    scene.view_settings.exposure = 0.35
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    scene.render.filepath = out_path
    return scene


def main():
    args = parse_args()
    canvas_w, canvas_h = (int(v) for v in args.canvas.lower().split("x"))

    meshes, size = import_and_normalise(args.input, args.nose)
    mats, roles = hmi_materials.apply_to_meshes(meshes, args.body)
    setup_hmi_lighting()
    cfg = setup_camera(args.camera, canvas_w, canvas_h)
    setup_render(canvas_w, canvas_h, args.supersample, args.samples, args.out)

    print(f"[hmi-render] body={args.body} camera={args.camera} "
          f"({cfg['label']}) az={cfg['azimuth_deg']} el={cfg['elevation_deg']} "
          f"ortho={cfg['ortho_scale']}")
    print(f"[hmi-render] vehicle size after normalise = {size} m")

    if args.save_blend:
        os.makedirs(os.path.dirname(args.save_blend), exist_ok=True)
        bpy.ops.wm.save_as_mainfile(filepath=args.save_blend)
        print(f"[hmi-render] saved master {args.save_blend}")

    bpy.ops.render.render(write_still=True)
    print(f"[hmi-render] wrote {args.out} "
          f"({canvas_w*args.supersample}x{canvas_h*args.supersample})")


if __name__ == "__main__":
    main()
