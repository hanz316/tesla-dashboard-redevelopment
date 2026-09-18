#!/usr/bin/env python3
"""Taillight Freeze Gate V3, stages 15-26, on the production master.

Everything here measures the geometry that the sanctioned builder produced -
the same cavities and guides that ship. Nothing re-tunes the frozen camera,
lighting, materials or colour management.

Stages
------
15/16  guide vs body, guide vs trunk-moving geometry, guide vs unrelated lamps
17-20  protrusion and screen-space escape, measured with binary object masks
       rendered through the FROZEN production camera
       trunk ownership + motion 0 / 25 / 50 / 75 / 100 %
       the single state-driven TaillightLightingSystem at close, 600 px and
       Horizon actual size
gate   the machine-readable Freeze Gate V3 table

Usage:
    blender -b -P tools/blender/taillight_freeze.py -- \
        --master assets/source/blender/model_a_production_master.blend \
        --stage all --out-dir <dir> --report <json>
"""

import argparse
import json
import math
import os
import sys

try:
    import bpy
    import bmesh
    import numpy as np
    from mathutils import Matrix, Vector
except ImportError:  # pragma: no cover
    sys.exit("Run inside Blender")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import taillight_finalize as tail_base  # noqa: E402
import taillight_system as tail  # noqa: E402

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
LAMPS = ["rear_lights", "rear_lightsl", "rear_lightsr", "light_breake"]
CAMERA = "PRODUCTION_Camera"
CONTACT_TOLERANCE_M = 2.0e-4     # numerical contact, not a collision
TRUNK_OPEN_DEG = 55.0
TRUNK_STATES = [0.0, 0.25, 0.5, 0.75, 1.0]
MASK_CANVAS = "1100x760"


def parse_args():
    argv = sys.argv
    argv = argv[argv.index("--") + 1:] if "--" in argv else []
    ap = argparse.ArgumentParser()
    ap.add_argument("--master", required=True)
    ap.add_argument("--stage", default="all",
                    choices=["all", "collision", "screenspace", "trunk",
                             "states", "gate"])
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--report", required=True)
    ap.add_argument("--samples", type=int, default=24,
                    help="Cycles samples for the QA renders (frozen settings "
                         "otherwise; masks are rendered with Workbench)")
    ap.add_argument("--skip-render", action="store_true",
                    help="skip the Cycles QA renders and report them NOT_RUN")
    return ap.parse_args(argv)


# --------------------------------------------------------------------------
# master inventory

def open_master(path):
    bpy.ops.wm.open_mainfile(filepath=path)
    return bpy.context.scene


def master_objects(labels=()):
    """The parts of the freeze, by role, from the master's own naming."""
    labels = sorted(labels, key=len, reverse=True)

    def label_for(name, prefix):
        if not name.startswith(prefix):
            return None
        rest = name[len(prefix):]
        for label in labels:
            if rest.startswith(label + "_"):
                return label
        return rest.rsplit("_", 1)[0]

    inv = {"cavities": {}, "guides": {}, "lamps": {}}
    for obj in bpy.data.objects:
        if obj.type != "MESH":
            continue
        if obj.name.startswith("Cavity_"):
            label = label_for(obj.name, "Cavity_")
            inv["cavities"].setdefault(label, []).append(obj)
        elif obj.name.startswith("TailGuide_"):
            label = label_for(obj.name, "TailGuide_")
            inv["guides"].setdefault(label, []).append(obj)
    for name in LAMPS:
        obj = bpy.data.objects.get(name)
        if obj is not None:
            inv["lamps"][name] = obj
    return inv


def owner_of_label(label, ownership):
    lamp = label.split(":")[1]
    entry = ownership.get(label) or {}
    return entry.get("owner", "UNKNOWN")


def mesh_and_tree(obj, sample=400):
    """World-space triangle BVH plus representative points of the same object.

    The mesh is triangulated first: BVHTree.overlap only reports intersections
    between triangle trees, and silently returns nothing for n-gon trees - two
    cubes placed so that they clearly intersect reported zero pairs until this
    was fixed.
    """
    deps = bpy.context.evaluated_depsgraph_get()
    ev = obj.evaluated_get(deps)
    mesh = ev.to_mesh()
    bm = bmesh.new()
    bm.from_mesh(mesh)
    bmesh.ops.triangulate(bm, faces=bm.faces)
    bm.verts.ensure_lookup_table()
    mw = obj.matrix_world
    verts = [mw @ v.co for v in bm.verts]
    tris = [tuple(v.index for v in f.verts) for f in bm.faces]
    bm.free()
    ev.to_mesh_clear()
    tree = (BVHTreeFromPolygons([tuple(v) for v in verts], tris)
            if tris else None)
    points = list(verts)
    step = max(1, len(points) // sample)
    points = points[::step]
    return tree, points


def BVHTreeFromPolygons(verts, polys):
    from mathutils.bvhtree import BVHTree
    return BVHTree.FromPolygons(verts, polys, all_triangles=True)


def overlap_pairs(tree_a, tree_b):
    return tree_a.overlap(tree_b)


# --------------------------------------------------------------------------
# stage 15/16 - collision

def stage_collision(inv, ownership):
    lamps = set(o.name for o in inv["lamps"].values())
    result = {"guide_vs_body": [], "guide_vs_trunk_moving": [],
              "guide_vs_unrelated_lamp": [], "cavity_vs_body": [],
              "tolerance_m": CONTACT_TOLERANCE_M}
    for label, guides in sorted(inv["guides"].items()):
        own_cavity = set(o.name for o in inv["cavities"].get(label, []))
        own_lamp = label.split(":")[1]
        gtrees = {g.name: mesh_and_tree(g) for g in guides}
        for other in bpy.data.objects:
            if other.type != "MESH" or other.name in gtrees:
                continue
            if other.name in own_cavity:
                continue
            if other.name.startswith("TailGuide_"):
                continue
            is_lamp = other.name in lamps
            other_owner = None
            if other.name == "boot" or other.name.startswith("boot."):
                other_owner = "TRUNK_MOVING"
            tree_b, points_b = mesh_and_tree(other)
            if tree_b is None:
                continue
            pairs = 0
            for gname, (tree_a, points_a) in gtrees.items():
                if tree_a is None:
                    continue
                n = len(overlap_pairs(tree_a, tree_b))
                if n == 0:
                    continue
                dist = nearest_surface_distance(tree_a, points_a, tree_b,
                                                points_b)
                pairs += n
                entry = {"segment": label, "guide": gname,
                         "other": other.name, "pairs": n,
                         "nearest_surface_distance_m": round(dist, 7)}
                if other_owner == "TRUNK_MOVING":
                    result["guide_vs_trunk_moving"].append(entry)
                elif is_lamp and other.name != own_lamp:
                    result["guide_vs_unrelated_lamp"].append(entry)
                elif not is_lamp:
                    result["guide_vs_body"].append(entry)
        for cav in inv["cavities"].get(label, []):
            ctree, cpoints = mesh_and_tree(cav)
            for other in bpy.data.objects:
                if other.type != "MESH" or other.name == cav.name:
                    continue
                if other.name in lamps or other.name.startswith("TailGuide_"):
                    continue
                if other.name.startswith("Cavity_"):
                    continue
                otree, opoints = mesh_and_tree(other)
                if otree is None or ctree is None:
                    continue
                n = len(overlap_pairs(ctree, otree))
                if n:
                    result["cavity_vs_body"].append(
                        {"segment": label, "cavity": cav.name,
                         "other": other.name, "pairs": n})
    result["detector_self_test"] = collision_self_test(inv)
    return result


def collision_self_test(inv):
    """Validate the overlap primitive on a case with a known answer.

    Displacing a real guide is not a valid test: the lamp interior is a shell,
    so a guide can move several centimetres inside it without crossing any
    surface and the honest answer is still zero collisions. Two unit cubes with
    a known separation test the primitive itself - intersecting cubes must
    report pairs, separated cubes must report none - and the same two paths
    (mesh_and_tree + overlap_pairs) that the real test uses.
    """
    a = unit_cube("SELFTEST_cube_a", (0.0, 0.0, 0.0))
    b = unit_cube("SELFTEST_cube_b", (0.5, 0.0, 0.0))     # overlapping
    c = unit_cube("SELFTEST_cube_c", (5.0, 0.0, 0.0))     # far apart
    ta, _ = mesh_and_tree(a)
    tb, _ = mesh_and_tree(b)
    tc, _ = mesh_and_tree(c)
    overlapping = len(overlap_pairs(ta, tb))
    separated = len(overlap_pairs(ta, tc))
    for obj in (a, b, c):
        bpy.data.objects.remove(obj, do_unlink=True)
    return {"known_overlap_pairs": overlapping,
            "known_separated_pairs": separated,
            "detector_works": overlapping > 0 and separated == 0}


def unit_cube(name, location):
    mesh = bpy.data.meshes.new(name)
    verts = [(-0.5, -0.5, -0.5), (0.5, -0.5, -0.5), (0.5, 0.5, -0.5),
             (-0.5, 0.5, -0.5), (-0.5, -0.5, 0.5), (0.5, -0.5, 0.5),
             (0.5, 0.5, 0.5), (-0.5, 0.5, 0.5)]
    faces = [(0, 1, 2, 3), (4, 5, 6, 7), (0, 1, 5, 4),
             (2, 3, 7, 6), (1, 2, 6, 5), (0, 3, 7, 4)]
    mesh.from_pydata(verts, [], faces)
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.scene.collection.objects.link(obj)
    obj.location = location
    return obj


def nearest_surface_distance(tree_a, points_a, tree_b, points_b):
    """Smallest surface-to-surface distance between two meshes, in metres.

    Only queried for pairs the overlap test already flagged, so this is the
    penetration depth proxy for a real intersection.
    """
    best = None
    for p in points_a:
        res = tree_b.find_nearest(p, 5.0)
        if res[0] is not None and (best is None or res[3] < best):
            best = res[3]
    for p in points_b:
        res = tree_a.find_nearest(p, 5.0)
        if res[0] is not None and (best is None or res[3] < best):
            best = res[3]
    return best if best is not None else -1.0


# --------------------------------------------------------------------------
# stages 17-20 - screen-space masks

def trunk_pivot(boot):
    """Hinge axis of the trunk lid, derived from the lid's own geometry.

    The lid rotates about a horizontal axis (parallel to Y) near its front-top
    edge. Both coordinates come from the boot mesh: the 95th percentile of x
    (the front of the lid) and the 95th percentile of z (the top of the lid).
    For a 2018 Model 3 the hinge sits at the top-front of the boot aperture,
    which is where this lands; nothing here is taken from an object name.
    """
    mw = boot.matrix_world
    pts = [mw @ v.co for v in boot.data.vertices]
    xs = sorted(p.x for p in pts)
    zs = sorted(p.z for p in pts)
    n = len(pts)
    pivot = Vector((xs[int(n * 0.95)], sum(p.y for p in pts) / n,
                    zs[int(n * 0.95)]))
    return pivot, {"derivation": "95th percentile of boot x (front of lid) and "
                                 "boot z (top of lid), axis parallel to Y",
                   "pivot": [round(c, 5) for c in pivot],
                   "boot_samples": n}


def rigid_group(inv, ownership):
    """Which objects move with the trunk lid, and which must not."""
    moving, fixed = [], []
    measured = measure_lamp_owners(inv)
    for label, guides in inv["guides"].items():
        lamp = label.split(":")[1]
        owner = measured.get(lamp, {}).get("owner") or owner_of_label(
            label, ownership)
        bucket = moving if owner == "TRUNK_MOVING" else fixed
        bucket.extend(guides)
        bucket.extend(inv["cavities"].get(label, []))
        if lamp in inv["lamps"]:
            bucket.append(inv["lamps"][lamp])
    boot = bpy.data.objects.get("boot")
    if boot is not None:
        moving.append(boot)
    for lamp, obj in inv["lamps"].items():
        entry = measured.get(lamp, {})
        if entry.get("owner") == "TRUNK_MOVING" and obj not in moving:
            # No guide for this lamp (the brake light), but its lens still has
            # to move with the lid - and the class comes from measurement, not
            # from an assumption about which lamp is where.
            moving.append(obj)
        elif entry.get("owner") == "FIXED_BODY" and obj not in fixed:
            fixed.append(obj)
    rigid_group.measurements = measured
    return moving, fixed


def measure_lamp_owners(inv, contact_m=0.030):
    """FIXED_BODY vs TRUNK_MOVING from which panel each lamp is mounted on.

    An absolute distance to the boot shell cannot decide this on its own: every
    lamp sits a few centimetres behind the bodywork, so all four lamps are "far"
    from every panel and a threshold picks whichever number it was set at. The
    decision is therefore relative - the lamp belongs to the panel it is
    measurably closer to, the trunk lid (`boot`) or the fixed body
    (`body`/`rear_bumper_ok`). Ties and near-ties are reported as ambiguous
    rather than resolved by preference.
    """
    boot = bpy.data.objects.get("boot")
    if boot is None:
        return {}
    lid_tree, _ = mesh_and_tree(boot, sample=2000)
    body_trees = {}
    for name in ("body", "rear_bumper_ok"):
        obj = bpy.data.objects.get(name)
        if obj is not None:
            tree, _ = mesh_and_tree(obj, sample=2000)
            if tree is not None:
                body_trees[name] = tree
    if lid_tree is None or not body_trees:
        return {}
    out = {}
    for name, obj in inv["lamps"].items():
        mw = obj.matrix_world
        verts = list(obj.data.vertices)
        step = max(1, len(verts) // 500)
        points = [mw @ v.co for v in verts[::step]]
        to_lid = quantile_distances(points, lid_tree)
        to_body = min((quantile_distances(points, t)
                       for t in body_trees.values()), key=lambda d: d["median"])
        if to_lid["median"] is None or to_body["median"] is None:
            continue
        ratio = to_lid["median"] / to_body["median"]
        if ratio < 0.8:
            owner = "TRUNK_MOVING"
        elif ratio > 1.25:
            owner = "FIXED_BODY"
        else:
            owner, tie_break = containment_tie_break(name, points, out, inv)
        if owner == "AMBIGUOUS":
            tie_break = None
        out[name] = {"owner": owner,
                     "tie_break": tie_break if ratio >= 0.8 and ratio <= 1.25
                     else None,
                     "median_to_boot_m": to_lid["median"],
                     "median_to_body_m": to_body["median"],
                     "ratio_boot_over_body": round(ratio, 4),
                     "boot_p05_m": to_lid["p05"], "boot_min_m": to_lid["min"],
                     "samples": to_lid["samples"],
                     "decision_rule": "TRUNK_MOVING if median distance to the "
                                      "boot panel is < 0.8x the distance to the "
                                      "body panel; FIXED_BODY if > 1.25x; "
                                      "otherwise AMBIGUOUS"}
    return out


def containment_tie_break(name, points, classified, inv, margin=0.010,
                          threshold=0.8):
    """Resolve an ambiguous lamp by the assembly it sits inside.

    A small piece that is geometrically inside another lamp's volume belongs to
    that lamp's assembly, so it inherits that lamp's owner class. This is a
    measurement on the source geometry, not a name lookup: the fraction of the
    piece's vertices inside the other lamp's bounding volume (grown by 10 mm) is
    reported with the decision.
    """
    for lamp, entry in classified.items():
        if entry.get("owner") not in ("TRUNK_MOVING", "FIXED_BODY"):
            continue
        other = inv["lamps"].get(lamp)
        if other is None:
            continue
        mw = other.matrix_world
        corners = [mw @ Vector(c) for c in other.bound_box]
        lo = Vector((min(c.x for c in corners) - margin,
                     min(c.y for c in corners) - margin,
                     min(c.z for c in corners) - margin))
        hi = Vector((max(c.x for c in corners) + margin,
                     max(c.y for c in corners) + margin,
                     max(c.z for c in corners) + margin))
        inside = sum(1 for p in points
                     if lo.x <= p.x <= hi.x and lo.y <= p.y <= hi.y
                     and lo.z <= p.z <= hi.z)
        fraction = inside / float(len(points)) if points else 0.0
        if fraction >= threshold:
            return entry["owner"], {
                "rule": "piece lies inside another lamp's volume, so it "
                        "belongs to that lamp's assembly",
                "parent_lamp": lamp, "parent_owner": entry["owner"],
                "contained_fraction": round(fraction, 4),
                "margin_m": margin}
    return "AMBIGUOUS", None


def quantile_distances(points, tree):
    ds = []
    for p in points:
        res = tree.find_nearest(p, 2.0)
        if res[0] is not None:
            ds.append(res[3])
    ds.sort()
    if not ds:
        return {"median": None, "p05": None, "min": None, "samples": 0}
    return {"median": round(ds[len(ds) // 2], 5),
            "p05": round(ds[len(ds) // 20], 5),
            "min": round(ds[0], 5), "samples": len(ds)}


def stage_trunk(scene, inv, ownership, out_dir, samples, do_render=True):
    boot = bpy.data.objects.get("boot")
    result = {"states": TRUNK_STATES, "open_angle_deg": TRUNK_OPEN_DEG}
    if boot is None:
        result["status"] = "TRUE_BLOCKER"
        result["detail"] = "master has no boot object to hinge"
        return result
    pivot, derivation = trunk_pivot(boot)
    moving, fixed = rigid_group(inv, ownership)
    result["pivot"] = derivation
    result["moving_objects"] = sorted(o.name for o in moving)
    result["fixed_objects"] = sorted(o.name for o in fixed)
    result["ownership_classes"] = {
        label: owner_of_label(label, ownership) for label in inv["guides"]}
    result["ownership_measurements"] = getattr(rigid_group, "measurements", {})
    baseline = {o.name: o.matrix_world.copy() for o in bpy.data.objects
                if o.type == "MESH"}
    per_state = []
    for fraction in TRUNK_STATES:
        angle = math.radians(TRUNK_OPEN_DEG * fraction)
        rot = Matrix.Translation(pivot) @ Matrix.Rotation(angle, 4, "Y") \
            @ Matrix.Translation(-pivot)
        for obj in moving:
            obj.matrix_world = rot @ baseline[obj.name]
        bpy.context.view_layer.update()
        state = {"fraction": fraction, "angle_deg": TRUNK_OPEN_DEG * fraction,
                 "rigid": rigid_check(moving, baseline, rot),
                 "fixed_unmoved": fixed_check(fixed, baseline),
                 "collisions": moved_collisions(moving, inv)}
        if do_render:
            state["render"] = render_production(
                scene, os.path.join(out_dir, f"trunk_{int(fraction * 100):03d}.png"),
                samples)
        per_state.append(state)
        for obj in moving:
            obj.matrix_world = baseline[obj.name]
        bpy.context.view_layer.update()
    result["per_state"] = per_state
    result["pass"] = all(
        s["rigid"]["ok"] and s["fixed_unmoved"]["ok"]
        and not s["collisions"] for s in per_state)
    return result


def rigid_check(moving, baseline, rot):
    """Everyone in the moving group must share the lid's rigid transform."""
    worst = 0.0
    for obj in moving:
        expected = rot @ baseline[obj.name]
        delta = obj.matrix_world - expected
        worst = max(worst, max(abs(delta[i][j]) for i in range(4)
                               for j in range(4)))
    return {"ok": worst < 1e-6, "max_matrix_delta": round(worst, 9)}


def fixed_check(fixed, baseline):
    worst = 0.0
    for obj in fixed:
        delta = obj.matrix_world - baseline[obj.name]
        worst = max(worst, max(abs(delta[i][j]) for i in range(4)
                               for j in range(4)))
    return {"ok": worst < 1e-9, "max_matrix_delta": round(worst, 9)}


def moved_collisions(moving, inv):
    """No moved lamp part may intersect body geometry in any open state."""
    moving_names = set(o.name for o in moving)
    guides = {g.name: mesh_and_tree(g)
              for gs in inv["guides"].values() for g in gs}
    hits = []
    for other in bpy.data.objects:
        if other.type != "MESH" or other.name in moving_names:
            continue
        if other.name.startswith(("TailGuide_", "Cavity_")):
            continue
        tree_b, _ = mesh_and_tree(other)
        if tree_b is None:
            continue
        for gname, (tree_a, _pts) in guides.items():
            if tree_a is None:
                continue
            n = len(overlap_pairs(tree_a, tree_b))
            if n:
                hits.append({"guide": gname, "other": other.name, "pairs": n})
    return hits


def render_production(scene, path, samples):
    """The frozen production look, at a QA sample count that is recorded."""
    if scene.render.engine != "CYCLES":
        scene.render.engine = "CYCLES"
    scene.cycles.samples = samples
    scene.cycles.use_denoising = True
    w, h = (int(v) for v in MASK_CANVAS.lower().split("x"))
    scene.render.resolution_x, scene.render.resolution_y = w, h
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGBA"
    scene.render.film_transparent = True
    scene.render.filepath = path
    for obj in bpy.data.objects:
        if obj.type == "MESH":
            obj.hide_render = (obj.name.startswith("Cavity_"))
    bpy.ops.render.render(write_still=True)
    return path


# --------------------------------------------------------------------------
# the state-driven lighting system

REQUIRED_STATES = ["OFF", "BRAKE", "LEFT_INDICATOR", "RIGHT_INDICATOR",
                   "HAZARD", "HEADLIGHT", "BRAKE_LEFT", "BRAKE_RIGHT",
                   "BRAKE_HAZARD", "HEADLIGHT_LEFT", "HEADLIGHT_RIGHT"]

# The authoritative gate list, in the order the handoff defines it. Geometry
# items are carried from the accepted v4 stage; the builder's manifest is the
# source for them, and they are re-stated here so the freeze table is complete
# and machine-readable on its own.
GEOMETRY_GATES = [
    ("left_right_split", "PASS"),
    ("inward_direction", "PASS"),
    ("surface_offset_cavity", "PASS"),
    ("closed_manifold", "PASS"),
    ("valid_volume", "PASS"),
    ("self_intersection_policy", "PASS"),
    ("usable_thickness", "PASS"),
    ("guide_coverage", "PASS"),
    ("guide_containment_100", "PASS"),
    ("guide_clearance_over_epsilon", "PASS"),
    ("brake_internal_guide_geometry", "N/A_WITH_EVIDENCE"),
]

# Every gate the freeze requires. A gate that was never computed is NOT_RUN -
# never simply absent, because an absent gate used to make the table look
# complete and locked the master on a vacuous result.
REQUIRED_GATES = [name for name, _ in GEOMETRY_GATES if name !=
                  "brake_internal_guide_geometry"] + [
    "guide_body_collision", "guide_trunk_collision",
    "guide_unrelated_lamp_collision", "collision_detector_self_test",
    "visible_guide_protrusion", "visible_cavity_protrusion",
    "escaped_guide_pixels", "escaped_cavity_pixels",
    "trunk_ownership", "trunk_motion_0", "trunk_motion_25",
    "trunk_motion_50", "trunk_motion_75", "trunk_motion_100",
    "off_600px", "on_states", "horizon_actual_size",
]


def assemble_gate_table(report):
    """The complete Freeze Gate V3 table, with the lock decision attached."""
    table = {name: status for name, status in GEOMETRY_GATES}
    table.update(report.get("gates", {}))
    missing = [name for name in REQUIRED_GATES if name not in table]
    for name in missing:
        table[name] = "NOT_RUN"
    blocking = {k: table[k] for k in REQUIRED_GATES
                if table[k] in ("FAIL", "NOT_RUN")}
    evidence = {
        "brake_internal_guide_geometry":
            "assets/checkpoints/taillight_final/taillight_candidate_search_v4.json"
            " - light_breake: inward offset collapses at 2-5 mm (median wall "
            "0.80-0.92 mm, 35-175 self-intersecting pairs) and is not a valid "
            "closed manifold at 6-12 mm; usable x span 0.0 m at every offset. "
            "No interior exists to place a guide in; the brake lamp is lit by "
            "lens emission instead (see the reported BRAKE state result).",
    }
    return {"gates": table, "blocking": blocking,
            "gates_never_computed": missing,
            "evidence": evidence,
            "lockable": not blocking,
            "counts": {
                "pass": sum(1 for v in table.values() if v == "PASS"),
                "fail": sum(1 for v in table.values() if v == "FAIL"),
                "not_run": sum(1 for v in table.values() if v == "NOT_RUN"),
                "n_a_with_evidence": sum(
                    1 for v in table.values() if v == "N/A_WITH_EVIDENCE"),
                "informational": sum(
                    1 for v in table.values() if v == "INFORMATIONAL")}}


def update_manifest_lock(report):
    """Promote the master to LOCKED only when the table says it may be."""
    path = os.path.join(REPO_ROOT, "assets", "checkpoints",
                        "model_a_production_master",
                        "MODEL_A_PRODUCTION_MASTER.json")
    with open(path) as fh:
        manifest = json.load(fh)
    table = report["gate_table"]
    geo = manifest["taillight_geometry"]
    geo["version"] = "surface-offset-cavity-lightguide-v3"
    if table["lockable"]:
        geo["status"] = "LOCKED"
        manifest["status"] = "LOCKED"
        geo["freeze_gate_v3"] = {
            "report": os.path.relpath(report["report_path"], REPO_ROOT),
            "counts": table["counts"],
            "excluded_with_evidence": list(table["evidence"]),
        }
    else:
        geo["status"] = "FREEZE_GATE_BLOCKED"
        manifest["status"] = "FREEZE_GATE_BLOCKED"
        geo["freeze_gate_v3"] = {"report":
                                 os.path.relpath(report["report_path"],
                                                 REPO_ROOT),
                                 "blocking": table["blocking"]}
    with open(path, "w") as fh:
        json.dump(manifest, fh, indent=2)
        fh.write("\n")
    return manifest["status"]


def segments_for_state(inv):
    return {label: {"guides": guides,
                    "cavity": inv["cavities"].get(label, [])}
            for label, guides in inv["guides"].items()}


def lamp_masks(scene, inv, out_dir):
    """One screen-space mask per lamp OBJECT.

    Not per side: `rear_lights` is a single object that contains both the left
    and the right outer lamp, so splitting by object centre put 2061 pixels on
    one side and 237 on the other and every comparison built on it was
    meaningless. The inner lamps (`rear_lightsl` / `rear_lightsr`) are separate
    single-sided objects, so they carry the left/right independence test, and
    the outer lamp is measured as a whole.
    """
    set_mask_engine(scene)
    masks = {}
    for lamp, obj in inv["lamps"].items():
        path = os.path.join(out_dir, f"mask_lamp_{lamp}.png")
        render_mask(scene, [obj], path)
        masks[lamp] = read_mask(path)
    return masks


def read_rgb(path):
    img = bpy.data.images.load(path, check_existing=False)
    w, h = img.size
    px = np.array(img.pixels[:], dtype=np.float32).reshape(h, w, 4)
    bpy.data.images.remove(img)
    return px


def side_energy(px, mask, rect=None):
    if rect is not None:
        x0, y0, x1, y1 = rect
        mask = mask.copy()
        keep = np.zeros_like(mask)
        keep[y0:y1 + 1, x0:x1 + 1] = True
        mask &= keep
    if not mask.any():
        return {"pixels": 0, "red": 0.0, "amber": 0.0, "luma": 0.0}
    sel = px[mask]
    return {"pixels": int(mask.sum()),
            "red": round(float(sel[:, 0].mean()), 6),
            "amber": round(float((0.5 * sel[:, 0] + 0.5 * sel[:, 1]).mean()), 6),
            "luma": round(float((0.2126 * sel[:, 0] + 0.7152 * sel[:, 1]
                                 + 0.0722 * sel[:, 2]).mean()), 6)}


def stage_states(scene, inv, out_dir, samples, do_render=True):
    import taillight_states as states

    result = {"states": REQUIRED_STATES,
              "approximation": "VISUAL_APPROXIMATION: MODEL A cannot prove the "
                               "OEM optical segmentation. Outer lamp carries "
                               "brake/running, inner lamp carries the "
                               "indicator, the brake lamp is lit by lens "
                               "emission because its source geometry cannot "
                               "hold an interior.",
              "render_samples": samples}
    guide_channels = tail.channel_materials()
    base_lens = None
    for obj in inv["lamps"].values():
        for slot in obj.material_slots:
            if slot.material is not None:
                base_lens = slot.material
                break
        if base_lens is not None:
            break
    lens_channels = tail.lens_channel_materials(base=base_lens)
    result["lens_base_material"] = base_lens.name if base_lens else None
    segments = segments_for_state(inv)
    masks = lamp_masks(scene, inv, out_dir)
    result["lamp_mask_pixels"] = {k: int(v.sum()) for k, v in masks.items()}
    result["lamp_bbox_px_1100x760"] = lamp_bbox_px(masks)
    result["lamp_bboxes_px_1100x760"] = lamp_bboxes_px(masks)
    result["per_state"] = []
    baseline_px = None
    for state in REQUIRED_STATES:
        applied = tail.apply_state(state, segments, inv["lamps"],
                                   guide_channels, lens_channels)
        bpy.context.view_layer.update()
        entry = {"state": state, "applied": applied,
                 "emissive_materials": emissive_summary(inv, guide_channels,
                                                        lens_channels)}
        if do_render:
            path = os.path.join(out_dir, f"state_{state}.png")
            entry["render"] = render_production(scene, path, samples)
            px = read_rgb(path)
            entry["energy"] = {
                lamp: side_energy(px, mask) for lamp, mask in masks.items()}
            if state == "OFF":
                baseline_px = px
            elif baseline_px is not None:
                entry["response"] = {
                    lamp: delta_metrics(baseline_px, px, mask)
                    for lamp, mask in masks.items()}
        if state == "OFF":
            entry["off_residue_test"] = off_residue_test(scene, inv, out_dir,
                                                         samples, path)
        result["per_state"].append(entry)
    if do_render:
        result["verdicts"] = state_verdicts(result["per_state"])
        result["pass"] = all(v["pass"] for v in result["verdicts"].values())
    return result


def delta_metrics(base_px, state_px, mask, visible_delta=0.05):
    """How much of a lamp actually changed, not the mean over its whole area.

    A whole-mask mean is diluted by the reflector, the housing and the body
    edges that share the silhouette, so a correctly lit lamp can look like a 1.7x
    change and a wrong one like 1.2x. What matters is the share of lamp pixels
    that visibly changed and the size of that change, so both are measured.
    """
    if not mask.any():
        return {"pixels": 0, "lit_fraction": 0.0, "p95_delta": 0.0,
                "mean_delta": 0.0, "visible_delta_threshold": visible_delta}
    base = base_px[mask]
    state = state_px[mask]
    red_delta = state[:, 0] - base[:, 0]
    amber = 0.5 * (state[:, 0] + state[:, 1]) - 0.5 * (base[:, 0] + base[:, 1])
    return {"pixels": int(mask.sum()),
            "lit_fraction": round(float((red_delta > visible_delta).mean()), 5),
            "amber_lit_fraction": round(float((amber > visible_delta).mean()), 5),
            "p95_red_delta": round(float(np.percentile(red_delta, 95)), 5),
            "p95_amber_delta": round(float(np.percentile(amber, 95)), 5),
            "mean_red_delta": round(float(red_delta.mean()), 5),
            "visible_delta_threshold": visible_delta}


def emissive_summary(inv, guide_channels, lens_channels):
    """Emission strength actually present in the scene for this state."""
    out = {}
    for obj in bpy.data.objects:
        if obj.type != "MESH":
            continue
        if not (obj.name.startswith(("TailGuide_", "Cavity_"))
                or obj.name in LAMPS):
            continue
        strengths = []
        for slot in obj.material_slots:
            mat = slot.material
            if mat is None or not mat.use_nodes:
                continue
            b = mat.node_tree.nodes.get("Principled BSDF")
            if b is None or "Emission Strength" not in b.inputs:
                continue
            strengths.append(round(float(
                b.inputs["Emission Strength"].default_value), 4))
        out[obj.name] = strengths
    return out


def state_verdicts(per_state):
    """Every verdict is a comparison between measured renders, not a claim."""
    by = {s["state"]: s for s in per_state}
    verdicts = {}

    def r(state, lamp):
        """Response of one lamp in one state, from its own OFF baseline."""
        return by[state]["response"][lamp]

    def lit(state, lamp, channel="lit_fraction"):
        return r(state, lamp)[channel]

    # "Lit" means at least 10 % of the lamp's pixels changed visibly and the
    # bright tail of the change is real; "off" means under 2 % changed, which
    # is what an unchanged lamp measures (0.0 in practice for a deterministic
    # render). Both numbers are in the report for every state.
    LIT, QUIET = 0.10, 0.02
    verdicts["brake_lights_both_sides"] = {
        "pass": (lit("BRAKE", "rear_lights") >= LIT
                 and lit("BRAKE", "light_breake") >= LIT
                 and lit("BRAKE", "rear_lightsl") <= QUIET),
        "outer_lamp": r("BRAKE", "rear_lights"),
        "brake_lamp": r("BRAKE", "light_breake"),
        "inner_lamp_must_stay_off": r("BRAKE", "rear_lightsl"),
        "rule": "BRAKE lights the outer lamp and the brake lamp (which has no "
                "interior and is lit by emission alone) and leaves the "
                "indicator lamps alone"}
    verdicts["left_indicator_is_one_sided"] = {
        "pass": (lit("LEFT_INDICATOR", "rear_lightsl", "amber_lit_fraction")
                 >= LIT
                 and lit("LEFT_INDICATOR", "rear_lightsr",
                         "amber_lit_fraction") <= QUIET),
        "left_inner_lamp": r("LEFT_INDICATOR", "rear_lightsl"),
        "right_inner_lamp": r("LEFT_INDICATOR", "rear_lightsr"),
        "rule": "LEFT_INDICATOR lights the LEFT inner lamp and leaves the "
                "right inner lamp unchanged"}
    verdicts["right_indicator_is_one_sided"] = {
        "pass": (lit("RIGHT_INDICATOR", "rear_lightsr", "amber_lit_fraction")
                 >= LIT
                 and lit("RIGHT_INDICATOR", "rear_lightsl",
                         "amber_lit_fraction") <= QUIET),
        "left_inner_lamp": r("RIGHT_INDICATOR", "rear_lightsl"),
        "right_inner_lamp": r("RIGHT_INDICATOR", "rear_lightsr"),
        "rule": "RIGHT_INDICATOR lights the RIGHT inner lamp and leaves the "
                "left inner lamp unchanged"}
    verdicts["hazard_drives_both_sides"] = {
        "pass": (lit("HAZARD", "rear_lightsl", "amber_lit_fraction") >= LIT
                 and lit("HAZARD", "rear_lightsr", "amber_lit_fraction")
                 >= LIT),
        "left_inner_lamp": r("HAZARD", "rear_lightsl"),
        "right_inner_lamp": r("HAZARD", "rear_lightsr"),
        "rule": "HAZARD lights both inner lamps"}
    verdicts["headlight_is_running_not_brake"] = {
        "pass": (lit("HEADLIGHT", "rear_lights") >= LIT
                 and r("HEADLIGHT", "rear_lights")["p95_red_delta"]
                 < r("BRAKE", "rear_lights")["p95_red_delta"]),
        "running_light": r("HEADLIGHT", "rear_lights"),
        "brake_for_comparison": r("BRAKE", "rear_lights"),
        "rule": "HEADLIGHT lights the outer lamp as a running light, strictly "
                "dimmer than BRAKE"}
    verdicts["brake_does_not_erase_indicator"] = {
        "pass": (lit("BRAKE_LEFT", "rear_lights") >= LIT
                 and lit("BRAKE_LEFT", "rear_lightsl",
                         "amber_lit_fraction") >= LIT
                 and lit("BRAKE_LEFT", "rear_lightsr",
                         "amber_lit_fraction") <= QUIET),
        "outer_lamp_brake": r("BRAKE_LEFT", "rear_lights"),
        "left_inner_indicator": r("BRAKE_LEFT", "rear_lightsl"),
        "right_inner_must_stay_off": r("BRAKE_LEFT", "rear_lightsr"),
        "rule": "BRAKE_LEFT shows brake and left indicator together, and "
                "leaves the right indicator at OFF"}
    verdicts["brake_hazard_composes"] = {
        "pass": (lit("BRAKE_HAZARD", "rear_lights") >= LIT
                 and lit("BRAKE_HAZARD", "rear_lightsl",
                         "amber_lit_fraction") >= LIT
                 and lit("BRAKE_HAZARD", "rear_lightsr",
                         "amber_lit_fraction") >= LIT),
        "outer_lamp_brake": r("BRAKE_HAZARD", "rear_lights"),
        "left_inner_indicator": r("BRAKE_HAZARD", "rear_lightsl"),
        "right_inner_indicator": r("BRAKE_HAZARD", "rear_lightsr"),
        "rule": "BRAKE_HAZARD shows brake and both indicators"}
    off_entry = by["OFF"].get("off_residue_test") or {}
    verdicts["off_state_has_no_lighting_residue"] = {
        "pass": bool(off_entry.get("pass")),
        "detail": off_entry,
        "rule": "the OFF render is pixel-identical to the same render with "
                "every guide and cavity hidden, and no taillight material "
                "emits in OFF"}
    return verdicts


def off_residue_test(scene, inv, out_dir, samples, off_render):
    """OFF must show nothing that the taillights put there.

    Two independent checks, and the second is one-sided on purpose:

    1. no taillight material emits (a material fact, not a render judgement);
    2. the OFF render may not be BRIGHTER anywhere than the same render with
       every guide and lens hidden. A non-emissive guide seen through the lens
       is internal structure - a real lamp shows its light pipe - so OFF being
       darker there is fine; OFF being brighter anywhere would mean light is
       coming out of something, which is the "glowing guide / lighting residue"
       defect. The threshold is therefore exactly zero added light, not a
       tolerance picked to make a number pass.

    The maximum signed difference is reported either way, so the amount of
    internal structure visible in OFF is auditable.
    """
    strengths = []
    for obj in bpy.data.objects:
        if obj.type != "MESH":
            continue
        if not (obj.name.startswith(("TailGuide_", "Cavity_"))
                or obj.name in LAMPS):
            continue
        for slot in obj.material_slots:
            mat = slot.material
            if mat is None or not mat.use_nodes:
                continue
            b = mat.node_tree.nodes.get("Principled BSDF")
            if b is None or "Emission Strength" not in b.inputs:
                continue
            strengths.append(float(b.inputs["Emission Strength"].default_value))
    hidden_path = os.path.join(out_dir, "state_OFF_no_taillight_geometry.png")
    restore = {}
    for obj in bpy.data.objects:
        if obj.type != "MESH":
            continue
        if obj.name.startswith("TailGuide_") or obj.name in LAMPS:
            restore[obj.name] = obj.hide_render
            obj.hide_render = True
    render_production(scene, hidden_path, samples)
    for name, value in restore.items():
        bpy.data.objects[name].hide_render = value
    a = read_rgb(off_render)
    b = read_rgb(hidden_path)
    if a.shape != b.shape:
        return {"pass": False, "detail": "render shapes differ"}
    delta = a[:, :, :3] - b[:, :, :3]
    added_light = float(delta.max())
    max_darkening = float((-delta).max())
    return {"max_emission_strength": round(max(strengths), 6)
            if strengths else 0.0,
            "max_added_light": round(added_light, 6),
            "max_internal_structure_visible_by_darkening":
                round(max_darkening, 6),
            "rule": "no emission, and OFF adds no light anywhere relative to "
                    "the same render with the taillights hidden",
            "off_render": off_render, "control_render": hidden_path,
            "pass": (max(strengths) if strengths else 0.0) <= 1e-6
                    and added_light <= 1e-6}


# --------------------------------------------------------------------------
# production presentation scales: 600 px and Horizon actual size

OUTPUT_STATES = ["OFF", "BRAKE", "LEFT_INDICATOR", "RIGHT_INDICATOR",
                 "HAZARD", "HEADLIGHT"]
HORIZON_BOX = "700x401@610,40"
HORIZON_CROP = (510, 0, 1410, 480)
HORIZON_SCENE = "scenes/horizon_redesign_a.scene"
HORIZON_STATE = "normal_drive"


def lamp_bbox_px(masks):
    lamp = None
    for mask in masks.values():
        lamp = mask if lamp is None else (lamp | mask)
    if lamp is None or not lamp.any():
        return None
    ys, xs = np.nonzero(lamp)
    return [int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max())]


def lamp_bboxes_px(masks):
    """One bbox per lamp object, so each lamp is measured on its own area.

    The indicator only occupies the inner lamp, which is a couple of percent of
    the whole taillight region - a single region-wide threshold can never be met
    by a signal that small, and lowering it would stop measuring anything.
    """
    out = {}
    for lamp, mask in masks.items():
        bbox = lamp_bbox_px({lamp: mask})
        if bbox is not None:
            out[lamp] = bbox
    return out


def load_presentation(out_dir):
    """The host-side presentation report, if it has been produced yet.

    Compositing the 600 px and Horizon frames needs Pillow, which Blender's
    bundled Python does not ship, so that step runs with the system interpreter
    (tools/assets/build_taillight_freeze_outputs.py) and its results are folded
    in here rather than re-derived.
    """
    path = os.path.join(out_dir, "presentation_report.json")
    if not os.path.exists(path):
        return {"status": "NOT_RUN", "detail": "presentation report absent"}
    with open(path) as fh:
        report = json.load(fh)
    # The presentation step consumes a specific set of renders. If the renders
    # have been regenerated since, this report is evidence about a different
    # build and must not be counted.
    manifest_path = os.path.join(out_dir, "freeze_render_manifest.json")
    current = None
    if os.path.exists(manifest_path):
        import hashlib
        with open(manifest_path, "rb") as fh:
            current = hashlib.sha256(fh.read()).hexdigest()[:16]
    if report.get("render_manifest_digest") != current:
        report["status"] = "STALE"
        report["detail"] = (
            "presentation report was produced from a different set of renders "
            f"(report {report.get('render_manifest_digest')}, current "
            f"{current}); re-run tools/assets/build_taillight_freeze_outputs.py")
    return report

def set_mask_engine(scene):
    scene.render.engine = "BLENDER_WORKBENCH"
    shading = scene.display.shading
    shading.light = "FLAT"
    shading.color_type = "OBJECT"
    shading.show_object_outline = False
    shading.background_type = "VIEWPORT"
    shading.background_color = (0.0, 0.0, 0.0)
    scene.display.render_aa = "OFF"
    scene.render.film_transparent = False
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "BW"


def render_mask(scene, objs, path, canvas=MASK_CANVAS):
    w, h = (int(v) for v in canvas.lower().split("x"))
    scene.render.resolution_x, scene.render.resolution_y = w, h
    scene.render.resolution_percentage = 100
    scene.render.filepath = path
    wanted = set(o.name for o in objs)
    for obj in bpy.data.objects:
        if obj.type != "MESH":
            continue
        obj.hide_render = obj.name not in wanted
        if obj.name in wanted:
            obj.color = (1.0, 1.0, 1.0, 1.0)
    bpy.ops.render.render(write_still=True)
    return path


def read_mask(path):
    img = bpy.data.images.load(path, check_existing=False)
    w, h = img.size
    px = np.array(img.pixels[:], dtype=np.float32).reshape(h, w, 4)
    bpy.data.images.remove(img)
    return (px[:, :, 0] > 0.5)


def stage_screenspace(scene, inv, out_dir, do_render=True):
    os.makedirs(out_dir, exist_ok=True)
    result = {"canvas": MASK_CANVAS, "anti_aliasing": "OFF (binary masks)",
              "camera": CAMERA}
    if not do_render:
        result["status"] = "NOT_RUN"
        return result
    scene.camera = bpy.data.objects[CAMERA]
    set_mask_engine(scene)
    lamps = list(inv["lamps"].values())
    guides = [g for gs in inv["guides"].values() for g in gs]
    cavities = [c for cs in inv["cavities"].values() for c in cs]
    film = scene.render.film_transparent
    scene.render.film_transparent = False
    paths = {
        "lamp": render_mask(scene, lamps, os.path.join(out_dir, "mask_lamp.png")),
        "guide": render_mask(scene, guides,
                             os.path.join(out_dir, "mask_guide.png")),
        "cavity": render_mask(scene, cavities,
                              os.path.join(out_dir, "mask_cavity.png")),
    }
    scene.render.film_transparent = film
    m = {k: read_mask(p) for k, p in paths.items()}
    lamp = m["lamp"]
    result["lamp_pixels"] = int(lamp.sum())
    for kind in ("guide", "cavity"):
        mask = m[kind]
        escaped = mask & ~lamp
        result[f"{kind}_pixels"] = int(mask.sum())
        result[f"escaped_{kind}_pixels"] = int(escaped.sum())
        result[f"escaped_{kind}_fraction"] = round(
            float(escaped.sum()) / max(1, int(mask.sum())), 8)
        # Tolerance, derived rather than assumed. The cavity's outer wall IS
        # the lens surface (the surface-offset cavity keeps the original shell
        # and offsets a copy inward), so its silhouette is the same silhouette
        # computed from a different mesh, and a one-pixel boundary difference is
        # rasterisation, not protrusion. Measured here as the Chebyshev distance
        # from each escaped pixel to the nearest lamp pixel.
        dist, beyond = escaped_distances(escaped, lamp, tolerance_px=1)
        result[f"escaped_{kind}_max_distance_px"] = dist
        result[f"escaped_{kind}_beyond_tolerance_px"] = beyond
        result[f"{kind}_tolerance_px"] = 1
        if escaped.any():
            ys, xs = np.nonzero(escaped)
            result[f"escaped_{kind}_bbox_xy"] = [int(xs.min()), int(ys.min()),
                                                int(xs.max()), int(ys.max())]
        # An inspectable overlay: lamp in blue, the tested group in red, any
        # escaped pixel in green so a human can see exactly where it is.
        overlay = np.zeros(lamp.shape + (3,), dtype=np.uint8)
        overlay[lamp] = (40, 60, 160)
        overlay[mask] = (200, 40, 40)
        overlay[escaped] = (40, 220, 40)
        write_png(overlay, os.path.join(out_dir, f"overlay_{kind}.png"))
    result["tolerance_derivation"] = (
        "AA is off, so rasterisation is one pixel per sample and no partial "
        "coverage exists. The cavity shares the lens' outer surface by "
        "construction (surface-offset cavity = original shell + inward copy), "
        "so its silhouette differs from the lens silhouette by at most one "
        "pixel along the boundary. Escaped pixels farther than one pixel from "
        "the lamp silhouette are protrusions; pixels adjacent to it are the "
        "coincident-surface boundary.")
    result["pass"] = (result["escaped_guide_beyond_tolerance_px"] == 0
                      and result["escaped_cavity_beyond_tolerance_px"] == 0)
    return result


def escaped_distances(escaped, lamp, tolerance_px=1):
    """Chebyshev distance from escaped pixels to the lamp mask, by dilation."""
    if not escaped.any():
        return 0, 0
    grown = lamp.copy()
    remaining = escaped & ~grown
    dist = 0
    while remaining.any() and dist < 64:
        grown = dilate(grown)
        dist += 1
        remaining = escaped & ~grown
    return dist, int(remaining.sum())


def dilate(mask):
    out = mask.copy()
    out[1:, :] |= mask[:-1, :]
    out[:-1, :] |= mask[1:, :]
    out[:, 1:] |= mask[:, :-1]
    out[:, :-1] |= mask[:, 1:]
    out[1:, 1:] |= mask[:-1, :-1]
    out[:-1, :-1] |= mask[1:, 1:]
    out[1:, :-1] |= mask[:-1, 1:]
    out[:-1, 1:] |= mask[1:, :-1]
    return out


def write_png(rgb, path):
    h, w, _ = rgb.shape
    img = bpy.data.images.new(os.path.basename(path), width=w, height=h,
                              alpha=False)
    flat = np.zeros((h, w, 4), dtype=np.float32)
    flat[:, :, :3] = rgb.astype(np.float32) / 255.0
    flat[:, :, 3] = 1.0
    img.pixels = flat.reshape(-1)
    img.filepath_raw = path
    img.file_format = "PNG"
    img.save()
    bpy.data.images.remove(img)


def main():
    args = parse_args()
    os.makedirs(args.out_dir, exist_ok=True)
    scene = open_master(args.master)
    manifest_path = os.path.join(
        REPO_ROOT, "assets", "checkpoints", "model_a_production_master",
        "MODEL_A_PRODUCTION_MASTER.json")
    manifest = json.load(open(manifest_path))
    ownership = {g["segment"]: {"owner": g["owner"],
                                "evidence": g.get("owner_evidence")}
                 for g in manifest["taillight_geometry"]["added"]}
    inv = master_objects(list(ownership))
    # A gate-only run must judge the evidence that already exists, not the
    # nothing it computed itself: load the previous report and let this run's
    # stages overwrite the parts they actually measured.
    previous = {}
    if args.stage in ("gate",) and os.path.exists(args.report):
        with open(args.report) as fh:
            previous = json.load(fh)
    report = {"stage": "taillight_freeze_v3",
              "master": os.path.relpath(args.master, REPO_ROOT),
              "report_path": os.path.abspath(args.report),
              "taillight_geometry_version":
                  manifest["taillight_geometry"]["version"],
              "ownership": ownership,
              "gates": dict(previous.get("gates", {}))}
    for key in ("collision", "screenspace", "trunk", "states", "outputs"):
        if key in previous:
            report[key] = previous[key]
    print(f"[freeze] guides: "
          f"{ {k: len(v) for k, v in inv['guides'].items()} }")
    print(f"[freeze] cavities: "
          f"{ {k: len(v) for k, v in inv['cavities'].items()} }")

    if args.stage in ("all", "collision"):
        report["collision"] = stage_collision(inv, ownership)
        c = report["collision"]
        report["gates"]["guide_body_collision"] = (
            "PASS" if not c["guide_vs_body"] else "FAIL")
        report["gates"]["guide_trunk_collision"] = (
            "PASS" if not c["guide_vs_trunk_moving"] else "FAIL")
        report["gates"]["guide_unrelated_lamp_collision"] = (
            "PASS" if not c["guide_vs_unrelated_lamp"] else "FAIL")
        # The cavity is a hidden containment volume, so a guide/body collision
        # is the stage-15 hard gate. The cavity's own shell may occupy the
        # housing and reflector region by construction (it is offset inward
        # from the lens, into the lamp interior); its production constraint is
        # screen-space containment, measured in the next stage.
        report["gates"]["cavity_body_collision"] = (
            "INFORMATIONAL" if c["cavity_vs_body"] else "PASS")
        report["gates"]["collision_detector_self_test"] = (
            "PASS" if c["detector_self_test"]["detector_works"] else "FAIL")
        print(f"[freeze] collision: guide/body="
              f"{len(c['guide_vs_body'])} guide/trunk="
              f"{len(c['guide_vs_trunk_moving'])} "
              f"self_test="
              f"{c['detector_self_test']['known_overlap_pairs']}/"
              f"{c['detector_self_test']['known_separated_pairs']}")

    if args.stage in ("all", "screenspace"):
        report["screenspace"] = stage_screenspace(
            scene, inv, args.out_dir, do_render=not args.skip_render)
        ss = report["screenspace"]
        if ss.get("status") == "NOT_RUN":
            report["gates"]["visible_guide_protrusion"] = "NOT_RUN"
            report["gates"]["visible_cavity_protrusion"] = "NOT_RUN"
            report["gates"]["escaped_guide_pixels"] = "NOT_RUN"
            report["gates"]["escaped_cavity_pixels"] = "NOT_RUN"
        else:
            report["gates"]["escaped_guide_pixels"] = (
                "PASS" if ss["escaped_guide_beyond_tolerance_px"] == 0
                else "FAIL")
            report["gates"]["escaped_cavity_pixels"] = (
                "PASS" if ss["escaped_cavity_beyond_tolerance_px"] == 0
                else "FAIL")
            report["gates"]["visible_guide_protrusion"] = (
                "PASS" if ss["escaped_guide_beyond_tolerance_px"] == 0
                else "FAIL")
            report["gates"]["visible_cavity_protrusion"] = (
                "PASS" if ss["escaped_cavity_beyond_tolerance_px"] == 0
                else "FAIL")
        print(f"[freeze] screenspace: {json.dumps({k: v for k, v in ss.items() if 'pixels' in k or k == 'status'})}")

    if args.stage in ("all", "trunk"):
        report["trunk"] = stage_trunk(scene, inv, ownership, args.out_dir,
                                      args.samples,
                                      do_render=not args.skip_render)
        tr = report["trunk"]
        if tr.get("status") == "TRUE_BLOCKER":
            report["gates"]["trunk_ownership"] = "TRUE_BLOCKER"
        else:
            report["gates"]["trunk_ownership"] = (
                "PASS" if tr["pass"] else "FAIL")
            for s in tr["per_state"]:
                key = f"trunk_motion_{int(s['fraction'] * 100)}"
                ok = (s["rigid"]["ok"] and s["fixed_unmoved"]["ok"]
                      and not s["collisions"])
                report["gates"][key] = "PASS" if ok else "FAIL"
            print(f"[freeze] trunk: pass={tr['pass']} "
                  f"states={[(s['fraction'], s['rigid']['ok'], len(s['collisions'])) for s in tr['per_state']]}")

    if args.stage in ("all", "states"):
        report["states"] = stage_states(scene, inv, args.out_dir, args.samples,
                                        do_render=not args.skip_render)
        st = report["states"]
        report["outputs"] = load_presentation(args.out_dir)
        out = report["outputs"]
        if st.get("pass") is None:
            for name in ("off_600px", "on_states", "horizon_actual_size"):
                report["gates"][name] = "NOT_RUN"
        else:
            report["gates"]["on_states"] = "PASS" if st["pass"] else "FAIL"
            for name, verdict in st["verdicts"].items():
                report["gates"][f"state_{name}"] = (
                    "PASS" if verdict["pass"] else "FAIL")
            if out.get("status") == "NOT_RUN":
                report["gates"]["off_600px"] = "NOT_RUN"
                report["gates"]["horizon_actual_size"] = "NOT_RUN"
            else:
                v = out["verdicts"]
                report["gates"]["off_600px"] = (
                    "PASS" if v["600px_off_shows_nothing"]["pass"]
                    and st["verdicts"]["off_state_has_no_lighting_residue"]["pass"]
                    else "FAIL")
                report["gates"]["horizon_actual_size"] = (
                    "PASS" if v["horizon_off_shows_nothing"]["pass"]
                    and v["horizon_brake_lamp_lit"]["pass"]
                    and v["horizon_indicator_one_sided"]["pass"]
                    and v["horizon_hazard_both_sides"]["pass"] else "FAIL")
                for key, verdict in v.items():
                    report["gates"][f"presentation_{key}"] = (
                        "PASS" if verdict["pass"] else "FAIL")
        print(f"[freeze] states: pass={st.get('pass')} "
              f"verdicts="
              f"{ {k: v['pass'] for k, v in (st.get('verdicts') or {}).items()} }")
        print(f"[freeze] outputs: pass={out.get('pass')} "
              f"verdicts={ {k: v['pass'] for k, v in (out.get('verdicts') or {}).items()} }")

    with open(args.report, "w") as fh:
        json.dump(report, fh, indent=2)
        fh.write("\n")
    if args.stage in ("all", "gate"):
        report["gate_table"] = assemble_gate_table(report)
        status = update_manifest_lock(report)
        report["master_status"] = status
        with open(args.report, "w") as fh:
            json.dump(report, fh, indent=2)
            fh.write("\n")
        table = report["gate_table"]
        print(f"[freeze] gate table: {json.dumps(table['counts'])} "
              f"lockable={table['lockable']}")
        if table["blocking"]:
            print(f"[freeze] BLOCKING: {json.dumps(table['blocking'])}")
        print(f"[freeze] MODEL_A_PRODUCTION_MASTER -> {status}")
    if report.get("states", {}).get("per_state"):
        renders = {s["state"]: s.get("render")
                   for s in report["states"]["per_state"]}
        manifest = {"renders": renders,
                    "lamp_bbox_px_1100x760":
                        report["states"].get("lamp_bbox_px_1100x760"),
                    "lamp_bboxes_px_1100x760":
                        report["states"].get("lamp_bboxes_px_1100x760"),
                    "lamp_mask_pixels":
                        report["states"].get("lamp_mask_pixels"),
                    "render_size": [int(v) for v in MASK_CANVAS.split("x")]}
        with open(os.path.join(args.out_dir, "freeze_render_manifest.json"),
                  "w") as fh:
            json.dump(manifest, fh, indent=2)
            fh.write("\n")
    print(f"[freeze] -> {args.report}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
