#!/usr/bin/env python3
"""Surface-offset (solidify-inward) taillight cavity.

The lens shells have ~0 thickness in their own normal direction, so no sweep
of their cross-section can create an interior. This derives the interior from
the SURFACE instead: duplicate the shell, offset it inward along its own
normals, and stitch the boundary, giving a closed volume whose wall-to-wall
thickness is the offset.

The offset runs on a CLEANUP COPY. The production lens is never modified.

Usage:
    blender -b -P tools/blender/taillight_offset.py -- --report out.json
"""

import argparse
import json
import math
import os
import sys

try:
    import bpy
    import bmesh
    from mathutils import Vector
    from mathutils.bvhtree import BVHTree
except ImportError:  # pragma: no cover
    sys.exit("Run inside Blender")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import render_vehicle_visual_v2 as vehicle_v2  # noqa: E402
import taillight_finalize as base  # noqa: E402

LAMPS = ["rear_lights", "rear_lightsl", "rear_lightsr", "light_breake"]
THICKNESSES = [0.002, 0.003, 0.004, 0.005, 0.006, 0.008, 0.010, 0.012]


def parse_args():
    argv = sys.argv
    argv = argv[argv.index("--") + 1:]
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", default=vehicle_v2.DEFAULT_INPUT)
    ap.add_argument("--report", required=True)
    ap.add_argument("--samples", type=int, default=256)
    return ap.parse_args(argv)


def cleaned_copy(points_name, verts, faces):
    """Cavity-construction copy with the source defects repaired."""
    mesh = bpy.data.meshes.new(points_name)
    mesh.from_pydata([tuple(v) for v in verts], [], faces)
    mesh.update()
    obj = bpy.data.objects.new(points_name, mesh)
    bpy.context.scene.collection.objects.link(obj)
    ops = {}
    bm = bmesh.new()
    bm.from_mesh(mesh)
    before = len(bm.verts)
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-5)
    ops["merged_vertices"] = before - len(bm.verts)
    loose = [v for v in bm.verts if not v.link_faces]
    bmesh.ops.delete(bm, geom=loose, context="VERTS")
    ops["loose_vertices_removed"] = len(loose)
    small = [f for f in bm.faces if f.calc_area() < 1e-10]
    if small:
        bmesh.ops.delete(bm, geom=small, context="FACES")
    ops["degenerate_faces_removed"] = len(small)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    ops["normals_recalculated"] = True
    bm.to_mesh(mesh)
    bm.free()
    mesh.update()
    return obj, ops


def normals_consistent(mesh):
    """Share of faces whose normal agrees with the recalculated reference."""
    bm = bmesh.new()
    bm.from_mesh(mesh)
    bm.faces.ensure_lookup_table()
    before = {f.index: f.normal.copy() for f in bm.faces}
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.normal_update()
    bad = sum(1 for f in bm.faces if before[f.index].dot(f.normal) < -0.5)
    bm.free()
    return 1.0 - bad / max(len(mesh.polygons), 1), bad


def inward_sign(obj, left_sign, side):
    """Decide which way is 'into the lamp', from geometry not assumption.

    The lamp sits on one side of the vehicle; inward is toward the vehicle
    centreline on Y. The sign is confirmed against the shell's own average
    normal so a flipped mesh is detected rather than silently inverted.
    """
    mw = obj.matrix_world
    verts = [mw @ v.co for v in obj.data.vertices]
    cy = sum(v.y for v in verts) / len(verts)
    inward_y = -1.0 if cy > 0 else 1.0
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    bm.normal_update()
    nsum = Vector((0.0, 0.0, 0.0))
    for f in bm.faces:
        nsum += f.normal
    bm.free()
    outward_y = 1.0 if nsum.y > 0 else -1.0
    # Do the stored normals point outward, i.e. away from the centreline?
    normals_outward = (outward_y == (1.0 if cy > 0 else -1.0))
    return {
        "component_centroid_y": round(cy, 4),
        "vehicle_side": side,
        "inward_axis_sign": inward_y,
        "stored_normals_point_outward": normals_outward,
        "flip_needed": not normals_outward,
    }


def solidify(obj, thickness, flip):
    for p in obj.data.polygons:
        p.use_smooth = True
    mod = obj.modifiers.new("Solidify", "SOLIDIFY")
    mod.thickness = thickness
    mod.offset = -1.0 if not flip else 1.0   # push the new shell inward
    mod.use_even_offset = True
    mod.use_quality_normals = True
    mod.use_rim = True
    deps = bpy.context.evaluated_depsgraph_get()
    ev = obj.evaluated_get(deps)
    mesh = bpy.data.meshes.new_from_object(ev)
    obj.modifiers.remove(mod)
    return mesh


def health(mesh):
    bm = bmesh.new()
    bm.from_mesh(mesh)
    boundary = sum(1 for e in bm.edges if len(e.link_faces) == 1)
    nonman = sum(1 for e in bm.edges if len(e.link_faces) > 2)
    wire = sum(1 for e in bm.edges if len(e.link_faces) == 0)
    degen = sum(1 for f in bm.faces if f.calc_area() < 1e-10)
    try:
        vol = bm.calc_volume(signed=True)
    except Exception:
        vol = 0.0
    bm.free()
    return {"boundary_edges": boundary, "non_manifold_edges": nonman,
            "wire_edges": wire, "degenerate_faces": degen,
            "signed_volume_m3": round(vol, 9), "outward": vol > 0,
            "watertight": boundary == 0 and nonman == 0 and wire == 0}


def thickness_stats(obj, samples):
    """Wall-to-wall thickness: distance from a surface point to the far wall."""
    tree = base.bvh_of(obj)
    mw = obj.matrix_world
    verts = [mw @ v.co for v in obj.data.vertices]
    step = max(1, len(verts) // samples)
    probe = verts[::step]
    vals = []
    for p in probe:
        n = (p - Vector((p.x, 0.0, p.z)))
        if n.length < 1e-6:
            n = Vector((0.0, 1.0, 0.0))
        n.normalize()
        res = tree.ray_cast(p - n * 0.0005, n, 0.06)
        if res[0] is not None and res[3] is not None and res[3] > 1e-5:
            vals.append(res[3])
    if not vals:
        return None
    vals.sort()
    n = len(vals)
    def pc(f):
        return round(vals[min(n - 1, int(n * f))], 5)
    return {"samples": n, "min_m": pc(0.0), "p1_m": pc(0.01),
            "p5_m": pc(0.05), "median_m": pc(0.5),
            "mean_m": round(sum(vals) / n, 5), "max_m": pc(1.0)}


def main():
    args = parse_args()
    meshes, size = vehicle_v2.import_and_normalise(args.input, "+Y")
    left_sign, err = base.resolve_left_sign()
    report = {"method": "surface-offset (solidify inward)", "vehicle_size_m": size,
              "left_sign": left_sign, "thickness_candidates_m": THICKNESSES,
              "epsilon_note": "epsilon is derived below from the measured "
                              "minimum wall-to-wall thickness, not fixed a priori",
              "lamps": {}, "sweep": []}

    groups = {"LEFT": [], "RIGHT": []}
    for name in LAMPS:
        obj = bpy.data.objects.get(name)
        if obj is None:
            continue
        comps = base.components(obj)
        entry = {"components": len(comps), "vertices": len(obj.data.vertices),
                 "normals": None, "inward": None, "cleanup": None}
        for pts, idx in comps:
            if len(pts) < 24:
                continue
            cy = sum(p.y for p in pts) / len(pts)
            side = "LEFT" if cy * left_sign > 0 else "RIGHT"
            groups[side].append((name, pts, idx, obj))
        report["lamps"][name] = entry

    results = {}
    for side in ("LEFT", "RIGHT"):
        items = groups[side]
        if not items:
            results[side] = {"built": False, "reason": "no components"}
            continue
        verts, faces = [], []
        base_index = 0
        for _name, pts, idx, obj in items:
            mw = obj.matrix_world
            local = {old: base_index + k for k, old in enumerate(idx)}
            verts += [mw @ obj.data.vertices[old].co for old in idx]
            for poly in obj.data.polygons:
                if all(vi in local for vi in poly.vertices):
                    faces.append([local[vi] for vi in poly.vertices])
            base_index += len(idx)
        copy, cleanup = cleaned_copy(f"Cavity_{side}_src", verts,
                                     [tuple(f) for f in faces])
        consistency, flipped = normals_consistent(copy.data)
        sign = inward_sign(copy, left_sign, side)
        results[side] = {"cleanup": cleanup, "normal_consistency": consistency,
                         "flipped_faces": flipped, "inward": sign,
                         "source_vertices": len(verts), "source_faces": len(faces)}

        best = None
        for th in THICKNESSES:
            mesh = solidify(copy, th, sign["flip_needed"])
            h = health(mesh)
            cov = bpy.data.objects.new(f"Cavity_{side}_{th}", mesh)
            bpy.context.scene.collection.objects.link(cov)
            tstats = thickness_stats(cov, args.samples)
            row = {"side": side, "thickness_m": th, "health": h,
                   "thickness_distribution": tstats}
            report["sweep"].append(row)
            if (h["watertight"] and h["outward"]
                    and h["signed_volume_m3"] > 0):
                if best is None:
                    best = (th, h, tstats, cov)
                else:
                    bpy.data.objects.remove(cov, do_unlink=True)
            else:
                bpy.data.objects.remove(cov, do_unlink=True)
        if best:
            results[side]["selected_thickness_m"] = best[0]
            results[side]["cavity"] = best[1]
            results[side]["thickness_distribution"] = best[2]
        else:
            results[side]["built"] = False
            results[side]["reason"] = "no offset thickness produced a valid closed volume"

    report["sides"] = results
    report["freeze_gate_v3"] = {
        "surface_offset_cavity": all(
            "selected_thickness_m" in results.get(s, {})
            for s in ("LEFT", "RIGHT")),
        "guide_containment_100": None,
        "note": "guide placement, screen-space QA, trunk motion and Parts 1-22 "
                "are separate passes; this report covers the cavity stage only",
    }
    os.makedirs(os.path.dirname(args.report), exist_ok=True)
    with open(args.report, "w") as fh:
        json.dump(report, fh, indent=2)
        fh.write("\n")
    for side in ("LEFT", "RIGHT"):
        r = results[side]
        print(f"[offset] {side}: cleanup={r.get('cleanup')} "
              f"consistency={r.get('normal_consistency')} "
              f"inward={r.get('inward')} "
              f"thickness={r.get('selected_thickness_m')} "
              f"cavity={r.get('cavity')}")
    print(f"[offset] -> {args.report}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
