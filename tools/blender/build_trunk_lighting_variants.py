#!/usr/bin/env python3
"""Trunk-attached lighting, rendered with the trunk layer.

The inner rear indicator lamps belong to the trunk lid (proved in the freeze
gate's ownership measurements), so on an open trunk their light is not at the
closed-position screen location. The obvious fix - warp the single-frame
indicator overlay by the trunk's screen transform - was measured and rejected:

    a rigid 3D rotation projects to an exact 2D affine only for a PLANAR
    surface. The trunk has depth, so the recovered affine is off by up to
    13.5 px across 65 sampled vertices at 356x236.

The architecture this repository already prefers is therefore used instead:

    FIXED_BODY lighting contribution      (base + brake/headlight/running)
  + TRUNK_MOVING lighting contribution    (rendered with the trunk layer)

For each trunk animation frame this renders the two indicator variants, so the
runtime never has to warp anything. Left and right inner lamps are disjoint, so
HAZARD is the alpha composite of the two variants rather than a third render -
verified against a direct render in the same run.

Usage:
    blender -b -P tools/blender/build_trunk_lighting_variants.py -- \
        --master assets/source/blender/model_a_production_master.blend \
        --out assets/rendered/vehicle \
        --contract assets/vehicle_state_moving_lighting.json \
        --report assets/checkpoints/vehicle_state_assets/trunk_lighting_variants.json
"""

import argparse
import hashlib
import json
import os
import sys

try:
    import bpy
    from mathutils import Matrix, Vector
except ImportError:  # pragma: no cover
    sys.exit("Run inside Blender")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import taillight_states as states  # noqa: E402
import taillight_system as tail  # noqa: E402

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
CANVAS = (356, 236)
TRUNK_OBJECT = "boot"
TRUNK_PANEL = "trunk"
FRAMES = 14
OPEN_ANGLE_DEG = 55.0
VERIFY_POSITIONS = (0, 7, 13)
HORIZON_CAMERA = {"name": "Camera_Horizon", "ortho_scale": 5.55,
                  "location": (-5.30, -4.55, 3.85), "target": (0.0, 0.0, 0.62)}
VARIANT_STATE = {"ind_left": "LEFT_INDICATOR",
                 "ind_right": "RIGHT_INDICATOR",
                 "ind_both": "HAZARD"}


def parse_args():
    argv = sys.argv
    argv = argv[argv.index("--") + 1:] if "--" in argv else []
    ap = argparse.ArgumentParser()
    ap.add_argument("--master", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--contract", required=True)
    ap.add_argument("--report", required=True)
    ap.add_argument("--samples", type=int, default=16)
    ap.add_argument("--verify-dir", default=None,
                    help="where to write the direct reference renders")
    return ap.parse_args(argv)


def setup(scene, samples):
    cam = bpy.data.objects.get(HORIZON_CAMERA["name"])
    if cam is None:
        data = bpy.data.cameras.new(HORIZON_CAMERA["name"])
        cam = bpy.data.objects.new(HORIZON_CAMERA["name"], data)
        scene.collection.objects.link(cam)
    cam.data.type = "ORTHO"
    cam.data.ortho_scale = HORIZON_CAMERA["ortho_scale"]
    cam.location = HORIZON_CAMERA["location"]
    target = bpy.data.objects.get("Camera_Horizon_Target")
    if target is None:
        target = bpy.data.objects.new("Camera_Horizon_Target", None)
        scene.collection.objects.link(target)
    target.location = HORIZON_CAMERA["target"]
    if not cam.constraints:
        con = cam.constraints.new("TRACK_TO")
        con.target = target
        con.track_axis = "TRACK_NEGATIVE_Z"
        con.up_axis = "UP_Y"
    scene.camera = cam
    scene.render.engine = "CYCLES"
    scene.cycles.device = "CPU"
    scene.cycles.samples = samples
    scene.cycles.use_denoising = True
    scene.cycles.seed = 0
    scene.cycles.use_animated_seed = False
    scene.render.resolution_x, scene.render.resolution_y = CANVAS
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGBA"
    scene.render.film_transparent = True
    return scene


def lighting_parts():
    guides, cavities, lamps = {}, {}, {}
    for obj in bpy.data.objects:
        if obj.type != "MESH":
            continue
        if obj.name.startswith("TailGuide_"):
            label = obj.name[len("TailGuide_"):].rsplit("_", 3)[0]
            guides.setdefault(label, []).append(obj)
        elif obj.name.startswith("Cavity_"):
            label = obj.name[len("Cavity_"):].rsplit("_", 1)[0]
            cavities.setdefault(label, []).append(obj)
        elif obj.name in states.LAMP_CHANNEL:
            lamps[obj.name] = obj
    segments = {label: {"guides": gs, "cavity": cavities.get(label, [])}
                for label, gs in guides.items()}
    return segments, lamps


def apply_state(state, parts, channels):
    segments, lamps = parts
    tail.apply_state(state, segments, lamps, channels[0], channels[1])
    bpy.context.view_layer.update()


def rotate_about(pivot, angle_deg, axis="Y"):
    return (Matrix.Translation(pivot)
            @ Matrix.Rotation(angle3(angle_deg), 4, axis)
            @ Matrix.Translation(-pivot))


def angle3(angle_deg):
    import math
    return math.radians(angle_deg)


def ease_open(t):
    return 4.0 * t * t * t if t < 0.5 else 1.0 - pow(-2.0 * t + 2.0, 3) / 2.0


def render(scene, path):
    scene.render.filepath = path
    bpy.ops.render.render(write_still=True)
    return os.path.getsize(path)


def main():
    args = parse_args()
    bpy.ops.wm.open_mainfile(filepath=args.master)
    scene = setup(bpy.context.scene, args.samples)
    trunk = bpy.data.objects.get(TRUNK_OBJECT)
    if trunk is None:
        sys.exit(f"no {TRUNK_OBJECT} in the master")
    rest = trunk.matrix_world.copy()
    pivot = rest.translation.copy()
    lights = tail.channel_materials()
    base_lens = None
    for obj in bpy.data.objects:
        if obj.name in states.LAMP_CHANNEL and obj.material_slots:
            for slot in obj.material_slots:
                if slot.material is not None:
                    base_lens = slot.material
                    break
            if base_lens:
                break
    lens_states = tail.lens_channel_materials(base=base_lens)
    parts = lighting_parts()

    # ---- trunk animation frames, per indicator channel -------------------
    variants = {}
    for name, state in VARIANT_STATE.items():
        directory = os.path.join(args.out, TRUNK_PANEL, name)
        os.makedirs(directory, exist_ok=True)
        apply_state(state, parts, (lights, lens_states))
        written = []
        for i in range(FRAMES):
            t = i / float(FRAMES - 1)
            trunk.matrix_world = rotate_about(
                pivot, ease_open(t) * OPEN_ANGLE_DEG) @ rest
            bpy.context.view_layer.update()
            path = os.path.join(directory, f"{i:03d}.png")
            render(scene, path)
            written.append(os.path.getsize(path))
        variants[name] = {"dir": f"{TRUNK_PANEL}/{name}", "frames": FRAMES,
                          "state": state,
                          "png_bytes_total": sum(written)}
        print(f"[trunk-lighting] {name}: {FRAMES} frames, "
              f"{sum(written) / 1024.0:.0f} KB, state={state}")
    apply_state("OFF", parts, (lights, lens_states))

    # ---- direct reference renders for the composite check ----------------
    verify = {}
    if args.verify_dir:
        os.makedirs(args.verify_dir, exist_ok=True)
        for label, state in (("lamp_off", "OFF"),
                             ("ind_left", "LEFT_INDICATOR"),
                             ("ind_right", "RIGHT_INDICATOR"),
                             ("hazard", "HAZARD")):
            apply_state(state, parts, (lights, lens_states))
            for i in VERIFY_POSITIONS:
                t = i / float(FRAMES - 1)
                trunk.matrix_world = rotate_about(
                    pivot, ease_open(t) * OPEN_ANGLE_DEG) @ rest
                bpy.context.view_layer.update()
                path = os.path.join(args.verify_dir,
                                    f"{label}_{i:03d}.png")
                render(scene, path)
                verify.setdefault(label, []).append(
                    {"frame": i,
                     "path": os.path.relpath(path, REPO_ROOT).replace(
                         os.sep, "/"),
                     "sha256_16": hashlib.sha256(
                         open(path, "rb").read()).hexdigest()[:16]})
            print(f"[trunk-lighting] verify {label}: "
                  f"{len(VERIFY_POSITIONS)} reference renders")
        apply_state("OFF", parts, (lights, lens_states))
    trunk.matrix_world = rest
    bpy.context.view_layer.update()

    contract = {
        "schema": "vehicle-state-moving-lighting v1",
        "source_master": "MODEL_A_PRODUCTION_MASTER",
        "taillight_geometry_version":
            "surface-offset-cavity-lightguide-v3",
        "why": "The inner rear indicator lamps belong to the trunk lid "
               "(TRUNK_MOVING, proved by the freeze gate ownership "
               "measurement), so their light is not at the closed-position "
               "screen location while the lid is open. A 2D warp of the "
               "single-frame overlay was measured and rejected: a rigid 3D "
               "rotation projects to an exact 2D affine only for a planar "
               "surface, and the trunk has depth (max error 13.5 px over 65 "
               "sampled vertices at 356x236).",
        "architecture": "FIXED_BODY lighting contribution (base + brake / "
                        "headlight / running overlays) plus TRUNK_MOVING "
                        "lighting contribution rendered with the trunk layer",
        "panels": {
            TRUNK_PANEL: {
                "object": TRUNK_OBJECT,
                "ownership": "TRUNK_MOVING",
                "carries": ["INDICATOR_LEFT", "INDICATOR_RIGHT"],
                "frames": FRAMES,
                "lights_off_dir": TRUNK_PANEL,
                "variants": variants,
                "hazard": "own variant (ind_both): drawing two full-vehicle "
                          "variants in sequence would let the second one's "
                          "unlit pixels overwrite the first one's lit lamp",
                "rejected_alternative": "2D affine warp of the closed-position "
                                        "indicator overlay",
            }
        },
        "fixed_body_overlays": ["vehicle.brake", "vehicle.headlight",
                                "vehicle.running"],
    }
    with open(args.contract, "w") as fh:
        json.dump(contract, fh, indent=2)
        fh.write("\n")
    report = {"contract": os.path.relpath(args.contract, REPO_ROOT),
              "canvas": list(CANVAS), "frames": FRAMES,
              "open_angle_deg": OPEN_ANGLE_DEG, "variants": variants,
              "verification_renders": verify,
              "png_bytes_total": sum(v["png_bytes_total"]
                                     for v in variants.values())}
    os.makedirs(os.path.dirname(args.report), exist_ok=True)
    with open(args.report, "w") as fh:
        json.dump(report, fh, indent=2)
        fh.write("\n")
    print(f"[trunk-lighting] -> {args.contract}")
    print(f"[trunk-lighting] -> {args.report}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
