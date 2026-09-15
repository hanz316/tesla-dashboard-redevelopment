#!/usr/bin/env python3
"""Build the canonical dashboard vehicle scene (placeholder geometry).

Creates ``assets/source/blender/model3.blend`` with:

* the full object split required by the V6 asset contract
  (Body / Glass / Wheel_* / Door_* / Frunk / Trunk / Headlight_* /
   Brake_* / Indicator_* / Interior)
* one fixed ``Camera_Horizon`` (high rear 3/4 view, never animated)
* one fixed light rig and shared materials
* every animation action listed in docs/VEHICLE_ASSET_PIPELINE.md

The geometry is an intentional placeholder: no third-party / unclear-licence
model is downloaded. Replace the meshes later, keep the object names, camera
and actions so the whole pipeline keeps working.

Run:
    blender -b -P tools/blender/build_model3_scene.py
    blender -b -P tools/blender/build_model3_scene.py -- --render-poc

Blender is NOT installed by this repo; see docs/VEHICLE_ASSET_PIPELINE.md.
"""

import argparse
import json
import math
import os
import sys

try:
    import bpy
    from mathutils import Matrix, Vector
except ImportError:  # pragma: no cover - only runs inside Blender
    sys.exit("Run inside Blender: blender -b -P tools/blender/build_model3_scene.py")


REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
DEFAULT_BLEND = os.path.join(REPO_ROOT, "assets", "source", "blender", "model3.blend")

# Canonical canvas used by every rendered state (matches the V6 catalog:
# vehicle layers are 356x236 with a separate 360x150 shadow).
CANVAS_W = 356
CANVAS_H = 236
SUPERSAMPLE = 3

WHEELBASE_FRONT_X = 1.45
WHEELBASE_REAR_X = -1.42
WHEEL_Y = 0.86

DOOR_OPEN_DEG = 55.0
FRUNK_OPEN_DEG = 42.0
TRUNK_OPEN_DEG = 48.0

FRAME_DOORS = 16
FRAME_HOODS = 14
FRAME_BLINK = 12          # one full blink cycle


def parse_args():
    argv = sys.argv
    argv = argv[argv.index("--") + 1:] if "--" in argv else []
    ap = argparse.ArgumentParser()
    ap.add_argument("--blend", default=DEFAULT_BLEND)
    ap.add_argument("--canvas", default=f"{CANVAS_W}x{CANVAS_H}")
    ap.add_argument("--supersample", type=int, default=SUPERSAMPLE)
    ap.add_argument("--render-poc", action="store_true",
                    help="after building, render a short door PoC")
    ap.add_argument("--poc-out", default=os.path.join(REPO_ROOT, "assets",
                                                      "rendered", "vehicle", "_poc"))
    return ap.parse_args(argv)


# --------------------------------------------------------------------------
# scene / material helpers
# --------------------------------------------------------------------------

def reset_scene():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    for block in (bpy.data.actions, bpy.data.materials, bpy.data.objects):
        for item in list(block):
            block.remove(item)


def new_material(name, base_rgba, metallic=0.35, roughness=0.42,
                 emission_rgba=None, emission_strength=0.0):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    if bsdf is None:
        return mat
    bsdf.inputs["Base Color"].default_value = base_rgba
    if "Metallic" in bsdf.inputs:
        bsdf.inputs["Metallic"].default_value = metallic
    if "Roughness" in bsdf.inputs:
        bsdf.inputs["Roughness"].default_value = roughness
    if emission_rgba is not None:
        # Blender 4.x renamed "Emission" -> "Emission Color".
        for key in ("Emission Color", "Emission"):
            if key in bsdf.inputs:
                bsdf.inputs[key].default_value = emission_rgba
                break
        if "Emission Strength" in bsdf.inputs:
            bsdf.inputs["Emission Strength"].default_value = emission_strength
    return mat


def add_box(name, location, scale, material, parent=None):
    bpy.ops.mesh.primitive_cube_add(size=1.0, location=location)
    obj = bpy.context.active_object
    obj.name = name
    obj.scale = Vector(scale)
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    obj.data.materials.append(material)
    if parent is not None:
        obj.parent = parent
    return obj


def add_hinged_box(name, hinge_x, y, z, size_x, size_y, size_z, material):
    """Box whose local origin sits on the hinge axis so rotation opens it."""
    bpy.ops.mesh.primitive_cube_add(size=1.0, location=(0.0, 0.0, 0.0))
    obj = bpy.context.active_object
    obj.name = name
    obj.scale = Vector((size_x, size_y, size_z))
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    # Shift geometry so the local origin is at the hinge edge.
    obj.data.transform(Matrix.Translation((size_x * 0.5, 0.0, 0.0)))
    obj.location = (hinge_x, y, z)
    obj.data.materials.append(material)
    return obj


# --------------------------------------------------------------------------
# vehicle
# --------------------------------------------------------------------------

def build_vehicle():
    body_mat = new_material("MAT_Body", (0.62, 0.65, 0.68, 1.0), metallic=0.55)
    glass_mat = new_material("MAT_Glass", (0.05, 0.07, 0.09, 1.0),
                             metallic=0.0, roughness=0.12)
    trim_mat = new_material("MAT_Trim", (0.10, 0.11, 0.12, 1.0), metallic=0.2)
    tire_mat = new_material("MAT_Tire", (0.04, 0.04, 0.05, 1.0), metallic=0.0,
                            roughness=0.85)
    rim_mat = new_material("MAT_Rim", (0.72, 0.74, 0.76, 1.0), metallic=0.9,
                           roughness=0.25)
    head_mat = new_material("MAT_Headlight", (0.85, 0.88, 0.92, 1.0),
                            emission_rgba=(1.0, 0.97, 0.88, 1.0))
    brake_mat = new_material("MAT_Brake", (0.45, 0.05, 0.05, 1.0),
                             emission_rgba=(1.0, 0.10, 0.08, 1.0))
    ind_mat = new_material("MAT_Indicator", (0.55, 0.32, 0.02, 1.0),
                           emission_rgba=(1.0, 0.55, 0.05, 1.0))
    interior_mat = new_material("MAT_Interior", (0.13, 0.14, 0.16, 1.0),
                                metallic=0.0, roughness=0.7)

    parts = {}
    parts["Body"] = add_box("Body", (0.0, 0.0, 0.62), (4.70, 1.86, 0.62), body_mat)
    add_box("Body_Sill_L", (0.0, 0.93, 0.45), (3.60, 0.10, 0.34), trim_mat,
            parent=parts["Body"])
    add_box("Body_Sill_R", (0.0, -0.93, 0.45), (3.60, 0.10, 0.34), trim_mat,
            parent=parts["Body"])
    parts["Glass"] = add_box("Glass", (0.10, 0.0, 1.06), (2.30, 1.62, 0.42),
                             glass_mat)
    parts["Interior"] = add_box("Interior", (0.05, 0.0, 0.92), (2.05, 1.45, 0.30),
                                interior_mat)

    # Doors: hinged at their front edge so one rotation opens them.
    parts["Door_FL"] = add_hinged_box(
        "Door_FL", 1.15, 0.90, 0.70, 0.92, 0.06, 0.50, body_mat)
    parts["Door_FR"] = add_hinged_box(
        "Door_FR", 1.15, -0.90, 0.70, 0.92, 0.06, 0.50, body_mat)
    parts["Door_RL"] = add_hinged_box(
        "Door_RL", -0.19, 0.90, 0.70, 0.78, 0.06, 0.48, body_mat)
    parts["Door_RR"] = add_hinged_box(
        "Door_RR", -0.19, -0.90, 0.70, 0.78, 0.06, 0.48, body_mat)

    # Hoods.
    parts["Frunk"] = add_hinged_box("Frunk", 1.30, 0.0, 0.88, 1.00, 1.60, 0.10,
                                    body_mat)
    parts["Trunk"] = add_hinged_box("Trunk", -1.55, 0.0, 0.92, 0.95, 1.66, 0.12,
                                    body_mat)

    # Wheels (tire + rim parented together).
    for tag, x, y in (
        ("Wheel_FL", WHEELBASE_FRONT_X, WHEEL_Y),
        ("Wheel_FR", WHEELBASE_FRONT_X, -WHEEL_Y),
        ("Wheel_RL", WHEELBASE_REAR_X, WHEEL_Y),
        ("Wheel_RR", WHEELBASE_REAR_X, -WHEEL_Y),
    ):
        bpy.ops.mesh.primitive_cylinder_add(vertices=24, radius=0.34, depth=0.24,
                                            location=(x, y, 0.34))
        wheel = bpy.context.active_object
        wheel.name = tag
        wheel.rotation_euler = (math.radians(90.0), 0.0, 0.0)
        bpy.ops.object.transform_apply(rotation=True)
        wheel.data.materials.append(tire_mat)
        bpy.ops.mesh.primitive_cylinder_add(vertices=20, radius=0.21, depth=0.26,
                                            location=(x, y, 0.34))
        rim = bpy.context.active_object
        rim.name = tag + "_Rim"
        rim.rotation_euler = (math.radians(90.0), 0.0, 0.0)
        bpy.ops.object.transform_apply(rotation=True)
        rim.data.materials.append(rim_mat)
        rim.parent = wheel
        parts[tag] = wheel

    # Light units.
    parts["Headlight_L"] = add_box("Headlight_L", (2.30, 0.62, 0.72),
                                   (0.10, 0.34, 0.12), head_mat)
    parts["Headlight_R"] = add_box("Headlight_R", (2.30, -0.62, 0.72),
                                   (0.10, 0.34, 0.12), head_mat)
    parts["Brake_L"] = add_box("Brake_L", (-2.32, 0.62, 0.82),
                               (0.08, 0.30, 0.12), brake_mat)
    parts["Brake_R"] = add_box("Brake_R", (-2.32, -0.62, 0.82),
                               (0.08, 0.30, 0.12), brake_mat)
    parts["Indicator_L"] = add_box("Indicator_L", (2.26, 0.80, 0.74),
                                   (0.10, 0.16, 0.10), ind_mat)
    parts["Indicator_R"] = add_box("Indicator_R", (2.26, -0.80, 0.74),
                                   (0.10, 0.16, 0.10), ind_mat)
    return parts


def setup_lighting():
    bpy.ops.object.light_add(type="SUN", location=(4.0, -5.0, 7.0))
    key = bpy.context.active_object
    key.name = "Light_Key"
    key.data.energy = 3.6
    key.rotation_euler = (math.radians(52.0), math.radians(6.0), math.radians(38.0))

    bpy.ops.object.light_add(type="SUN", location=(-4.0, 3.0, 5.0))
    fill = bpy.context.active_object
    fill.name = "Light_Fill"
    fill.data.energy = 1.1
    fill.rotation_euler = (math.radians(62.0), 0.0, math.radians(-140.0))

    world = bpy.data.worlds.new("W_Studio")
    bpy.context.scene.world = world
    world.use_nodes = True
    bg = world.node_tree.nodes.get("Background")
    if bg is not None and "Color" in bg.inputs:
        bg.inputs["Color"].default_value = (0.05, 0.06, 0.07, 1.0)


def setup_camera_horizon():
    """High rear 3/4 view: roof, tail, both flanks, doors, hoods visible."""
    target = bpy.data.objects.new("Camera_Horizon_Target", None)
    bpy.context.scene.collection.objects.link(target)
    target.location = (0.0, 0.0, 0.62)

    cam_data = bpy.data.cameras.new("Camera_Horizon")
    cam_data.type = "ORTHO"          # deterministic framing between states
    cam_data.ortho_scale = 5.55
    cam = bpy.data.objects.new("Camera_Horizon", cam_data)
    bpy.context.scene.collection.objects.link(cam)
    cam.location = (-5.30, -4.55, 3.85)

    con = cam.constraints.new("TRACK_TO")
    con.target = target
    con.track_axis = "TRACK_NEGATIVE_Z"
    con.up_axis = "UP_Y"

    bpy.context.scene.camera = cam
    return cam


# --------------------------------------------------------------------------
# actions
# --------------------------------------------------------------------------

def _new_action(name):
    action = bpy.data.actions.new(name)
    action.use_fake_user = True
    return action


def _assign_action(owner, action):
    """Assign an action to an object OR a material node tree.

    Handles Blender 4.4+ slotted actions, where an action must also be
    bound to a slot before it evaluates.
    """
    if owner.animation_data is None:
        owner.animation_data_create()
    owner.animation_data.action = action
    try:
        slots = getattr(action, "slots", None)
        if hasattr(owner.animation_data, "action_slot") and slots:
            if owner.animation_data.action_slot is None:
                owner.animation_data.action_slot = slots[0]
    except Exception:  # pragma: no cover - only relevant on 4.4+
        pass


def _key_rotation(obj, action, degrees_by_frame, axis=2):
    """axis: 0=X, 1=Y, 2=Z."""
    _assign_action(obj, action)
    obj.rotation_mode = "XYZ"
    for frame, deg in degrees_by_frame.items():
        rot = [0.0, 0.0, 0.0]
        rot[axis] = math.radians(deg)
        obj.rotation_euler = rot
        obj.keyframe_insert(data_path="rotation_euler", frame=frame)
    for fcurve in action.fcurves:
        for kp in fcurve.keyframe_points:
            kp.interpolation = "BEZIER"


def _key_emission(obj, action, strength_by_frame):
    """Keyframes the material emission strength (static overlays / blink loops).

    Material node inputs are animated on the node tree's own animation data,
    not on the object, so the action is assigned there.
    """
    mat = obj.data.materials[0] if obj.data.materials else None
    if mat is None or not mat.use_nodes:
        return False
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    if bsdf is None or "Emission Strength" not in bsdf.inputs:
        return False
    _assign_action(mat.node_tree, action)
    socket = bsdf.inputs["Emission Strength"]
    for frame, strength in strength_by_frame.items():
        socket.default_value = strength
        socket.keyframe_insert(data_path="default_value", frame=frame)
    return True


def build_actions(parts):
    """Create every action named in docs/VEHICLE_ASSET_PIPELINE.md."""
    created = {}

    # A. continuous opening animations
    for name, obj, deg in (
        ("Door_FL_Open", parts["Door_FL"], -DOOR_OPEN_DEG),
        ("Door_FR_Open", parts["Door_FR"], DOOR_OPEN_DEG),
        ("Door_RL_Open", parts["Door_RL"], -DOOR_OPEN_DEG),
        ("Door_RR_Open", parts["Door_RR"], DOOR_OPEN_DEG),
    ):
        action = _new_action(name)
        _key_rotation(obj, action, {1: 0.0, FRAME_DOORS: deg}, axis=2)
        created[name] = {"objects": [obj.name], "channel": "rotation",
                         "first": 1, "last": FRAME_DOORS}

    for name, obj, deg in (
        ("Frunk_Open", parts["Frunk"], -FRUNK_OPEN_DEG),
        ("Trunk_Open", parts["Trunk"], TRUNK_OPEN_DEG),
    ):
        action = _new_action(name)
        _key_rotation(obj, action, {1: 0.0, FRAME_HOODS: deg}, axis=1)
        created[name] = {"objects": [obj.name], "channel": "rotation",
                         "first": 1, "last": FRAME_HOODS}

    # B. static overlays (single frame; both sides share the action name)
    brake = _new_action("Brake_On")
    _key_emission(parts["Brake_L"], brake, {1: 2.4})
    created["Brake_On"] = {"objects": ["Brake_L", "Brake_R"],
                           "channel": "emission", "first": 1, "last": 1}

    head = _new_action("Headlight_On")
    _key_emission(parts["Headlight_L"], head, {1: 2.4})
    created["Headlight_On"] = {"objects": ["Headlight_L", "Headlight_R"],
                               "channel": "emission", "first": 1, "last": 1}

    # C. short blink loops (one full cycle)
    blink = {1: 0.0,
             int(FRAME_BLINK * 0.25): 3.2,
             int(FRAME_BLINK * 0.5): 0.0,
             int(FRAME_BLINK * 0.75): 3.2,
             FRAME_BLINK: 0.0}
    for name, obj in (("Indicator_Left", parts["Indicator_L"]),
                      ("Indicator_Right", parts["Indicator_R"])):
        action = _new_action(name)
        _key_emission(obj, action, blink)
        created[name] = {"objects": [obj.name], "channel": "emission",
                         "first": 1, "last": FRAME_BLINK}

    hazard = _new_action("Hazard")
    _key_emission(parts["Indicator_L"], hazard, blink)
    created["Hazard"] = {"objects": ["Indicator_L", "Indicator_R"],
                         "channel": "emission", "first": 1, "last": FRAME_BLINK}
    return created


# --------------------------------------------------------------------------
# render setup + optional PoC
# --------------------------------------------------------------------------

def setup_render(canvas_w, canvas_h, supersample, out_dir=None):
    scene = bpy.context.scene
    engines = [i.identifier for i in
               scene.render.bl_rna.properties["engine"].enum_items]
    for candidate in ("BLENDER_EEVEE_NEXT", "BLENDER_EEVEE", "BLENDER_WORKBENCH"):
        if candidate in engines:
            scene.render.engine = candidate
            break
    scene.render.film_transparent = True
    scene.render.resolution_x = canvas_w * supersample
    scene.render.resolution_y = canvas_h * supersample
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGBA"
    scene.render.image_settings.compression = 70
    if out_dir:
        scene.render.filepath = os.path.join(out_dir, "")
    return scene


def main():
    args = parse_args()
    canvas_w, canvas_h = (int(v) for v in args.canvas.lower().split("x"))

    reset_scene()
    parts = build_vehicle()
    setup_lighting()
    setup_camera_horizon()
    actions = build_actions(parts)
    setup_render(canvas_w, canvas_h, args.supersample, args.poc_out)

    os.makedirs(os.path.dirname(args.blend), exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=args.blend)

    manifest = {
        "generated_by": "tools/blender/build_model3_scene.py",
        "blend": os.path.relpath(args.blend, REPO_ROOT),
        "camera": "Camera_Horizon",
        "canvas": {"width": canvas_w, "height": canvas_h,
                   "supersample": args.supersample},
        "objects": sorted(o.name for o in bpy.data.objects if o.type == "MESH"),
        "actions": actions,
    }
    manifest_path = os.path.splitext(args.blend)[0] + ".manifest.json"
    with open(manifest_path, "w") as fh:
        json.dump(manifest, fh, indent=2)

    mesh_count = len([o for o in bpy.data.objects if o.type == "MESH"])
    print(f"[scene] saved {args.blend}")
    print(f"[scene] manifest {manifest_path}")
    print(f"[scene] meshes={mesh_count} actions={len(bpy.data.actions)} "
          f"camera={bpy.context.scene.camera.name}")
    print(f"[scene] canvas={canvas_w}x{canvas_h} supersample={args.supersample} "
          f"render={canvas_w*args.supersample}x{canvas_h*args.supersample}")

    if args.render_poc:
        os.makedirs(args.poc_out, exist_ok=True)
        info = actions["Door_FL_Open"]
        scene = bpy.context.scene
        scene.frame_start = info["first"]
        scene.frame_end = info["last"]
        print(f"[poc] rendering Door_FL_Open frames {info['first']}-{info['last']}"
              f" -> {args.poc_out}")
        bpy.ops.render.render(animation=True)
        produced = [f for f in os.listdir(args.poc_out) if f.endswith(".png")]
        print(f"[poc] {len(produced)} PNG frames written")


if __name__ == "__main__":
    main()
