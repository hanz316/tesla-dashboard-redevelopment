#!/usr/bin/env python3
"""Fair A/B render of two vehicle models with identical framing.

Normalises any model to: nose along +X, wheels on Z=0, centred on X/Y,
length = 4.694 m (real Model 3), then renders it with the SAME
Camera_Horizon, lighting rig, world, resolution and exposure so two models
can be compared honestly.

Two material modes:
    original  keep the model's own materials (shows material capability)
    unified   override with neutral test materials (shows pure geometry)

Nothing is written back to the source model.

Usage:
    blender -b -P tools/blender/ab_render.py -- \\
        --input model.fbx --nose -Y --mode original \\
        --out out/model_A_original.png --tag A
"""

import argparse
import math
import os
import sys

try:
    import bpy
    from mathutils import Vector
except ImportError:  # pragma: no cover
    sys.exit("Run inside Blender: blender -b -P tools/blender/ab_render.py")

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))

MODEL3_LENGTH_M = 4.694
MODEL3_WIDTH_M = 1.849
MODEL3_HEIGHT_M = 1.443


def parse_args():
    argv = sys.argv
    argv = argv[argv.index("--") + 1:] if "--" in argv else []
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--tag", default="X")
    ap.add_argument("--nose", default="-Y",
                    choices=["+X", "-X", "+Y", "-Y"],
                    help="which world axis the vehicle nose points along")
    ap.add_argument("--mode", default="original",
                    choices=["original", "unified"])
    ap.add_argument("--canvas", default="900x640",
                    help="render canvas in px (supersampled before downscale)")
    ap.add_argument("--supersample", type=int, default=2)
    ap.add_argument("--world-height-m", type=float, default=0.0,
                    help="lift the car if its wheels are below z=0")
    return ap.parse_args(argv)


def load(path):
    ext = os.path.splitext(path)[1].lower()
    bpy.ops.wm.read_factory_settings(use_empty=True)
    if ext == ".fbx":
        bpy.ops.import_scene.fbx(filepath=path)
    elif ext == ".obj":
        try:
            bpy.ops.wm.obj_import(filepath=path)
        except AttributeError:
            bpy.ops.import_scene.obj(filepath=path)
    elif ext in (".glb", ".gltf"):
        bpy.ops.import_scene.gltf(filepath=path)
    elif ext == ".blend":
        bpy.ops.wm.open_mainfile(filepath=path)
        # The file may ship its own camera/lighting rig; remove only those so
        # the A/B comparison uses one shared rig. Meshes/empties are kept.
        for obj in [o for o in bpy.data.objects if o.type in ("LIGHT", "CAMERA")]:
            bpy.data.objects.remove(obj, do_unlink=True)
        for cam in list(bpy.data.cameras):
            bpy.data.cameras.remove(cam)
        for light in list(bpy.data.lights):
            bpy.data.lights.remove(light)
    else:
        sys.exit(f"unsupported input: {ext}")


def mesh_bounds(meshes):
    lo = Vector((1e9, 1e9, 1e9))
    hi = Vector((-1e9, -1e9, -1e9))
    for obj in meshes:
        for corner in obj.bound_box:
            w = obj.matrix_world @ Vector(corner)
            lo = Vector((min(lo.x, w.x), min(lo.y, w.y), min(lo.z, w.z)))
            hi = Vector((max(hi.x, w.x), max(hi.y, w.y), max(hi.z, w.z)))
    return lo, hi


def normalise(meshes, nose_axis):
    """Rotate nose to +X, scale to real length, centre on X/Y, rest on Z=0.

    Transformations are applied as WORLD matrices on root objects only, so
    imported hierarchies (FBX often nests meshes under empties with their own
    rotation) are moved consistently. Using ``obj.rotation_euler`` here is a
    trap: FBX imports commonly carry a 90 deg X rotation, and
    ``rotate_axis`` acts in local space, which silently leaves the vehicle
    sideways.
    """
    from mathutils import Matrix

    # Imported assets frequently arrive with render/viewport visibility off
    # (the wintrez .blend ships 'Full Car Extra' with hide_render=True, which
    # renders an empty frame). Force visibility on in memory only.
    for obj in meshes:
        if obj.hide_render or obj.hide_viewport:
            print(f"[ab] enabling hidden object {obj.name!r} "
                  f"(hide_render={obj.hide_render}, "
                  f"hide_viewport={obj.hide_viewport})")
            obj.hide_render = False
            obj.hide_viewport = False

    bpy.context.view_layer.update()
    roots = [o for o in bpy.data.objects if o.parent is None]
    if not roots:
        roots = list(meshes)

    # Rotate so the nose points along +X.
    angle = {"+X": 0.0, "+Y": -90.0, "-Y": 90.0, "-X": 180.0}[nose_axis]
    if angle:
        rot = Matrix.Rotation(math.radians(angle), 4, "Z")
        for obj in roots:
            obj.matrix_world = rot @ obj.matrix_world
        bpy.context.view_layer.update()

    lo, hi = mesh_bounds(meshes)
    length = max((hi - lo).x, 1e-6)
    scale = MODEL3_LENGTH_M / length
    scale_m = Matrix.Scale(scale, 4)
    for obj in roots:
        obj.matrix_world = scale_m @ obj.matrix_world
    bpy.context.view_layer.update()

    lo, hi = mesh_bounds(meshes)
    centre = (lo + hi) * 0.5
    shift = Matrix.Translation((-centre.x, -centre.y, -lo.z))
    for obj in roots:
        obj.matrix_world = shift @ obj.matrix_world
    bpy.context.view_layer.update()
    lo, hi = mesh_bounds(meshes)
    return {
        "rotation_z_deg": angle,
        "scale": round(scale, 6),
        "final_size": [round((hi - lo).x, 3), round((hi - lo).y, 3),
                       round((hi - lo).z, 3)],
        "ground_z": round(lo.z, 4),
    }


def make_material(name, base, metallic, roughness, emission_strength=0.0,
                  emission_colour=(1, 1, 1, 1)):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    if bsdf is None:
        return mat
    bsdf.inputs["Base Color"].default_value = base
    if "Metallic" in bsdf.inputs:
        bsdf.inputs["Metallic"].default_value = metallic
    if "Roughness" in bsdf.inputs:
        bsdf.inputs["Roughness"].default_value = roughness
    for key in ("Emission Color", "Emission"):
        if key in bsdf.inputs:
            bsdf.inputs[key].default_value = emission_colour
            break
    if "Emission Strength" in bsdf.inputs:
        bsdf.inputs["Emission Strength"].default_value = emission_strength
    return mat


def apply_unified_materials(meshes):
    """Neutral test materials so geometry can be judged independently."""
    silver = make_material("AB_Body", (0.62, 0.64, 0.67, 1.0), 0.85, 0.28)
    glass = make_material("AB_Glass", (0.03, 0.04, 0.06, 1.0), 0.0, 0.08)
    rubber = make_material("AB_Tire", (0.035, 0.035, 0.04, 1.0), 0.0, 0.9)
    graphite = make_material("AB_Rim", (0.16, 0.17, 0.18, 1.0), 0.8, 0.35)
    off = make_material("AB_LightOff", (0.75, 0.76, 0.78, 1.0), 0.2, 0.15)
    trim = make_material("AB_Trim", (0.07, 0.07, 0.08, 1.0), 0.5, 0.45)

    def pick(name):
        low = name.lower()
        if any(k in low for k in ("glass", "kaca", "windscreen", "window")):
            return glass
        if any(k in low for k in ("tire", "tyre", "rubber", "ban")):
            return rubber
        if any(k in low for k in ("rim", "hub", "wheel", "velg")):
            return graphite
        if any(k in low for k in ("light", "lamp", "lens", "break", "brake",
                                  "indicator", "fog", "reflect")):
            return off
        if any(k in low for k in ("black", "trim", "chrome", "silver",
                                  "metal", "interior", "carpet", "belt")):
            return trim
        return silver

    for obj in meshes:
        for slot in obj.material_slots:
            if slot.material:
                slot.material = pick(slot.material.name)
            else:
                slot.material = silver


def setup_camera(meshes, canvas_w, canvas_h):
    """Fixed high rear three-quarter view, framed identically for any model."""
    target = bpy.data.objects.new("AB_Camera_Target", None)
    bpy.context.scene.collection.objects.link(target)
    target.location = (0.0, 0.0, MODEL3_HEIGHT_M * 0.45)

    cam_data = bpy.data.cameras.new("Camera_Horizon")
    cam_data.type = "ORTHO"
    # Frame so the car fills a useful share of the canvas while keeping a
    # small margin. Ortho scale maps to the LARGER canvas dimension.
    aspect = canvas_w / float(canvas_h)
    base = MODEL3_LENGTH_M * 1.05
    cam_data.ortho_scale = max(base, base / aspect)
    cam = bpy.data.objects.new("Camera_Horizon", cam_data)
    bpy.context.scene.collection.objects.link(cam)
    # Nose is +X, so the rear is -X: stand behind and to one side, elevated.
    cam.location = (-6.4, -4.1, 3.4)
    con = cam.constraints.new("TRACK_TO")
    con.target = target
    con.track_axis = "TRACK_NEGATIVE_Z"
    con.up_axis = "UP_Y"
    bpy.context.scene.camera = cam
    return cam


def setup_lighting():
    bpy.ops.object.light_add(type="AREA", location=(4.0, -4.0, 5.0))
    key = bpy.context.active_object
    key.name = "AB_Key"
    key.data.energy = 900.0
    key.data.size = 6.0
    key.rotation_euler = (math.radians(45), 0, math.radians(45))

    bpy.ops.object.light_add(type="AREA", location=(-5.0, 4.0, 3.6))
    fill = bpy.context.active_object
    fill.name = "AB_Fill"
    fill.data.energy = 260.0
    fill.data.size = 8.0
    fill.rotation_euler = (math.radians(65), 0, math.radians(-135))

    bpy.ops.object.light_add(type="AREA", location=(-6.0, -2.5, 2.2))
    rim = bpy.context.active_object
    rim.name = "AB_Rim"
    rim.data.energy = 420.0
    rim.data.size = 5.0
    rim.rotation_euler = (math.radians(80), 0, math.radians(-70))

    world = bpy.data.worlds.new("AB_World")
    bpy.context.scene.world = world
    world.use_nodes = True
    bg = world.node_tree.nodes.get("Background")
    if bg is not None:
        bg.inputs["Color"].default_value = (0.035, 0.042, 0.05, 1.0)
        if "Strength" in bg.inputs:
            bg.inputs["Strength"].default_value = 1.0


def setup_render(canvas_w, canvas_h, supersample, out_path):
    scene = bpy.context.scene
    engines = [i.identifier for i in
               scene.render.bl_rna.properties["engine"].enum_items]
    for candidate in ("BLENDER_EEVEE_NEXT", "BLENDER_EEVEE"):
        if candidate in engines:
            scene.render.engine = candidate
            break
    scene.render.film_transparent = True
    scene.render.resolution_x = canvas_w * supersample
    scene.render.resolution_y = canvas_h * supersample
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGBA"
    scene.render.image_settings.compression = 90
    # Same exposure for every A/B render.
    try:
        scene.view_settings.view_transform = "Standard"
    except Exception:
        pass
    scene.view_settings.exposure = 0.0
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    scene.render.filepath = out_path
    return scene


def main():
    args = parse_args()
    canvas_w, canvas_h = (int(v) for v in args.canvas.lower().split("x"))

    load(args.input)
    meshes = [o for o in bpy.data.objects if o.type == "MESH"]
    if not meshes:
        sys.exit("no meshes imported")
    info = normalise(meshes, args.nose)
    if args.mode == "unified":
        apply_unified_materials(meshes)
    setup_lighting()
    setup_camera(meshes, canvas_w, canvas_h)
    setup_render(canvas_w, canvas_h, args.supersample, args.out)

    print(f"[ab {args.tag}] {os.path.relpath(args.input, REPO_ROOT)}")
    print(f"[ab {args.tag}] mode={args.mode} nose={args.nose} "
          f"normalise={info}")
    bpy.ops.render.render(write_still=True)
    print(f"[ab {args.tag}] wrote {args.out} "
          f"({canvas_w*args.supersample}x{canvas_h*args.supersample})")


if __name__ == "__main__":
    main()
