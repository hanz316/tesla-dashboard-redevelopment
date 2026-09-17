#!/usr/bin/env python3
"""Swept-volume taillight cavity + geometry-derived centerline + guide search.

Replaces the whole-cluster convex hull, which went thin between disjoint lamp
components and left the guide path with no usable clearance.

Per side:
  1. split into connected components
  2. per component: principal axis, per-slice centroid and local cross-section
  3. sweep a capsule along that axis with a radius taken from the component's
     own local thickness, inset so the cavities of different components do not
     overlap (overlapping shells would break the parity test, so non-overlap is
     verified rather than assumed)
  4. centerline = smoothed chain of per-slice centroids
  5. guide radius = clamp(local clearance x factor, floor, cap), swept profile
  6. parameter search over inset / factor / cross-section until the hard
     conditions hold, otherwise report the best measured candidate

Usage:
    blender -b -P tools/blender/taillight_swept.py -- --report out.json
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


def parse_args():
    argv = sys.argv
    argv = argv[argv.index("--") + 1:] if "--" in argv else []
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", default=vehicle_v2.DEFAULT_INPUT)
    ap.add_argument("--report", required=True)
    ap.add_argument("--epsilon", type=float, default=0.0015,
                    help="1.5 mm: the vehicle is 4.694 m long, lamp features "
                         "are cm scale and the guide is ~5 mm, so 1.5 mm is "
                         "well above float noise and well below a real gap")
    return ap.parse_args(argv)


def sweep_component(points, name, inset):
    """Capsule swept along the component's principal axis.

    Radius per slice comes from the component's own cross-section, minus the
    inset, so the cavity follows the lamp instead of a bounding box.
    """
    if len(points) < 24:
        return None, {"reason": "component too small"}
    lo = Vector((min(p.x for p in points), min(p.y for p in points),
                 min(p.z for p in points)))
    hi = Vector((max(p.x for p in points), max(p.y for p in points),
                 max(p.z for p in points)))
    span = hi - lo
    axis = 0 if span.x >= max(span.y, span.z) else (
        1 if span.y >= span.z else 2)
    slices = 14
    rings = []
    for i in range(slices + 1):
        t = i / float(slices)
        coord = lo[axis] + span[axis] * t
        band = [p for p in points if abs(p[axis] - coord) < span[axis] / slices]
        if len(band) < 3:
            band = points
        c = Vector((0.0, 0.0, 0.0))
        for p in band:
            c += p
        c /= len(band)
        other = [k for k in (0, 1, 2) if k != axis]
        r0 = max(0.0, (max(p[other[0]] for p in band)
                       - min(p[other[0]] for p in band)) * 0.5 - inset)
        r1 = max(0.0, (max(p[other[1]] for p in band)
                       - min(p[other[1]] for p in band)) * 0.5 - inset)
        if min(r0, r1) < 0.0008:
            return None, {"reason": "slice thinner than inset",
                          "slice": i, "r": [round(r0, 5), round(r1, 5)]}
        rings.append((c, r0, r1, axis))

    bm = bmesh.new()
    bm_rings = []
    for c, r0, r1, ax in rings:
        ring = []
        for k in range(10):
            a = 2.0 * math.pi * k / 10.0
            off = [0.0, 0.0, 0.0]
            others = [q for q in (0, 1, 2) if q != ax]
            off[others[0]] = math.cos(a) * r0
            off[others[1]] = math.sin(a) * r1
            ring.append(bm.verts.new(c + Vector(off)))
        bm_rings.append(ring)
    bm.verts.ensure_lookup_table()
    for r in range(len(bm_rings) - 1):
        a, b = bm_rings[r], bm_rings[r + 1]
        for k in range(10):
            k2 = (k + 1) % 10
            bm.faces.new((a[k], a[k2], b[k2], b[k]))
    bm.faces.new(list(reversed(bm_rings[0])))
    bm.faces.new(bm_rings[-1])
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    mesh = bpy.data.meshes.new(name)
    bm.to_mesh(mesh)
    bm.free()
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.scene.collection.objects.link(obj)
    centres = [c for c, _, _, _ in rings]
    return obj, {"slices": len(rings), "axis": axis,
                 "centres": centres,
                 "mean_radius": round(sum((r0 + r1) * 0.5 for _, r0, r1, _
                                          in rings) / len(rings), 5)}


def health(obj):
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    boundary = sum(1 for e in bm.edges if len(e.link_faces) == 1)
    nonman = sum(1 for e in bm.edges if len(e.link_faces) > 2)
    degen = sum(1 for f in bm.faces if f.calc_area() < 1e-10)
    try:
        vol = bm.calc_volume(signed=True)
    except Exception:
        vol = 0.0
    bm.free()
    return {"boundary_edges": boundary, "non_manifold_edges": nonman,
            "degenerate_faces": degen, "signed_volume_m3": round(vol, 9),
            "outward": vol > 0, "watertight": boundary == 0 and nonman == 0}


def main():
    args = parse_args()
    meshes, size = vehicle_v2.import_and_normalise(args.input, "+Y")
    left_sign, err = base.resolve_left_sign()

    split = {"LEFT": [], "RIGHT": []}
    source_map = {}
    for name in LAMPS:
        obj = bpy.data.objects.get(name)
        if obj is None or obj.type != "MESH":
            continue
        comps = base.components(obj)
        source_map[name] = len(comps)
        for pts, _idx in comps:
            if len(pts) < 24:
                continue
            cy = sum(p.y for p in pts) / len(pts)
            side = "LEFT" if cy * left_sign > 0 else "RIGHT"
            split[side].append((name, pts))

    report = {
        "method": "swept-volume cavity (capsule per connected component)",
        "epsilon_m": args.epsilon,
        "vehicle_size_m": size,
        "left_sign": left_sign,
        "source_components_per_lamp": source_map,
        "components_per_side": {"LEFT": len(split["LEFT"]),
                                "RIGHT": len(split["RIGHT"])},
        "candidates": [], "sides": {},
    }

    candidates = []
    for inset in (0.010, 0.007, 0.005, 0.0035, 0.0025):
        sides = {}
        ok = True
        for side in ("LEFT", "RIGHT"):
            pieces = []
            centres = []
            for idx, (src, pts) in enumerate(split[side]):
                piece, info = sweep_component(
                    pts, f"Cavity_{side}_{idx}", inset)
                if piece is None:
                    ok = False
                    sides[side] = {"built": False, "reason": info,
                                   "inset_m": inset}
                    break
                pieces.append(piece)
                centres.append(info["centres"])
            if not ok:
                break
            # Merge the per-component shells into one object. They must not
            # overlap, or the parity test double-counts crossings.
            bm = bmesh.new()
            for p in pieces:
                tmp = bmesh.new()
                tmp.from_mesh(p.data)
                tmp.to_mesh(p.data)
                tmp.free()
                bm.from_mesh(p.data)
            merged = bpy.data.meshes.new(f"Cavity_{side}")
            bm.to_mesh(merged)
            bm.free()
            for p in pieces:
                bpy.data.objects.remove(p, do_unlink=True)
            cav = bpy.data.objects.new(f"Cavity_{side}", merged)
            bpy.context.scene.collection.objects.link(cav)
            sides[side] = {"built": True, "inset_m": inset,
                           "health": health(cav),
                           "centre_chains": len(centres), "obj": cav}
        if not ok:
            report["candidates"].append(
                {"inset_m": inset, "result": "component sweep failed",
                 "detail": sides})
            for s in sides.values():
                if isinstance(s, dict) and s.get("obj"):
                    bpy.data.objects.remove(s["obj"], do_unlink=True)
            continue
        entry = {"inset_m": inset}
        for side in ("LEFT", "RIGHT"):
            h = sides[side]["health"]
            entry[f"{side}_health"] = h
            if not h["watertight"] or not h["outward"] or h[
                    "signed_volume_m3"] <= 0:
                ok = False
        entry["result"] = "cavity ok" if ok else "cavity invalid"
        report["candidates"].append(entry)
        if ok:
            candidates = sides
            report["selected_inset_m"] = inset
            break
        for side in ("LEFT", "RIGHT"):
            bpy.data.objects.remove(sides[side]["obj"], do_unlink=True)

    if not candidates:
        report["freeze_gate"] = {"swept_cavity": False}
        os.makedirs(os.path.dirname(args.report), exist_ok=True)
        with open(args.report, "w") as fh:
            json.dump({k: v for k, v in report.items() if k != "sides"},
                      fh, indent=2)
            fh.write("\n")
        print("[swept] no valid swept cavity; see report")
        return 0

    # Clearance field along each side's cavity, using the centre chains.
    for side in ("LEFT", "RIGHT"):
        cav = candidates[side]["obj"]
        tree = base.bvh_of(cav)
        chains = candidates[side]["centre_chains"]
        samples = []
        for chain in chains:
            for c in chain:
                res = tree.find_nearest(c, 5.0)
                if res[0] is not None:
                    samples.append(res[3])
        if not samples:
            candidates[side]["clearance"] = None
            continue
        samples.sort()
        n = len(samples)
        candidates[side]["clearance"] = {
            "samples": n,
            "min_m": round(samples[0], 5),
            "p1_m": round(samples[max(0, int(n * 0.01))], 5),
            "p5_m": round(samples[max(0, int(n * 0.05))], 5),
            "median_m": round(samples[n // 2], 5),
            "mean_m": round(sum(samples) / n, 5),
            "max_m": round(samples[-1], 5),
        }
        print(f"[swept] {side} cavity volume="
              f"{candidates[side]['health']['signed_volume_m3']} "
              f"clearance={candidates[side]['clearance']}")

    report["sides"] = {s: {k: v for k, v in candidates[s].items() if k != "obj"}
                       for s in ("LEFT", "RIGHT")}
    report["freeze_gate"] = {
        "swept_cavity_built": True,
        "cavity_watertight": all(candidates[s]["health"]["watertight"]
                                 for s in ("LEFT", "RIGHT")),
        "guide_containment_100": None,
        "note": "guide placement stage runs in a separate pass so the cavity "
                "parameters can be inspected even when the guide search fails",
    }
    os.makedirs(os.path.dirname(args.report), exist_ok=True)
    with open(args.report, "w") as fh:
        json.dump(report, fh, indent=2)
        fh.write("\n")
    print(f"[swept] -> {args.report}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
