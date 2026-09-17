#!/usr/bin/env python3
"""Part A/B-adjacent: geometry + normal diagnostic for MODEL A.

The question this answers is not "does the car look good" but "is the plastic
look coming from the mesh". A mesh with inconsistent normals, non-manifold
edges, duplicated vertices or a few huge faces will produce pinched, wavy or
facetted reflections no matter how good the shader is - and no amount of HDRI
searching fixes that.

Reports per exterior object:
  vertex / face / triangle / quad / ngon counts
  non-manifold, boundary and wire edges
  duplicated vertices (coincident within 1e-5)
  flipped faces (counted against a recalculate-outside reference)
  custom split normals, smooth-face share, sharp edges
  modifiers (auto smooth / weighted normal / subdivision)
  edge length and face area distribution, large-face share

Usage:
    blender -b -P tools/blender/diagnose_body_geometry.py -- \
        [--json out.json] [--all]
"""

import argparse
import json
import math
import os
import sys

try:
    import bpy
    import bmesh
except ImportError:  # pragma: no cover
    sys.exit("Run inside Blender")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import render_vehicle_visual_v2 as vehicle_v2  # noqa: E402

# Exterior panels we care about. MODEL A does NOT have a separate object for
# the front fenders, the rear quarters or the C pillars - they are all part of
# "body" - so those regions can only be judged through body as a whole.
EXTERIOR = {
    "body": "body shell (roof metal, fenders, rear quarters, C pillars)",
    "bonnet_ok": "hood",
    "boot": "trunk lid",
    "door_lf": "front left door",
    "door_rf": "front right door",
    "door_lr": "rear left door",
    "door_rr": "rear right door",
    "front_bumper_ok": "front bumper",
    "rear_bumper_ok": "rear bumper",
    "bodysills": "rocker / sill",
}

SECONDARY = {
    "glass": "glass (roof pane + windows)",
    "tembus_depan_ok": "front glass piece",
    "tembus_belakang": "rear glass piece",
    "tembus_boot_ok": "trunk glass piece",
    "black_lights": "light housings (black)",
    "chrome_light": "headlight trim",
    "back_chrome_light": "taillight trim",
    "aluminium_light": "light trim",
    "hub_lf": "front left wheel",
    "hub_rf": "front right wheel",
    "hub_lb": "rear left wheel",
    "hub_rb": "rear right wheel",
}


def parse_args():
    argv = sys.argv
    argv = argv[argv.index("--") + 1:] if "--" in argv else []
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", default=vehicle_v2.DEFAULT_INPUT)
    ap.add_argument("--json", default=None)
    ap.add_argument("--all", action="store_true",
                    help="report every mesh object, not just the named panels")
    return ap.parse_args(argv)


def object_report(obj):
    mesh = obj.data
    bm = bmesh.new()
    bm.from_mesh(mesh)
    bm.faces.ensure_lookup_table()

    tris = sum(max(len(f.verts) - 2, 0) for f in bm.faces)
    quads = sum(1 for f in bm.faces if len(f.verts) == 4)
    ngons = sum(1 for f in bm.faces if len(f.verts) > 4)
    non_manifold = sum(1 for e in bm.edges if not e.is_manifold)
    boundary = sum(1 for e in bm.edges if len(e.link_faces) == 1)
    wire = sum(1 for e in bm.edges if len(e.link_faces) == 0)
    interior = sum(1 for e in bm.edges if len(e.link_faces) > 2)

    # Duplicate vertices: coincident positions that were never welded.
    seen = {}
    duplicates = 0
    for v in bm.verts:
        key = (round(v.co.x, 5), round(v.co.y, 5), round(v.co.z, 5))
        if key in seen:
            duplicates += 1
        else:
            seen[key] = True

    # Flipped faces: how many faces disagree with a recalculated-outside
    # reference. Any non-zero count means the mesh is not consistently wound.
    original = {f.index: f.normal.copy() for f in bm.faces}
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.normal_update()
    flipped = 0
    for f in bm.faces:
        before = original.get(f.index)
        if before is not None and before.dot(f.normal) < -0.5:
            flipped += 1

    edge_lengths = [e.calc_length() for e in bm.edges]
    areas = [f.calc_area() for f in bm.faces]

    def stats(values):
        if not values:
            return {}
        values = sorted(values)
        n = len(values)
        return {
            "min": values[0],
            "median": values[n // 2],
            "max": values[-1],
            "p99": values[int(n * 0.99)],
        }

    median_area = stats(areas).get("median", 0.0)
    large = sum(1 for a in areas if median_area > 0 and a > median_area * 9.0)

    smooth_faces = sum(1 for p in mesh.polygons if p.use_smooth)
    sharp_edges = sum(1 for e in mesh.edges if e.use_edge_sharp)

    bm.free()
    return {
        "name": obj.name,
        "vertices": len(mesh.vertices),
        "polygons": len(mesh.polygons),
        "triangles": tris,
        "quads": quads,
        "ngons": ngons,
        "ngon_share": round(ngons / max(len(mesh.polygons), 1), 4),
        "non_manifold_edges": non_manifold,
        "boundary_edges": boundary,
        "interior_edges_gt2_faces": interior,
        "wire_edges": wire,
        "duplicate_vertices": duplicates,
        "flipped_faces": flipped,
        "flipped_share": round(flipped / max(len(mesh.polygons), 1), 4),
        "has_custom_split_normals": bool(getattr(mesh, "has_custom_normals",
                                                 False)),
        "smooth_face_share": round(smooth_faces / max(len(mesh.polygons), 1), 4),
        "sharp_edges": sharp_edges,
        "modifiers": [m.type for m in obj.modifiers],
        "materials": [m.name for m in mesh.materials if m],
        "edge_length": stats(edge_lengths),
        "face_area": stats(areas),
        "large_faces_gt9x_median": large,
        "large_face_share": round(large / max(len(areas), 1), 4),
        "area_max_over_median": round(
            (stats(areas).get("max", 0.0) / median_area), 2)
        if median_area > 0 else 0.0,
    }


def main():
    args = parse_args()
    meshes, size = vehicle_v2.import_and_normalise(args.input, "+Y")
    by_name = {o.name: o for o in meshes}

    wanted = dict(EXTERIOR)
    wanted.update(SECONDARY)
    if args.all:
        for o in meshes:
            wanted.setdefault(o.name, "other")

    report = {"vehicle_size_m": size, "objects": []}
    print(f"[geom] imported {len(meshes)} mesh objects, "
          f"normalised size {size}")
    for name, role in sorted(wanted.items()):
        obj = by_name.get(name)
        if obj is None:
            print(f"[geom] MISSING object: {name} ({role})")
            continue
        r = object_report(obj)
        r["role"] = role
        report["objects"].append(r)

    print(f"\n{'object':18s} {'verts':>7s} {'polys':>7s} {'tris':>7s} "
          f"{'ngon%':>6s} {'nonMan':>7s} {'dupV':>6s} {'flip%':>6s} "
          f"{'custN':>6s} {'smooth%':>8s} {'maxArea/med':>11s} {'large%':>7s}")
    print("-" * 116)
    for r in report["objects"]:
        print(f"{r['name'][:18]:18s} {r['vertices']:7d} {r['polygons']:7d} "
              f"{r['triangles']:7d} {r['ngon_share']*100:6.1f} "
              f"{r['non_manifold_edges']:7d} {r['duplicate_vertices']:6d} "
              f"{r['flipped_share']*100:6.1f} "
              f"{str(r['has_custom_split_normals']):>6s} "
              f"{r['smooth_face_share']*100:8.1f} "
              f"{r['area_max_over_median']:11.1f} "
              f"{r['large_face_share']*100:7.2f}")

    if args.json:
        os.makedirs(os.path.dirname(args.json), exist_ok=True)
        with open(args.json, "w") as fh:
            json.dump(report, fh, indent=2)
            fh.write("\n")
        print(f"\n[geom] -> {args.json}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
