#!/usr/bin/env python3
"""Part B: does MODEL A's surface geometry cap the achievable reflection?

Triangle count is not the question. The question is whether the SURFACE is
smooth enough to carry a reflection: dihedral angles between adjacent faces,
triangle shape and size distribution, and how much of the panel is covered by
a handful of oversized triangles.

Each panel is classified as:
    FIXABLE_BY_NORMALS     geometry is fine-grained, only shading disagrees
    FIXABLE_BY_LOCAL_REMESH geometry is coarse or irregular but the shape is
                           right, so retopology would help
    SOURCE_MODEL_LIMITATION the panel does not carry enough surface to fix,
                           or is averaged out of a merged object

Usage:
    blender -b -P tools/blender/report_mesh_quality.py -- --json out.json
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

PANELS = {
    "door_lf": "front left door",
    "door_rf": "front right door",
    "door_lr": "rear left door",
    "door_rr": "rear right door",
    "bonnet_ok": "hood",
    "boot": "trunk lid",
    "body": "body shell (roof, fenders, rear quarters, C pillars)",
    "front_bumper_ok": "front bumper",
    "rear_bumper_ok": "rear bumper",
}


def parse_args():
    argv = sys.argv
    argv = argv[argv.index("--") + 1:] if "--" in argv else []
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", default=vehicle_v2.DEFAULT_INPUT)
    ap.add_argument("--json", default=None)
    ap.add_argument("--thin-aspect", type=float, default=8.0)
    return ap.parse_args(argv)


def percentile(values, p):
    if not values:
        return 0.0
    values = sorted(values)
    return values[min(len(values) - 1, int(len(values) * p))]


def analyse(obj, thin_aspect):
    mesh = obj.data
    bm = bmesh.new()
    bm.from_mesh(mesh)
    bm.faces.ensure_lookup_table()
    bm.edges.ensure_lookup_table()

    # Dihedral angle between adjacent faces: the direct measure of faceting.
    dihedrals = []
    for e in bm.edges:
        if len(e.link_faces) == 2:
            a, b = e.link_faces
            try:
                dihedrals.append(math.degrees(a.normal.angle(b.normal)))
            except ValueError:
                pass

    aspects, areas, edge_lengths = [], [], []
    for f in bm.faces:
        ls = [e.calc_length() for e in f.edges]
        if len(ls) >= 3:
            lo, hi = min(ls), max(ls)
            if lo > 1e-9:
                aspects.append(hi / lo)
        areas.append(f.calc_area())
    for e in bm.edges:
        edge_lengths.append(e.calc_length())

    # Connected islands
    seen = set()
    island_faces = []
    for f in bm.faces:
        if f.index in seen:
            continue
        group = []
        stack = [f]
        while stack:
            cur = stack.pop()
            if cur.index in seen:
                continue
            seen.add(cur.index)
            group.append(cur)
            for e in cur.edges:
                for nf in e.link_faces:
                    if nf.index not in seen:
                        stack.append(nf)
        island_faces.append(group)
    islands = len(island_faces)

    # The statistics above cover the WHOLE object, which for these imported
    # panels includes dozens of small internal pieces. What matters for a
    # reflection is the exterior skin, so the same measurements are repeated
    # on the largest connected island only.
    largest = max(island_faces, key=len) if island_faces else []
    big_dih, big_aspect, big_areas = [], [], []
    lset = set(f.index for f in largest)
    for f in largest:
        ls = [e.calc_length() for e in f.edges]
        if len(ls) >= 3:
            lo, hi = min(ls), max(ls)
            if lo > 1e-9:
                big_aspect.append(hi / lo)
        big_areas.append(f.calc_area())
    for e in bm.edges:
        fs = [f for f in e.link_faces if f.index in lset]
        if len(fs) == 2:
            try:
                big_dih.append(math.degrees(fs[0].normal.angle(fs[1].normal)))
            except ValueError:
                pass
    big_med = percentile(big_areas, 0.5)

    surface_area = sum(areas)
    vertex_density = len(bm.verts) / surface_area if surface_area > 0 else 0.0
    thin = sum(1 for a in aspects if a > thin_aspect)

    med_area = percentile(areas, 0.5)
    face_count = len(bm.faces)
    bm.free()
    return {
        "vertices": len(mesh.vertices),
        "triangles": len(mesh.polygons),
        "surface_area_m2": round(surface_area, 4),
        "vertex_density_per_m2": round(vertex_density, 1),
        "dihedral_median_deg": round(percentile(dihedrals, 0.5), 2),
        "dihedral_p95_deg": round(percentile(dihedrals, 0.95), 2),
        "dihedral_p99_deg": round(percentile(dihedrals, 0.99), 2),
        "aspect_median": round(percentile(aspects, 0.5), 2),
        "aspect_p95": round(percentile(aspects, 0.95), 2),
        "thin_triangle_share": round(thin / max(len(aspects), 1), 4),
        "area_median_m2": round(med_area, 8),
        "area_p95_over_median": round(
            percentile(areas, 0.95) / med_area, 2) if med_area else 0.0,
        "area_max_over_median": round(
            (max(areas) / med_area), 2) if med_area else 0.0,
        "edge_median_m": round(percentile(edge_lengths, 0.5), 5),
        "islands": islands,
        "largest_island_faces": len(largest),
        "largest_island_share": round(len(largest) / max(face_count, 1), 4),
        "skin_dihedral_median_deg": round(percentile(big_dih, 0.5), 2),
        "skin_dihedral_p95_deg": round(percentile(big_dih, 0.95), 2),
        "skin_aspect_p95": round(percentile(big_aspect, 0.95), 2),
        "skin_area_max_over_median": round(
            (max(big_areas) / big_med), 2) if big_med else 0.0,
    }


def classify(m):
    """Deliberately conservative: the label is a triage aid, not a verdict."""
    # Judged on the exterior skin (largest island), not on the whole object.
    dih = m["skin_dihedral_p95_deg"]
    asp = m["skin_aspect_p95"]
    if dih > 18.0 or asp > 25.0:
        if m["vertex_density_per_m2"] < 400:
            return "SOURCE_MODEL_LIMITATION", (
                f"skin coarse and irregular: dihedral p95 {dih}deg, aspect p95 "
                f"{asp}, density {m['vertex_density_per_m2']}/m2")
        return "FIXABLE_BY_LOCAL_REMESH", (
            f"skin has density ({m['vertex_density_per_m2']}/m2) but is "
            f"irregular: dihedral p95 {dih}deg, aspect p95 {asp}")
    if asp > 12.0 or m["skin_area_max_over_median"] > 100.0:
        return "FIXABLE_BY_LOCAL_REMESH", (
            f"skin is smooth (dihedral p95 {dih}deg) but triangle sizes are "
            f"uneven (max/median {m['skin_area_max_over_median']})")
    return "FIXABLE_BY_NORMALS", (
        f"skin smooth and even: dihedral p95 {dih}deg, aspect p95 {asp}, "
        f"area max/median {m['skin_area_max_over_median']}")


def main():
    args = parse_args()
    meshes, size = vehicle_v2.import_and_normalise(args.input, "+Y")
    by_name = {o.name: o for o in meshes}

    report = {"vehicle_size_m": size, "panels": {}}
    print(f"{'panel':16s} {'allDih95':>8s} {'skinDih95':>9s} {'skinAsp95':>10s} "
          f"{'thin%':>6s} {'max/med':>8s} {'dens/m2':>9s} {'islands':>8s} "
          f"{'skin%':>6s}  class")
    print("-" * 128)
    for name, role in PANELS.items():
        obj = by_name.get(name)
        if obj is None:
            print(f"[quality] MISSING {name}")
            continue
        m = analyse(obj, args.thin_aspect)
        label, why = classify(m)
        report["panels"][name] = {"role": role, "metrics": m,
                                  "class": label, "reason": why}
        print(f"{name:16s} {m['dihedral_p95_deg']:8.2f} "
              f"{m['skin_dihedral_p95_deg']:9.2f} {m['skin_aspect_p95']:10.2f} "
              f"{m['thin_triangle_share']*100:6.1f} "
              f"{m['area_max_over_median']:8.1f} "
              f"{m['vertex_density_per_m2']:9.1f} {m['islands']:8d} "
              f"{m['largest_island_share']*100:6.1f}  "
              f"{label}")

    if args.json:
        os.makedirs(os.path.dirname(args.json), exist_ok=True)
        with open(args.json, "w") as fh:
            json.dump(report, fh, indent=2)
            fh.write("\n")
        print(f"\n[quality] -> {args.json}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
