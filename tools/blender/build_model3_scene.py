#!/usr/bin/env python3
"""Blender PoC / production starter for the dashboard vehicle visual.

Builds a fixed-camera, layered placeholder vehicle, animates one door,
and renders a transparent PNG sequence — the offline half of the
animation pipeline described in docs/RENDERING_CAPABILITY_AUDIT.md.

Run (Blender must be installed; this repo does not install it):

    blender -b -P tools/blender/build_model3_scene.py -- \
        --out assets/vehicle/test_door --frames 16 --door-angle 55

Then pack the result for the runtime if a single bitmap is preferred:

    python3 tools/assets/pack_atlas.py --input assets/vehicle/test_door \\
        --prefix frame_ --out assets/vehicle/test_door_atlas --name door_fl_open

Notes:
- Placeholder geometry only. The production model should keep the same
  object names so animation code and export presets stay valid.
- Fixed camera: the dashboard views the car from a fixed angle, so the
  camera must never move between states.
"""

import argparse
import math
import os
import sys

try:
    import bpy
    from mathutils import Vector
except ImportError:  # pragma: no cover - only runs inside Blender
    sys.exit("This script must be run with: blender -b -P <script>")


def parse_args():
    argv = sys.argv
    argv = argv[argv.index("--") + 1:] if "--" in argv else []
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="assets/vehicle/test_door")
    ap.add_argument("--frames", type=int, default=16)
    ap.add_argument("--door-angle", type=float, default=55.0)
    ap.add_argument("--width", type=int, default=600)
    ap.add_argument("--height", type=int, default=320)
    return ap.parse_args(argv)


def reset_scene():
    bpy.ops.wm.read_factory_settings(use_empty=True)


def add_box(name, location, scale, rotation=(0, 0, 0)):
    bpy.ops.mesh.primitive_cube_add(size=1.0, location=location)
    obj = bpy.context.active_object
    obj.name = name
    obj.scale = Vector(scale)
    obj.rotation_euler = rotation
    return obj


def build_vehicle():
    """Layered placeholder vehicle. Names match the production contract."""
    parts = {}
    parts["Body"] = add_box("Body", (0.0, 0.0, 0.55), (3.4, 1.5, 0.5))
    parts["Glass"] = add_box("Glass", (0.15, 0.0, 0.95), (1.7, 1.25, 0.28))
    # Door_FL pivots at its front edge; we animate its own rotation.
    door = add_box("Door_FL", (0.75, 0.78, 0.62), (0.9, 0.06, 0.42))
    door.data.transform(
        __import__("mathutils").Matrix.Translation((0.45, 0.0, 0.0))
    )
    door.location.x -= 0.45
    parts["Door_FL"] = door
    parts["Door_FR"] = add_box("Door_FR", (0.75, -0.78, 0.62), (0.9, 0.06, 0.42))
    parts["Door_RL"] = add_box("Door_RL", (-0.95, 0.78, 0.62), (0.85, 0.06, 0.42))
    parts["Door_RR"] = add_box("Door_RR", (-0.95, -0.78, 0.62), (0.85, 0.06, 0.42))
    parts["Frunk"] = add_box("Frunk", (1.85, 0.0, 0.72), (0.85, 1.35, 0.10))
    parts["Trunk"] = add_box("Trunk", (-1.85, 0.0, 0.78), (0.80, 1.35, 0.12))
    for tag, x, y in (
        ("Wheel_FL", 1.25, 0.80),
        ("Wheel_FR", 1.25, -0.80),
        ("Wheel_RL", -1.20, 0.80),
        ("Wheel_RR", -1.20, -0.80),
    ):
        parts[tag] = add_box(tag, (x, y, 0.28), (0.30, 0.14, 0.30))
    parts["Headlight_L"] = add_box("Headlight_L", (2.05, 0.55, 0.68), (0.10, 0.28, 0.09))
    parts["Headlight_R"] = add_box("Headlight_R", (2.05, -0.55, 0.68), (0.10, 0.28, 0.09))
    parts["Brake_L"] = add_box("Brake_L", (-2.10, 0.55, 0.75), (0.06, 0.24, 0.08))
    parts["Brake_R"] = add_box("Brake_R", (-2.10, -0.55, 0.75), (0.06, 0.24, 0.08))
    parts["Indicator_L"] = add_box("Indicator_L", (2.02, 0.72, 0.70), (0.08, 0.14, 0.07))
    parts["Indicator_R"] = add_box("Indicator_R", (2.02, -0.72, 0.70), (0.08, 0.14, 0.07))
    return parts


def setup_camera(width, height):
    """Fixed camera: identical for every state and every render."""
    bpy.ops.object.camera_add(location=(6.2, -6.4, 3.4))
    cam = bpy.context.active_object
    cam.name = "DashCam"
    cam.rotation_euler = (math.radians(66.0), 0.0, math.radians(44.0))
    cam.data.type = "ORTHO"
    cam.data.ortho_scale = 6.4
    bpy.context.scene.camera = cam
    return cam


def setup_render(out_dir, width, height):
    scene = bpy.context.scene
    # Blender 4.2+ renamed EEVEE to BLENDER_EEVEE_NEXT; fall back for 3.x.
    try:
        engines = [
            item.identifier
            for item in scene.render.bl_rna.properties["engine"].enum_items
        ]
    except Exception:  # pragma: no cover - defensive for future versions
        engines = []
    if "BLENDER_EEVEE_NEXT" in engines:
        scene.render.engine = "BLENDER_EEVEE_NEXT"
    elif "BLENDER_EEVEE" in engines:
        scene.render.engine = "BLENDER_EEVEE"
    scene.render.film_transparent = True
    scene.render.resolution_x = width
    scene.render.resolution_y = height
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGBA"
    scene.render.filepath = os.path.join(out_dir, "frame_")
    return scene


def add_light():
    bpy.ops.object.light_add(type="SUN", location=(4.0, -5.0, 6.0))
    light = bpy.context.active_object
    light.data.energy = 4.0
    light.rotation_euler = (math.radians(50.0), 0.0, math.radians(35.0))


def animate_door(door, frames, angle_deg):
    scene = bpy.context.scene
    scene.frame_start = 1
    scene.frame_end = frames
    door.rotation_mode = "XYZ"
    door.rotation_euler = (0.0, 0.0, 0.0)
    door.keyframe_insert(data_path="rotation_euler", frame=1)
    door.rotation_euler = (0.0, 0.0, math.radians(-angle_deg))
    door.keyframe_insert(data_path="rotation_euler", frame=frames)
    for fcurve in door.animation_data.action.fcurves:
        for kp in fcurve.keyframe_points:
            kp.interpolation = "BEZIER"


def main():
    args = parse_args()
    out_dir = os.path.abspath(args.out)
    os.makedirs(out_dir, exist_ok=True)

    reset_scene()
    parts = build_vehicle()
    setup_camera(args.width, args.height)
    add_light()
    animate_door(parts["Door_FL"], args.frames, args.door_angle)
    scene = setup_render(out_dir, args.width, args.height)

    bpy.ops.render.render(animation=True)
    produced = sorted(
        f for f in os.listdir(out_dir) if f.startswith("frame_") and f.endswith(".png")
    )
    print(f"[blender-poc] frames={len(produced)} out={out_dir}")
    print(f"[blender-poc] resolution={args.width}x{args.height} "
          f"transparent={scene.render.film_transparent}")
    print(f"[blender-poc] objects={len(bpy.data.objects)} "
          f"(Body/Glass/Door_FL/... contract preserved)")


if __name__ == "__main__":
    main()
