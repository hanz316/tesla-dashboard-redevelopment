#!/usr/bin/env python3
"""Door_FL opening animation prototype + benchmark asset generator.

Frame 1 of the animation work. Only the left front door.

* verifies the hinge pivot objectively (origin vs door bbox) and with a
  BVH overlap sweep that finds the angle where the door would start
  intersecting the body/fender
* animates closed -> open with an ease-in-out curve (slow start, natural
  middle, decelerating finish; no overshoot, no bounce)
* renders a fixed canvas + fixed anchor PNG sequence at a requested
  runtime vehicle width and fps, for the T113 decode benchmarks

Non-destructive: the source FBX / master .blend are never modified.

Usage:
    blender -b -P tools/blender/render_door_animation.py -- --verify
    blender -b -P tools/blender/render_door_animation.py -- \\
        --fps 30 --vehicle-width 600 --out assets/rendered/door_fl/600_30
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
    from mathutils.bvhtree import BVHTree
except ImportError:  # pragma: no cover
    sys.exit("Run inside Blender")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import hmi_studio_v2  # noqa: E402
import hmi_studio_v3  # noqa: E402
import render_vehicle_visual_v2 as vehicle_v2  # noqa: E402
import render_vehicle_visual_v3 as vehicle_v3  # noqa: E402

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
DEFAULT_INPUT = os.path.join(REPO_ROOT, "assets", "source", "download",
                             "model_a_ameer", "source", "tesla_car1.fbx")
MODEL3_LENGTH_M = 4.694

DOOR_OBJECT = "door_lf"
BODY_OBJECTS = ("body", "bodysills", "base", "front_black", "bonnet_ok")

# Runtime visual widths requested for the benchmark matrix.
VEHICLE_WIDTHS = {"400": 400, "600": 600, "800": 800}

# The car occupies ~78% of the canvas width once the door is open, leaving a
# fixed margin so every frame shares one canvas and one anchor.
OCCUPANCY = 0.78
CANVAS_ASPECT = 760.0 / 1100.0

# Part 10/11: open and close are separate animations with independent timing
# and independent easing. Close is deliberately slightly faster than open.
DEFAULT_OPEN_DURATION_S = 0.62
DEFAULT_CLOSE_DURATION_S = 0.54
DEFAULT_DURATION_S = DEFAULT_OPEN_DURATION_S
DEFAULT_OPEN_ANGLE_DEG = 52.0
# Rotation sign about the vertical hinge axis that swings this door OUT of
# the car. Measured, not assumed - see swing_direction_report(). +Z rotates
# the door through the body (far-edge y delta -0.073 m); -Z pushes the far
# edge outward (+0.929 m at 52 deg).
OPEN_SIGN = -1.0


def parse_args():
    argv = sys.argv
    argv = argv[argv.index("--") + 1:] if "--" in argv else []
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", default=DEFAULT_INPUT)
    ap.add_argument("--verify", action="store_true",
                    help="print pivot + collision sweep and exit")
    ap.add_argument("--door", default=DOOR_OBJECT)
    ap.add_argument("--fps", type=int, default=30, choices=[24, 30, 60])
    ap.add_argument("--duration", type=float, default=None,
                    help="override BOTH open and close durations")
    ap.add_argument("--open-duration", type=float,
                    default=DEFAULT_OPEN_DURATION_S)
    ap.add_argument("--close-duration", type=float,
                    default=DEFAULT_CLOSE_DURATION_S)
    ap.add_argument("--direction", default="both",
                    choices=["open", "close", "both"],
                    help="render one direction or both into <out>/<direction>/")
    ap.add_argument("--open-angle", type=float, default=DEFAULT_OPEN_ANGLE_DEG)
    ap.add_argument("--vehicle-width", type=int, default=600,
                    choices=[400, 600, 800])
    ap.add_argument("--canvas", default=None,
                    help="override the derived WxH canvas, e.g. 2200x1520 "
                         "for a review-grade still pair")
    ap.add_argument("--out", default=None)
    ap.add_argument("--body", default=None,
                    help="material preset; defaults per --material version")
    ap.add_argument("--material", default="v3", choices=["v2", "v3"])
    ap.add_argument("--look", default="normal", choices=["normal", "soft"])
    ap.add_argument("--engine", default="eevee", choices=["eevee", "cycles"])
    ap.add_argument("--samples", type=int, default=64)
    ap.add_argument("--supersample", type=int, default=1)
    ap.add_argument("--azimuth", type=float, default=-32.0,
                    help="camera azimuth in degrees; +32 looks at the -Y "
                         "(passenger) side, -32 at the +Y (driver) side, "
                         "which is the side door_lf lives on")
    return ap.parse_args(argv)


def import_and_normalise(path):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.fbx(filepath=path)
    meshes = [o for o in bpy.data.objects if o.type == "MESH"]
    for obj in meshes:
        obj.hide_render = False
        obj.hide_viewport = False
    bpy.context.view_layer.update()
    roots = [o for o in bpy.data.objects if o.parent is None] or list(meshes)

    rot = Matrix.Rotation(math.radians(-90.0), 4, "Z")   # +Y (nose) -> +X
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
    return meshes


def door_pivot_report(door):
    lo = Vector((1e9, 1e9, 1e9))
    hi = Vector((-1e9, -1e9, -1e9))
    for corner in door.bound_box:
        w = door.matrix_world @ Vector(corner)
        lo = Vector((min(lo.x, w.x), min(lo.y, w.y), min(lo.z, w.z)))
        hi = Vector((max(hi.x, w.x), max(hi.y, w.y), max(hi.z, w.z)))
    origin = door.matrix_world.translation
    print("[door] pivot check (normalised space, nose +X):")
    print(f"[door]   door bbox min={tuple(round(v,4) for v in lo)} "
          f"max={tuple(round(v,4) for v in hi)}")
    print(f"[door]   origin={tuple(round(v,4) for v in origin)}")
    print(f"[door]   origin to bbox max X = {hi.x - origin.x:+.4f} m "
          f"(door length {hi.x - lo.x:.4f} m)")
    print(f"[door]   origin to bbox min Y = {origin.y - lo.y:+.4f} m "
          f"(door width {hi.y - lo.y:.4f} m)")
    verdict = "ON THE HINGE (front edge)" if abs(hi.x - origin.x) < 0.05 \
        else "NOT on the front edge - needs fixing"
    print(f"[door]   verdict: {verdict}")
    return lo, hi, origin


def collision_sweep(door, angle_deg, samples):
    """Rotate the door about its hinge and test BVH overlap with the body.

    Both trees must live in the SAME space or the test is meaningless. The
    first version of this function compared the door's and the body's *local*
    vertices, which are expressed relative to two different object matrices,
    so it reported "0 overlapping pairs" for every angle including 0 deg
    (where the door is by definition attached to the body). Everything here
    is therefore converted to world space first.
    """
    body_objs = [bpy.data.objects[n] for n in BODY_OBJECTS
                 if n in bpy.data.objects]
    if not body_objs:
        print("[door] no body objects found for the collision sweep")
        return None
    print(f"[door]   collision reference bodies: "
          f"{sorted(o.name for o in body_objs)}")

    rest_matrix = door.matrix_world.copy()
    results = []

    def world_tree(obj):
        deps = bpy.context.evaluated_depsgraph_get()
        ev = obj.evaluated_get(deps)
        mesh = ev.to_mesh()
        mw = obj.matrix_world
        verts = [mw @ v.co for v in mesh.vertices]
        polys = [tuple(p.vertices) for p in mesh.polygons]
        tree = BVHTree.FromPolygons(verts, polys, all_triangles=False)
        ev.to_mesh_clear()
        return tree

    deps = bpy.context.evaluated_depsgraph_get()
    body_trees = [world_tree(obj) for obj in body_objs]

    # The door geometry sits *inside* the body aperture, so it overlaps the
    # body even at 0 deg. That baseline is a property of the source model, not
    # of the animation. Only contacts that touch a body face the door did NOT
    # already touch when closed are real "the door would clip through the
    # fender/A-pillar" events.
    baseline = bpy.data.objects[DOOR_OBJECT].matrix_world.copy()
    door = bpy.data.objects[DOOR_OBJECT]
    door.matrix_world = baseline
    bpy.context.view_layer.update()
    closed_tree = world_tree(door)
    closed_faces = [set() for _ in body_trees]
    closed_door_faces = set()
    for index, tree in enumerate(body_trees):
        for door_face, body_face in closed_tree.overlap(tree):
            closed_faces[index].add(body_face)
            closed_door_faces.add(door_face)
    print(f"[door]   closed-state contact baseline: "
          f"{sum(len(s) for s in closed_faces)} body faces, "
          f"{len(closed_door_faces)} door faces")

    for step in range(0, int(angle_deg) + 1, samples):
        door.matrix_world = door_open_matrix(rest_matrix, OPEN_SIGN * step)
        bpy.context.view_layer.update()
        door_tree = world_tree(door)
        hits = 0
        new_contacts = 0
        skin_clips = 0
        for index, tree in enumerate(body_trees):
            for door_face, body_face in door_tree.overlap(tree):
                hits += 1
                if body_face not in closed_faces[index]:
                    new_contacts += 1
                if door_face not in closed_door_faces:
                    # A door face that is freely visible when closed has been
                    # driven into the body: this is what a viewer would read
                    # as the door clipping through the fender / A-pillar.
                    skin_clips += 1
        swing = door_swing(rest_matrix, OPEN_SIGN * step)
        results.append((step, hits, new_contacts, skin_clips, swing))
        print(f"[door]   angle {step:3d} deg -> overlapping pairs: {hits:5d}"
              f" | new body faces: {new_contacts:4d}"
              f" | visible-skin clips: {skin_clips:4d}"
              f" | outer-edge travel {swing:.3f} m")

    door.matrix_world = rest_matrix
    bpy.context.view_layer.update()
    return results


def door_open_matrix(rest_matrix, angle_deg):
    """Rotate the door about the vertical axis THROUGH ITS HINGE.

    `Matrix.Rotation(...) @ rest_matrix` would rotate about the world origin,
    which sits ~1.4 m away from this hinge, so the door would orbit across the
    car instead of swinging on its hinge.
    """
    pivot = rest_matrix.translation.copy()
    return (Matrix.Translation(pivot)
            @ Matrix.Rotation(math.radians(angle_deg), 4, "Z")
            @ Matrix.Translation(-pivot)
            @ rest_matrix)


def door_swing(rest_matrix, angle_deg):
    """How far the door's outer edge actually travels, in metres."""
    door = bpy.data.objects[DOOR_OBJECT]
    rest = door.bound_box
    far = max((Vector(c) for c in rest), key=lambda v: (v - Vector((0, 0, 0))).length)
    start = rest_matrix @ far
    end = door_open_matrix(rest_matrix, angle_deg) @ far
    return (end - start).length


def door_world_bbox(door):
    lo = Vector((1e9, 1e9, 1e9))
    hi = Vector((-1e9, -1e9, -1e9))
    for corner in door.bound_box:
        w = door.matrix_world @ Vector(corner)
        lo = Vector((min(lo.x, w.x), min(lo.y, w.y), min(lo.z, w.z)))
        hi = Vector((max(hi.x, w.x), max(hi.y, w.y), max(hi.z, w.z)))
    return lo, hi


def swing_direction_report(door, rest_matrix, angle_deg):
    """Which sign of Z actually swings the door OUT of the car?

    The body centreline is near y = 0 and this door lives on +Y, so a door
    that opens must push its rear edge to LARGER +Y. Measuring that is the
    only reliable way to pick the sign: inferring it from a bbox delta taken
    in the wrong coordinate space is how the first version of this script
    ended up rotating the door through the car body.
    """
    door.matrix_world = rest_matrix
    bpy.context.view_layer.update()
    lo0, hi0 = door_world_bbox(door)
    print(f"[door]   closed: y range {lo0.y:.3f}..{hi0.y:.3f}")
    for sign, label in ((+1.0, "+Z"), (-1.0, "-Z")):
        door.matrix_world = door_open_matrix(rest_matrix, sign * angle_deg)
        bpy.context.view_layer.update()
        lo, hi = door_world_bbox(door)
        outward = hi.y - hi0.y
        verdict = "OUTWARD (away from the car)" if outward > 0.2 \
            else ("INWARD (through the car) - wrong sign" if outward < 0
                  else "ambiguous")
        print(f"[door]   {label} {angle_deg:.0f} deg: y range "
              f"{lo.y:.3f}..{hi.y:.3f} | far-edge y delta {outward:+.3f} m "
              f"-> {verdict}")
    door.matrix_world = rest_matrix
    bpy.context.view_layer.update()


def ease_in_out_cubic(t):
    """OPEN easing: slow initial release, smooth acceleration, decelerating
    finish. No spring, no bounce, no overshoot."""
    if t < 0.5:
        return 4.0 * t * t * t
    return 1.0 - pow(-2.0 * t + 2.0, 3.0) / 2.0


def ease_in_out_quint(t):
    """CLOSE easing: quintic smootherstep.

    Deliberately NOT the mirror of the open curve. A closed door has to settle
    against the seal, so this has zero velocity AND zero acceleration at both
    ends: the pull-off is softer and the arrival at the latch is damped, which
    reads as a heavier, better-damped part than simply reversing the open.
    Still strictly monotonic and bounded to [0, 1], so no overshoot.
    """
    return t * t * t * (t * (t * 6.0 - 15.0) + 10.0)


def setup_camera_and_render(vehicle_width, canvas_w, canvas_h, engine, samples,
                            supersample, out_dir, azimuth_deg=32.0):
    # Same framing family as V2-A so the animation matches the static look.
    az = math.radians(azimuth_deg)
    el = math.radians(22.0)
    target = Vector((0.0, 0.0, 0.60))
    direction = Vector((-math.cos(el) * math.cos(az),
                        -math.cos(el) * math.sin(az), math.sin(el)))
    cam_data = bpy.data.cameras.new("Camera_Horizon")
    cam_data.type = "ORTHO"
    aspect = canvas_w / float(canvas_h)
    base = vehicle_width / float(vehicle_width) * (MODEL3_LENGTH_M * 1.0)
    # ortho_scale is chosen so the vehicle occupies OCCUPANCY of the width.
    ortho = (MODEL3_LENGTH_M * 1.0) / OCCUPANCY
    cam_data.ortho_scale = max(ortho, ortho / aspect)
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
    del base

    scene = bpy.context.scene
    if engine == "cycles":
        addon_utils.enable("cycles", default_set=True, persistent=True)
        scene.render.engine = "CYCLES"
        if hasattr(scene, "cycles"):
            scene.cycles.samples = samples
            scene.cycles.use_denoising = True
            scene.cycles.max_bounces = 6
            scene.cycles.use_adaptive_sampling = True
    else:
        engines = [i.identifier for i in
                   scene.render.bl_rna.properties["engine"].enum_items]
        for candidate in ("BLENDER_EEVEE_NEXT", "BLENDER_EEVEE"):
            if candidate in engines:
                scene.render.engine = candidate
                break
        eevee = getattr(scene, "eevee", None)
        if eevee is not None and hasattr(eevee, "taa_render_samples"):
            eevee.taa_render_samples = samples

    scene.render.film_transparent = True
    scene.render.resolution_x = canvas_w
    scene.render.resolution_y = canvas_h
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGBA"
    scene.render.image_settings.compression = 90
    try:
        scene.view_settings.view_transform = "AgX"
    except Exception:
        pass
    scene.view_settings.exposure = 0.30
    os.makedirs(out_dir, exist_ok=True)
    scene.render.filepath = os.path.join(out_dir, "")
    return scene


def main():
    args = parse_args()
    meshes = import_and_normalise(args.input)
    door = bpy.data.objects.get(args.door)
    if door is None:
        sys.exit(f"door object not found: {args.door}")

    if args.verify:
        door_pivot_report(door)
        print("[door] swing direction check:")
        swing_direction_report(door, door.matrix_world.copy(), args.open_angle)
        print(f"[door] collision sweep (sign {OPEN_SIGN:+.0f}Z):")
        collision_sweep(door, 70.0, 5)
        return

    if args.out is None:
        sys.exit("--out is required for rendering")

    if args.material == "v3":
        preset = args.body or "silver_v3"
        hmi_studio_v3.apply_v3_materials(meshes, preset)
        hmi_studio_v3.build_reflection_studio_v3()
        hmi_studio_v3.build_light_rig_v3()
    else:
        preset = args.body or "silver01"
        hmi_studio_v2.apply_v2_materials(meshes, preset)
        hmi_studio_v2.build_reflection_studio()
        # Without these lights the scene has no emitters at all
        # (read_factory_settings(use_empty=True) removes the world) and every
        # frame renders as a pure black silhouette.
        vehicle_v2.setup_key_rig()

    if args.canvas:
        canvas_w, canvas_h = (int(v) for v in args.canvas.lower().split("x"))
    else:
        canvas_w = int(round(args.vehicle_width / OCCUPANCY))
        canvas_h = int(round(canvas_w * CANVAS_ASPECT))
    setup_camera_and_render(args.vehicle_width, canvas_w, canvas_h,
                            args.engine, args.samples, args.supersample,
                            args.out, args.azimuth)
    # Same filmic look as the V3 stills, so the animation cuts together with
    # them instead of looking like a different render.
    vehicle_v3.apply_look(bpy.context.scene, args.look, None)

    open_duration = (args.duration if args.duration is not None
                     else args.open_duration)
    close_duration = (args.duration if args.duration is not None
                      else args.close_duration)

    rest_matrix = door.matrix_world.copy()
    scene = bpy.context.scene
    print(f"[door] material={args.material} preset={preset} look={args.look} "
          f"fps={args.fps} open={open_duration}s close={close_duration}s "
          f"open_angle={args.open_angle} vehicle_width={args.vehicle_width} "
          f"canvas={canvas_w}x{canvas_h}")

    directions = (["open", "close"] if args.direction == "both"
                  else [args.direction])
    for direction in directions:
        duration = open_duration if direction == "open" else close_duration
        frame_count = max(2, int(round(duration * args.fps)) + 1)
        out_dir = os.path.join(args.out, direction)
        os.makedirs(out_dir, exist_ok=True)
        print(f"[door] {direction}: duration={duration}s frames={frame_count}")
        start = time.time()
        for index in range(frame_count):
            t = index / float(frame_count - 1)
            if direction == "open":
                angle = args.open_angle * ease_in_out_cubic(t)
            else:
                # Close runs from fully open back to the seal.
                angle = args.open_angle * (1.0 - ease_in_out_quint(t))
            door.matrix_world = door_open_matrix(rest_matrix,
                                                 OPEN_SIGN * angle)
            scene.frame_set(index + 1)
            scene.render.filepath = os.path.join(out_dir, f"{index:03d}.png")
            bpy.ops.render.render(write_still=True)
            if index % 5 == 0 or index == frame_count - 1:
                print(f"[door]   {direction} frame {index:03d} "
                      f"angle={angle:5.1f} deg ({time.time()-start:.1f}s)")
        total = time.time() - start
        print(f"[door] RENDER_TIME {direction} {total:.1f}s for "
              f"{frame_count} frames ({total/frame_count:.2f}s/frame) "
              f"-> {out_dir}")


if __name__ == "__main__":
    main()
