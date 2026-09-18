#!/usr/bin/env python3
"""Build the production vehicle state assets from the LOCKED master.

Follows the contract that already exists in the repository rather than
inventing a new one:

* canvas 356x236, one fixed camera, one fixed anchor
  (`assets/manifest.json`, `tools/assets/verify_alignment.py`);
* `BASE + STATIC STATE OVERLAYS + MOVING BODY LAYERS` - never a unique
  full-vehicle asset per combination;
* door sequences 16 frames, frunk/trunk 14 frames, indicator loops 12 frames,
  brake/headlight single-frame overlays (the A/B/C classes in
  `docs/ANIMATION_STATE_STRATEGY.md`);
* the taillight channels come from the frozen TaillightLightingSystem, not from
  a second implementation of the same semantics.

Every pivot and swing direction is measured on Model A. Nothing is copied from
Door_FL to another panel.

Usage:
    blender -b -P tools/blender/build_vehicle_state_assets.py -- \
        --master assets/source/blender/model_a_production_master.blend \
        --out assets/rendered/vehicle \
        --report assets/checkpoints/vehicle_state_assets/vehicle_state_assets.json
"""

import argparse
import hashlib
import json
import math
import os
import re
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
SUPERSAMPLE = 1
HORIZON_CAMERA = {
    "name": "Camera_Horizon",
    "type": "ORTHO",
    "ortho_scale": 5.55,
    "location": (-5.30, -4.55, 3.85),
    "target": (0.0, 0.0, 0.62),
}
# name -> (blender object, axis of rotation, opening angle, frames, owners)
PANELS = [
    ("door_fl", "door_lf", "Z", 52.0, 16),
    ("door_fr", "door_rf", "Z", 52.0, 16),
    ("door_rl", "door_lr", "Z", 52.0, 16),
    ("door_rr", "door_rr", "Z", 52.0, 16),
    ("frunk", "bonnet_ok", "Y", 45.0, 14),
    ("trunk", "boot", "Y", 55.0, 14),
]
DOOR_OPEN_FRAMES = 16
DOOR_FPS = 24
INDICATOR_FRAMES = 12
INDICATOR_FPS = 12


def parse_args():
    argv = sys.argv
    argv = argv[argv.index("--") + 1:] if "--" in argv else []
    ap = argparse.ArgumentParser()
    ap.add_argument("--master", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--report", required=True)
    ap.add_argument("--samples", type=int, default=32)
    ap.add_argument("--only", default=None, help="one panel name, for smoke tests")
    ap.add_argument("--frames", type=int, default=None,
                    help="override the frame count (smoke tests)")
    ap.add_argument("--skip-state-renders", action="store_true")
    ap.add_argument("--write-marker", action="store_true",
                    help="write MODEL3_SOURCE.json (production marker)")
    return ap.parse_args(argv)


def open_master(path):
    bpy.ops.wm.open_mainfile(filepath=path)
    scene = bpy.context.scene
    scene.render.engine = "CYCLES"
    scene.cycles.device = "CPU"
    return scene


def setup_horizon_camera(scene):
    """The camera the 356x236 asset contract was defined around."""
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
    return cam


def configure_render(scene, samples):
    scene.render.resolution_x = CANVAS[0] * SUPERSAMPLE
    scene.render.resolution_y = CANVAS[1] * SUPERSAMPLE
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGBA"
    scene.render.film_transparent = True
    scene.cycles.samples = samples
    scene.cycles.use_denoising = True
    scene.cycles.seed = 0
    scene.cycles.use_animated_seed = False


def panel_report(obj, axis):
    """Hinge, extent and edge check, measured on the panel itself."""
    mw = obj.matrix_world
    corners = [mw @ Vector(c) for c in obj.bound_box]
    lo = Vector((min(c.x for c in corners), min(c.y for c in corners),
                 min(c.z for c in corners)))
    hi = Vector((max(c.x for c in corners), max(c.y for c in corners),
                 max(c.z for c in corners)))
    hinge = mw.translation.copy()
    if axis == "Z":      # door: hinge runs along Z at one X edge
        edge = min(abs(hinge.x - lo.x), abs(hinge.x - hi.x))
        length = hi.x - lo.x
        kind = "vertical hinge at an X edge"
    else:                # hood/boot: hinge runs along Y at the top X edge
        edge = min(abs(hinge.x - lo.x), abs(hinge.x - hi.x))
        length = hi.x - lo.x
        kind = "lateral hinge at an X edge (top of the panel)"
    return {"hinge": [round(v, 5) for v in hinge],
            "bbox_min": [round(v, 4) for v in lo],
            "bbox_max": [round(v, 4) for v in hi],
            "hinge_from_nearest_edge_m": round(edge, 5),
            "panel_extent_along_x_m": round(length, 4),
            "hinge_kind": kind,
            "hinge_on_edge": edge < 0.05}


def rotate_about(pivot, angle_deg, axis):
    return (Matrix.Translation(pivot)
            @ Matrix.Rotation(math.radians(angle_deg), 4, axis)
            @ Matrix.Translation(-pivot))


def far_edge_point(obj):
    mw = obj.matrix_world
    corners = [mw @ Vector(c) for c in obj.bound_box]
    hinge = mw.translation
    return max(corners, key=lambda c: (c - hinge).length)


def measure_swing_sign(obj, axis, angle_deg, door):
    """Which sign actually opens the panel, measured not assumed.

    A door must move its far edge AWAY from the centreline; a hood or boot lid
    must move its far edge UP. Both are measured on the real bound box; copying
    the sign from another panel is how a door ends up swinging through the car.
    """
    rest = obj.matrix_world.copy()
    pivot = rest.translation.copy()
    far = far_edge_point(obj)
    best = None
    for sign in (1.0, -1.0):
        rot = rotate_about(pivot, sign * angle_deg, axis)
        moved = rot @ far
        if door:
            outward = abs(moved.y) - abs(far.y)
        else:
            outward = moved.z - far.z
        if best is None or outward > best[0]:
            best = (outward, sign)
    obj.matrix_world = rest
    bpy.context.view_layer.update()
    return {"sign": best[1], "far_edge_travel_m": round(best[0], 5),
            "rule": "outward |y| for doors, upward z for hood/boot"}


def ease_open(t):
    return 4.0 * t * t * t if t < 0.5 else 1.0 - pow(-2.0 * t + 2.0, 3) / 2.0


def render_to(scene, path):
    scene.render.filepath = path
    bpy.ops.render.render(write_still=True)
    return path


def png_record(path, rel_root, source_state, ownership, command):
    size = os.path.getsize(path)
    with open(path, "rb") as fh:
        digest = hashlib.sha256(fh.read()).hexdigest()[:16]
    return {"asset": os.path.relpath(path, rel_root).replace(os.sep, "/"),
            "source_master": "MODEL_A_PRODUCTION_MASTER "
                             "(surface-offset-cavity-lightguide-v3)",
            "source_state": source_state,
            "native_dimensions": list(CANVAS),
            "decoded_rgba_bytes": CANVAS[0] * CANVAS[1] * 4,
            "png_bytes": size,
            "ownership": ownership,
            "sha256_16": digest,
            "command": command}


def render_lighting_state(scene, out_dir, name, state, samples, ownership):
    """One overlay frame for a lighting channel, via the frozen system."""
    inv = {"guides": {}, "cavities": {}, "lamps": {}}
    for obj in bpy.data.objects:
        if obj.type != "MESH":
            continue
        if obj.name.startswith("TailGuide_"):
            label = obj.name[len("TailGuide_"):].rsplit("_", 3)[0]
            inv["guides"].setdefault(label, []).append(obj)
        elif obj.name.startswith("Cavity_"):
            label = obj.name[len("Cavity_"):].rsplit("_", 1)[0]
            inv["cavities"].setdefault(label, []).append(obj)
        elif obj.name in states.LAMP_CHANNEL:
            inv["lamps"][obj.name] = obj
    guide_channels = tail.channel_materials()
    base_lens = None
    for obj in inv["lamps"].values():
        for slot in obj.material_slots:
            if slot.material is not None:
                base_lens = slot.material
                break
        if base_lens:
            break
    lens_channels = tail.lens_channel_materials(base=base_lens)
    segments = {label: {"guides": gs, "cavity": inv["cavities"].get(label, [])}
                for label, gs in inv["guides"].items()}
    tail.apply_state(state, segments, inv["lamps"], guide_channels,
                     lens_channels)
    bpy.context.view_layer.update()
    path = os.path.join(out_dir, f"{name}", "000.png")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    render_to(scene, path)
    return png_record(path, out_dir, state, ownership,
                      f"build_vehicle_state_assets.py --state {state}")


FRONT_LAMP_PATTERN = re.compile(
    r"(lights_head|foglight|foglights|tembus_depan|indicator_lights)", re.I)


def front_lamp_objects():
    return [o for o in bpy.data.objects
            if o.type == "MESH" and FRONT_LAMP_PATTERN.search(o.name)
            and o.material_slots]


def render_headlight_overlay(scene, out_dir, samples):
    """The front headlight overlay.

    `vehicle.headlight` in assets/manifest.json is the FRONT lamp, not the rear
    running light. It uses the same mechanism as the taillight channels - a
    copy of the frozen lens material with emission added for one channel - so
    there is still only one way a lamp is made to glow in this pipeline.
    """
    lamps = front_lamp_objects()
    if not lamps:
        return None, {"error": "no front lamp objects found"}
    saved = {}
    for obj in lamps:
        for index, slot in enumerate(obj.data.materials):
            if slot is None:
                continue
            saved[(obj.name, index)] = slot
            emissive = slot.copy()
            emissive.name = f"{slot.name}_HEADLIGHT"
            node = (emissive.node_tree.nodes.get("Principled BSDF")
                    if emissive.use_nodes else None)
            if node is not None:
                for key in ("Emission Color", "Emission"):
                    if key in node.inputs:
                        node.inputs[key].default_value = (1.0, 0.96, 0.88, 1.0)
                        break
                if "Emission Strength" in node.inputs:
                    node.inputs["Emission Strength"].default_value = 4.0
            obj.data.materials[index] = emissive
    bpy.context.view_layer.update()
    path = os.path.join(out_dir, "headlight_on", "000.png")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    render_to(scene, path)
    for (obj_name, index), material in saved.items():
        bpy.data.objects[obj_name].data.materials[index] = material
    bpy.context.view_layer.update()
    return png_record(path, out_dir, "HEADLIGHT (front lamps)", "FIXED_BODY",
                      "build_vehicle_state_assets.py --front-headlights"), {
        "lamps": [o.name for o in lamps],
        "mechanism": "frozen lens material copy + emission (same channel "
                     "mechanism as the taillight system)"}


def screen_affine(obj, rest, current):
    """The 2D affine a rigidly attached panel undergoes in this camera.

    Orthographic projection makes the mapping from a 3D rotation to screen
    space an exact 2D affine, so it is recovered from rigidly attached points
    instead of being approximated by a rotation about a projected pivot. The
    runtime needs it to move a lighting overlay that is mounted on a moving
    panel (the trunk carries the inner lamps).

    The three solving points are chosen to span the largest screen triangle:
    three nearly collinear points make the solve ill-conditioned and produced
    coefficients around 2.5 for a motion that is a rotation. The affine is then
    verified against every other sampled point, and the worst error in pixels
    is reported - this is only usable if it is exact for an orthographic
    camera.
    """
    from bpy_extras.object_utils import world_to_camera_view
    scene = bpy.context.scene
    cam = scene.camera
    width, height = scene.render.resolution_x, scene.render.resolution_y
    mw = obj.matrix_world
    step = max(1, len(obj.data.vertices) // 64)
    points = [mw @ v.co for v in list(obj.data.vertices)[::step]]
    if len(points) < 3:
        points = [mw @ Vector(c) for c in obj.bound_box]
    src, dst = [], []
    for c in points:
        p_closed = rest @ c
        p_open = current @ c
        a = world_to_camera_view(scene, cam, p_closed)
        b = world_to_camera_view(scene, cam, p_open)
        src.append((a.x * width, a.y * height))
        dst.append((b.x * width, b.y * height))
    best = None
    for i in range(len(src)):
        for j in range(i + 1, len(src)):
            for k in range(j + 1, len(src)):
                area = abs((src[j][0] - src[i][0]) * (src[k][1] - src[i][1])
                           - (src[k][0] - src[i][0]) * (src[j][1] - src[i][1]))
                if best is None or area > best[0]:
                    best = (area, i, j, k)
    if best is None or best[0] < 1e-6:
        return None
    _, i, j, k = best
    solve_src = [src[i], src[j], src[k]]
    solve_dst = [dst[i], dst[j], dst[k]]
    (x0, y0), (x1, y1), (x2, y2) = solve_src
    (u0, v0), (u1, v1), (u2, v2) = solve_dst
    denom = (x0 * (y1 - y2) + x1 * (y2 - y0) + x2 * (y0 - y1))
    if abs(denom) < 1e-9:
        return None
    def solve(vals):
        a = (vals[0] * (y1 - y2) + vals[1] * (y2 - y0)
             + vals[2] * (y0 - y1)) / denom
        b = (vals[0] * (x2 - x1) + vals[1] * (x0 - x2)
             + vals[2] * (x1 - x0)) / denom
        c = (vals[0] * (x1 * y2 - x2 * y1) + vals[1] * (x2 * y0 - x0 * y2)
             + vals[2] * (x0 * y1 - x1 * y0)) / denom
        return [round(a, 8), round(b, 8), round(c, 5)]
    affine = {"a": solve([u0, u1, u2]), "b": solve([v0, v1, v2])}
    worst = 0.0
    for (sx, sy), (tx, ty) in zip(src, dst):
        px = affine["a"][0] * sx + affine["a"][1] * sy + affine["a"][2]
        py = affine["b"][0] * sx + affine["b"][1] * sy + affine["b"][2]
        worst = max(worst, abs(px - tx), abs(py - ty))
    affine["verification"] = {
        "points_checked": len(src),
        "max_error_px": round(worst, 6),
        "exact": worst < 0.01}
    affine["note"] = (
        "screen (u,v) = A * (x,y) + c, in render pixels, bottom-up rows; "
        "maps the CLOSED screen position of a trunk-attached point to its "
        "position at this frame's opening angle")
    return affine


def main():
    args = parse_args()
    scene = open_master(args.master)
    setup_horizon_camera(scene)
    configure_render(scene, args.samples)
    os.makedirs(args.out, exist_ok=True)
    report = {"canvas": list(CANVAS), "camera": HORIZON_CAMERA,
              "samples": args.samples,
              "contract": "assets/manifest.json (v6-vehicle v2)",
              "assets": [], "panels": {}, "sequences": {}, "overlays": {}}

    # ---- static base + lighting overlays -------------------------------
    if not args.skip_state_renders:
        base_dir = os.path.join(args.out, "base")
        os.makedirs(base_dir, exist_ok=True)
        tail.apply_state("OFF", {}, {}, tail.channel_materials(),
                         tail.lens_channel_materials())
        base_path = os.path.join(base_dir, "000.png")
        render_to(scene, base_path)
        report["assets"].append(png_record(
            base_path, args.out, "OFF + all panels closed", "FIXED_BODY",
            "build_vehicle_state_assets.py"))
        for name, state in (("brake_on", "BRAKE"),
                            ("running_on", "HEADLIGHT"),
                            ("indicator_left", "LEFT_INDICATOR"),
                            ("indicator_right", "RIGHT_INDICATOR"),
                            ("hazard", "HAZARD")):
            record = render_lighting_state(scene, args.out, name, state,
                                           args.samples, "FIXED_BODY")
            report["assets"].append(record)
            if state == "BRAKE":
                report["overlays"]["vehicle.brake"] = record["asset"]
            if state == "HEADLIGHT":
                # The rear running light shares the brake lamp in the frozen
                # system; it is recorded separately from the FRONT headlight
                # overlay below.
                report["overlays"]["vehicle.running"] = record["asset"]
        front, front_info = render_headlight_overlay(scene, args.out,
                                                     args.samples)
        if front is not None:
            report["assets"].append(front)
            report["overlays"]["vehicle.headlight"] = front["asset"]
            report["front_headlight"] = front_info

    # ---- moving panels --------------------------------------------------
    for name, object_name, axis, angle, frames in PANELS:
        if args.only and args.only != name:
            continue
        obj = bpy.data.objects.get(object_name)
        if obj is None:
            report["panels"][name] = {"error": f"{object_name} missing"}
            continue
        count = args.frames or frames
        rest = obj.matrix_world.copy()
        info = panel_report(obj, axis)
        info.update(measure_swing_sign(obj, axis, angle, axis == "Z"))
        info.update({"object": object_name, "axis": axis,
                     "open_angle_deg": angle, "frames": count,
                     "fps": DOOR_FPS if axis == "Z" else DOOR_FPS,
                     "open_duration_s": round((count - 1) / float(DOOR_FPS), 3),
                     "close_duration_s": round(
                         (count - 1) / float(DOOR_FPS) * (0.54 / 0.62), 3),
                     "easing": "ease_in_out_cubic (open); the close animation "
                               "plays the same frames backwards at its own "
                               "duration"})
        pivot = rest.translation.copy()
        out_dir = os.path.join(args.out, name)
        os.makedirs(out_dir, exist_ok=True)
        frames_written = []
        affines = []
        for i in range(count):
            t = i / float(count - 1)
            applied = ease_open(t) * angle * info["sign"]
            obj.matrix_world = rotate_about(pivot, applied, axis) @ rest
            bpy.context.view_layer.update()
            if name == "trunk":
                # The trunk carries the inner lamps, so a lighting overlay
                # mounted on them has to follow the same screen transform.
                affines.append(screen_affine(obj, rest, obj.matrix_world))
            path = os.path.join(out_dir, f"{i:03d}.png")
            render_to(scene, path)
            frames_written.append(path)
        obj.matrix_world = rest
        bpy.context.view_layer.update()
        info["png_bytes_total"] = sum(os.path.getsize(p) for p in frames_written)
        info["decoded_rgba_bytes_total"] = count * CANVAS[0] * CANVAS[1] * 4
        info["decoded_rgba_bytes_per_frame"] = CANVAS[0] * CANVAS[1] * 4
        if affines:
            info["lighting_overlay_screen_affine_per_frame"] = affines
            info["carries_lighting"] = True
        report["panels"][name] = info
        report["sequences"][f"vehicle.{name.replace('_', '.')}"] = {
            "dir": name, "frames": count, "fps": info["fps"],
            "mode": "to_state"}
        print(f"[assets] {name}: hinge={info['hinge']} "
              f"on_edge={info['hinge_on_edge']} sign={info['sign']:+} "
              f"travel={info['far_edge_travel_m']}m frames={count} "
              f"png={info['png_bytes_total']}B")

    report["totals"] = {
        "png_bytes": sum(a["png_bytes"] for a in report["assets"])
        + sum(p.get("png_bytes_total", 0) for p in report["panels"].values()),
        "assets": len(report["assets"]),
        "panels": len([p for p in report["panels"].values()
                       if "error" not in p]),
    }
    os.makedirs(os.path.dirname(args.report), exist_ok=True)
    with open(args.report, "w") as fh:
        json.dump(report, fh, indent=2)
        fh.write("\n")
    if args.write_marker:
        marker = os.path.join(args.out, "MODEL3_SOURCE.json")
        with open(marker, "w") as fh:
            json.dump({"source": "MODEL_A_PRODUCTION_MASTER",
                       "taillight_geometry_version":
                           "surface-offset-cavity-lightguide-v3",
                       "builder": "tools/blender/build_vehicle_state_assets.py",
                       "canvas": list(CANVAS)}, fh, indent=2)
            fh.write("\n")
    print(f"[assets] -> {args.report} "
          f"(png {report['totals']['png_bytes'] / 1048576.0:.2f} MB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
