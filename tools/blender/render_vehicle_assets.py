#!/usr/bin/env python3
"""Render vehicle states/animations from model3.blend — no manual GUI work.

Loads ``assets/source/blender/model3.blend`` (with its generated
``model3.manifest.json``), applies the requested action, renders a
transparent PNG sequence with the fixed ``Camera_Horizon``, downsamples
the supersampled render to the V6 canvas size, then runs the asset
budget check.

Examples:
    blender -b -P tools/blender/render_vehicle_assets.py -- --all
    blender -b -P tools/blender/render_vehicle_assets.py -- --action Door_FL_Open
    blender -b -P tools/blender/render_vehicle_assets.py -- --action Brake_On
    blender -b -P tools/blender/render_vehicle_assets.py -- --list

Output layout (one directory per action, identical canvas for every frame):
    assets/rendered/vehicle/door_fl/000.png ... 015.png
    assets/rendered/vehicle/brake_on/000.png
"""

import argparse
import json
import os
import subprocess
import sys

try:
    import bpy
except ImportError:  # pragma: no cover - only runs inside Blender
    sys.exit("Run inside Blender: blender -b -P tools/blender/render_vehicle_assets.py")

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
DEFAULT_BLEND = os.path.join(REPO_ROOT, "assets", "source", "blender", "model3.blend")
DEFAULT_OUT = os.path.join(REPO_ROOT, "assets", "rendered", "vehicle")

# action name -> output directory name
ACTION_DIRS = {
    "Door_FL_Open": "door_fl",
    "Door_FR_Open": "door_fr",
    "Door_RL_Open": "door_rl",
    "Door_RR_Open": "door_rr",
    "Frunk_Open": "frunk",
    "Trunk_Open": "trunk",
    "Brake_On": "brake_on",
    "Headlight_On": "headlight_on",
    "Indicator_Left": "indicator_left",
    "Indicator_Right": "indicator_right",
    "Hazard": "hazard",
}


def parse_args():
    argv = sys.argv
    argv = argv[argv.index("--") + 1:] if "--" in argv else []
    ap = argparse.ArgumentParser()
    ap.add_argument("--blend", default=DEFAULT_BLEND)
    ap.add_argument("--out", default=DEFAULT_OUT)
    ap.add_argument("--action", action="append", default=[])
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--keep-supersample", action="store_true",
                    help="keep the full-resolution frames instead of downscaling")
    ap.add_argument("--no-budget", action="store_true")
    return ap.parse_args(argv)


def load_manifest(blend_path):
    path = os.path.splitext(blend_path)[0] + ".manifest.json"
    if not os.path.isfile(path):
        sys.exit(f"manifest missing: {path}\n"
                 f"run build_model3_scene.py first")
    with open(path) as fh:
        return json.load(fh)


def bind_action(action_name, info):
    """Assign the action to the object (rotation) or node tree (emission)."""
    action = bpy.data.actions.get(action_name)
    if action is None:
        sys.exit(f"action not found in blend: {action_name}")
    channel = info.get("channel", "rotation")
    for obj_name in info["objects"]:
        obj = bpy.data.objects.get(obj_name)
        if obj is None:
            print(f"  ! object {obj_name} missing, skipping")
            continue
        if channel == "rotation":
            owner = obj
        else:
            mat = obj.data.materials[0] if obj.data.materials else None
            if mat is None or not mat.use_nodes:
                continue
            owner = mat.node_tree
        if owner.animation_data is None:
            owner.animation_data_create()
        owner.animation_data.action = action
        # Blender 4.4+ slotted actions need an explicit slot binding.
        try:
            slots = getattr(action, "slots", None)
            if hasattr(owner.animation_data, "action_slot") and slots:
                if owner.animation_data.action_slot is None:
                    owner.animation_data.action_slot = slots[0]
        except Exception:  # pragma: no cover
            pass


def render_action(action_name, info, args, canvas, supersample):
    out_dir = os.path.join(args.out, ACTION_DIRS.get(action_name, action_name.lower()))
    os.makedirs(out_dir, exist_ok=True)
    for f in os.listdir(out_dir):
        if f.endswith(".png"):
            os.remove(os.path.join(out_dir, f))

    bind_action(action_name, info)

    scene = bpy.context.scene
    scene.camera = bpy.data.objects["Camera_Horizon"]
    scene.frame_start = info["first"]
    scene.frame_end = info["last"]
    # Keep the render canvas fixed for every frame (no per-frame crop).
    scene.render.resolution_x = canvas["width"] * supersample
    scene.render.resolution_y = canvas["height"] * supersample
    scene.render.film_transparent = True
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGBA"
    scene.render.filepath = os.path.join(out_dir, "")

    print(f"[render] {action_name}: frames {info['first']}-{info['last']} -> {out_dir}")
    bpy.ops.render.render(animation=True)

    frames = sorted(f for f in os.listdir(out_dir) if f.endswith(".png"))
    # Blender numbers frames as 0001.png; normalise to 000.png style.
    for f in frames:
        try:
            idx = int(os.path.splitext(f)[0]) - info["first"]
        except ValueError:
            continue
        target = os.path.join(out_dir, f"{idx:03d}.png")
        if os.path.join(out_dir, f) != target:
            os.replace(os.path.join(out_dir, f), target)

    if not args.keep_supersample and supersample > 1:
        downscale(out_dir, canvas)
    return out_dir


def downscale(out_dir, canvas):
    """Downsample supersampled frames to the exact catalog canvas."""
    try:
        from PIL import Image
    except ImportError:
        print("  ! Pillow unavailable inside Blender's Python: frames stay "
              "supersampled. Re-run tools/assets/downscale_frames.py on the host.")
        return
    for f in sorted(os.listdir(out_dir)):
        if not f.endswith(".png"):
            continue
        path = os.path.join(out_dir, f)
        img = Image.open(path)
        if img.size == (canvas["width"], canvas["height"]):
            continue
        img.resize((canvas["width"], canvas["height"]), Image.LANCZOS).save(path)
    print(f"  downsampled to {canvas['width']}x{canvas['height']}")


def run_budget(out_dir):
    script = os.path.join(REPO_ROOT, "tools", "assets", "check_budget.py")
    if not os.path.isfile(script):
        return
    print("\n[budget] " + "-" * 60)
    subprocess.run([sys.executable, script, "--sequence", out_dir], check=False)


def main():
    args = parse_args()
    manifest = load_manifest(args.blend)
    canvas = manifest.get("canvas", {"width": 356, "height": 236, "supersample": 3})
    supersample = canvas.get("supersample", 3)
    actions = manifest["actions"]

    if args.list:
        print("available actions:")
        for name, info in sorted(actions.items()):
            print(f"  {name:16} frames {info['first']}-{info['last']} "
                  f"channel={info.get('channel', 'rotation')} "
                  f"objects={','.join(info['objects'])}")
        return

    selected = list(actions) if args.all else args.action
    if not selected:
        sys.exit("nothing selected: pass --all or --action NAME (see --list)")
    unknown = [a for a in selected if a not in actions]
    if unknown:
        sys.exit(f"unknown action(s): {', '.join(unknown)}")

    bpy.ops.wm.open_mainfile(filepath=args.blend)
    rendered = []
    for name in selected:
        rendered.append(render_action(name, actions[name], args, canvas, supersample))

    if not args.no_budget:
        for out_dir in rendered:
            run_budget(out_dir)
    print(f"\n[done] {len(rendered)} sequence(s) under {args.out}")


if __name__ == "__main__":
    main()
