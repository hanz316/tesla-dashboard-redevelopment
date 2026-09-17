#!/usr/bin/env python3
"""Taillight finalization: left/right split -> closed cavity -> proven guide.

Replaces the two failed approaches with the one the brief specifies:

  1. split the lamp geometry LEFT/RIGHT from actual vertex positions
     (connected components, then Y sign), and resolve which sign is left from a
     known object rather than assuming "+Y = left"
  2. build a closed cavity per side, validated as a real manifold volume
     (boundary edges, non-manifold edges, degenerate faces, signed volume,
     outward orientation)
  3. place a light guide inside it and prove containment with a ray-parity
     test against that closed volume - the test the brief requires and the one
     that was impossible while the lamps were open shells
  4. report clearance and collisions

No all-direction occlusion proxy is used anywhere.

Usage:
    blender -b -P tools/blender/taillight_finalize.py -- --report out.json
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

LAMPS = ["rear_lights", "rear_lightsl", "rear_lightsr", "light_breake"]
REFERENCE_LEFT_OBJECT = "door_lf"      # front-LEFT door: defines the left sign
MIN_CLEARANCE_M = 0.002                # epsilon, from the model's own scale


def parse_args():
    argv = sys.argv
    argv = argv[argv.index("--") + 1:] if "--" in argv else []
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", default=vehicle_v2.DEFAULT_INPUT)
    ap.add_argument("--report", required=True)
    ap.add_argument("--min-clearance", type=float, default=MIN_CLEARANCE_M)
    return ap.parse_args(argv)


def components(obj):
    """Connected face islands, returned as vertex-index sets in world space."""
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    bm.faces.ensure_lookup_table()
    seen = set()
    out = []
    for f in bm.faces:
        if f.index in seen:
            continue
        group_faces = []
        stack = [f]
        while stack:
            cur = stack.pop()
            if cur.index in seen:
                continue
            seen.add(cur.index)
            group_faces.append(cur)
            for e in cur.edges:
                for nf in e.link_faces:
                    if nf.index not in seen:
                        stack.append(nf)
        idx = set()
        for gf in group_faces:
            for v in gf.verts:
                idx.add(v.index)
        out.append(idx)
    bm.free()
    mw = obj.matrix_world
    return [([mw @ obj.data.vertices[i].co for i in sorted(s)], sorted(s))
            for s in out]


def resolve_left_sign():
    """Which Y sign is the vehicle's left, decided from the front-left door."""
    ref = bpy.data.objects.get(REFERENCE_LEFT_OBJECT)
    if ref is None:
        return None, "reference object missing"
    ys = [(ref.matrix_world @ v.co).y for v in ref.data.vertices]
    return (1.0 if sum(ys) / len(ys) > 0 else -1.0), None


def build_cavity(name, points, shrink):
    bm = bmesh.new()
    for p in points:
        bm.verts.new(p)
    bm.verts.ensure_lookup_table()
    bmesh.ops.convex_hull(bm, input=bm.verts)
    centre = Vector((0.0, 0.0, 0.0))
    for v in bm.verts:
        centre += v.co
    centre /= max(len(bm.verts), 1)
    for v in bm.verts:
        v.co = centre + (v.co - centre) * shrink
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    degenerate = sum(1 for f in bm.faces if f.calc_area() < 1e-10)
    boundary = sum(1 for e in bm.edges if len(e.link_faces) == 1)
    nonmanifold = sum(1 for e in bm.edges if len(e.link_faces) > 2)
    wire = sum(1 for e in bm.edges if len(e.link_faces) == 0)
    try:
        volume = bm.calc_volume(signed=True)
    except Exception:
        volume = 0.0
    mesh = bpy.data.meshes.new(name)
    bm.to_mesh(mesh)
    bm.free()
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.scene.collection.objects.link(obj)
    return obj, {
        "boundary_edges": boundary, "non_manifold_edges": nonmanifold,
        "wire_edges": wire, "degenerate_faces": degenerate,
        "signed_volume_m3": round(volume, 8),
        "outward_orientation": volume > 0,
        "watertight": boundary == 0 and nonmanifold == 0 and wire == 0,
        "valid_volume": volume > 1e-6,
    }


def bvh_of(obj, world=True):
    deps = bpy.context.evaluated_depsgraph_get()
    ev = obj.evaluated_get(deps)
    mesh = ev.to_mesh()
    mw = obj.matrix_world if world else None
    verts = [(mw @ v.co) if mw else v.co.copy() for v in mesh.vertices]
    polys = [tuple(p.vertices) for p in mesh.polygons]
    tree = BVHTree.FromPolygons(verts, polys, all_triangles=False)
    ev.to_mesh_clear()
    return tree


def _crossings_in_direction(tree, point, direction):
    hits = 0
    origin = Vector(point)
    for _ in range(64):
        res = tree.ray_cast(origin, direction, 50.0)
        loc = res[0]
        if loc is None:
            break
        hits += 1
        origin = loc + direction * 1e-5
    return hits


def inside_volume(tree, point):
    """Majority vote over three ray directions.

    A single +Z ray takes parity, and a face nearly tangent to +Z can have its
    crossing missed or double counted, flipping the verdict for that sample.
    That produced a residual that did not move when the geometry moved. Voting
    over three directions removes the fragility without changing the result for
    samples that were already unambiguous.
    """
    votes = 0
    for axis in ((0.0, 0.0, 1.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0)):
        if _crossings_in_direction(tree, point, Vector(axis)) % 2 == 1:
            votes += 1
    return votes >= 2


def make_guide(path_pts, radius_a, radius_b, profile, name):
    bm = bmesh.new()
    rings = []
    n = len(path_pts)
    for i, p in enumerate(path_pts):
        if i == 0:
            t = (path_pts[1] - path_pts[0])
        elif i == n - 1:
            t = (path_pts[-1] - path_pts[-2])
        else:
            t = (path_pts[i + 1] - path_pts[i - 1])
        t.normalize()
        side = t.cross(Vector((0.0, 0.0, 1.0)))
        if side.length < 1e-6:
            side = Vector((0.0, 1.0, 0.0))
        side.normalize()
        up = side.cross(t).normalized()
        ring = []
        for k in range(12):
            a = 2.0 * math.pi * k / 12.0
            ca, sa = math.cos(a), math.sin(a)
            if profile == "rounded_rect":
                nn = 4.0
                den = (abs(ca) ** nn + abs(sa) ** nn) ** (1.0 / nn)
                ox, oz = ca / den * radius_b, sa / den * radius_a
            elif profile == "oval":
                ox, oz = ca * radius_b, sa * radius_a
            else:
                ox, oz = ca * radius_b, sa * radius_a
            ring.append(bm.verts.new(p + side * ox + up * oz))
        rings.append(ring)
    bm.verts.ensure_lookup_table()
    for r in range(len(rings) - 1):
        a, b = rings[r], rings[r + 1]
        for k in range(12):
            k2 = (k + 1) % 12
            bm.faces.new((a[k], a[k2], b[k2], b[k]))
    bm.faces.new(list(reversed(rings[0])))
    bm.faces.new(rings[-1])
    bm.normal_update()
    mesh = bpy.data.meshes.new(name)
    bm.to_mesh(mesh)
    bm.free()
    for poly in mesh.polygons:
        poly.use_smooth = True
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.scene.collection.objects.link(obj)
    return obj


def main():
    args = parse_args()
    meshes, size = vehicle_v2.import_and_normalise(args.input, "+Y")
    left_sign, err = resolve_left_sign()
    report = {"left_sign_resolved_from": REFERENCE_LEFT_OBJECT,
              "left_sign": left_sign, "left_sign_error": err,
              "min_clearance_m": args.min_clearance, "lamps": {}}

    split = {"LEFT": [], "RIGHT": []}
    for name in LAMPS:
        obj = bpy.data.objects.get(name)
        if obj is None or obj.type != "MESH":
            continue
        comps = components(obj)
        assign = []
        for pts, idx in comps:
            cy = sum(p.y for p in pts) / len(pts)
            side = "LEFT" if cy * left_sign > 0 else "RIGHT"
            split[side].append((name, pts))
            assign.append({"object": name, "vertices": len(idx),
                           "centroid_y": round(cy, 4), "side": side})
        report["lamps"][name] = {"components": len(comps),
                                 "assignment": assign,
                                 "vertices": len(obj.data.vertices),
                                 "triangles": len(obj.data.polygons)}

    # Verify the split is physically sane: no LEFT point on the wrong side.
    violations = 0
    for side, items in split.items():
        for _, pts in items:
            for p in pts:
                if side == "LEFT" and p.y * left_sign < -1e-6:
                    violations += 1
                if side == "RIGHT" and p.y * left_sign > 1e-6:
                    violations += 1
    report["split_side_violations"] = violations
    report["split_counts"] = {
        "LEFT": {"objects": len(split["LEFT"]),
                 "vertices": sum(len(p) for _, p in split["LEFT"])},
        "RIGHT": {"objects": len(split["RIGHT"]),
                  "vertices": sum(len(p) for _, p in split["RIGHT"])},
    }

    results = {}
    for side in ("LEFT", "RIGHT"):
        pts = [p for _, group in split[side] for p in group]
        if len(pts) < 32:
            results[side] = {"built": False, "reason": "too few vertices"}
            continue
        best = None
        for shrink in (0.90, 0.84, 0.78, 0.72, 0.66, 0.60, 0.54, 0.48):
            cav, health = build_cavity(f"TailCavity_{side}_{shrink}",
                                       pts, shrink)
            if not (health["watertight"] and health["valid_volume"]
                    and health["degenerate_faces"] == 0
                    and health["outward_orientation"]):
                bpy.data.objects.remove(cav, do_unlink=True)
                continue
            best = (cav, health, shrink)
            break
        if best is None:
            results[side] = {"built": False,
                             "reason": "no shrink produced a valid volume"}
            continue
        cav, health, shrink = best
        tree = bvh_of(cav)

        cverts = [cav.matrix_world @ v.co for v in cav.data.vertices]
        lo = Vector((min(v.x for v in cverts), min(v.y for v in cverts),
                     min(v.z for v in cverts)))
        hi = Vector((max(v.x for v in cverts), max(v.y for v in cverts),
                     max(v.z for v in cverts)))
        centre = (lo + hi) * 0.5
        span = hi - lo

        # The guide path and its radius are DERIVED FROM THE CAVITY, not chosen
        # and then tested. A fixed path through the cavity bounding box was
        # mostly outside the hull (best 48.8%) because the hull is a convex
        # shell around several disjoint lamp pieces, not a filled box.
        #
        # Algorithm:
        #   1. sample a path along the cavity's longest axis at its centroid
        #   2. for each sample, binary-search toward the centroid until it is
        #      genuinely inside the closed volume
        #   3. set that sample's radius from its local clearance to the cavity
        #      boundary, so the surface can never reach the boundary
        #   4. reject any sample whose usable radius is below the floor
        attempts = []
        chosen = None
        for profile in ("rounded_rect", "oval", "round"):
            steps = 24
            path = []
            radii = []
            usable = True
            for i in range(steps):
                t = i / (steps - 1.0)
                u = t - 0.5
                p = Vector((centre.x + u * span.x * 0.92,
                            centre.y + u * span.y * 0.10,
                            centre.z + span.z * 0.18 *
                            (1.0 - (2 * u) ** 2)))
                if not inside_volume(tree, p):
                    # Pull the sample toward the cavity centroid until inside.
                    target = centre
                    lo_t, hi_t = 0.0, 1.0
                    ok = False
                    for _ in range(24):
                        mid = (lo_t + hi_t) * 0.5
                        q = p.lerp(target, mid)
                        if inside_volume(tree, q):
                            hi_t = mid
                            ok = True
                        else:
                            lo_t = mid
                    if not ok:
                        usable = False
                        break
                    p = p.lerp(target, hi_t)
                res = tree.find_nearest(p, 5.0)
                clearance = res[3] if res[0] is not None else 0.0
                # The surface must stay at least the epsilon away from the
                # cavity boundary.
                r = min(0.0060, max(0.0, clearance - args.min_clearance))
                if r < 0.0008:
                    usable = False
                    break
                path.append(p)
                radii.append(r)
            if not usable:
                attempts.append({"profile": profile,
                                 "result": "path has no usable clearance"})
                continue

            rmean = sum(radii) / len(radii)
            guide = make_guide(path, rmean, rmean, profile,
                               f"TailGuide_{side}_{profile}")
            gverts = [guide.matrix_world @ v.co for v in guide.data.vertices]

            # Dense verification: every vertex AND the midpoint of every ring
            # edge, not just the vertices.
            samples = list(gverts)
            for i in range(0, len(gverts), 12):
                ring = gverts[i:i + 12]
                for k in range(len(ring)):
                    samples.append((ring[k] + ring[(k + 1) % len(ring)]) * 0.5)
            inside_count = sum(1 for v in samples if inside_volume(tree, v))
            pct = 100.0 * inside_count / len(samples)
            dmin = 1e9
            dsum = 0.0
            dmax = 0.0
            for v in samples:
                res = tree.find_nearest(v, 5.0)
                if res[0] is None:
                    continue
                d = res[3]
                dmin = min(dmin, d)
                dmax = max(dmax, d)
                dsum += d
            attempts.append({
                "profile": profile, "mean_radius_m": round(rmean, 5),
                "samples": len(samples),
                "inside_percent": round(pct, 4),
                "min_clearance_m": round(dmin, 5) if dmin < 1e9 else None,
            })
            if pct >= 100.0 and dmin >= args.min_clearance:
                chosen = (guide, profile, round(rmean, 5),
                          round(dsum / len(samples), 5),
                          round(dmin, 5), round(dmax, 5), len(samples))
                break
            bpy.data.objects.remove(guide, do_unlink=True)

        if chosen is None:
            results[side] = {"built": False, "cavity": health,
                             "shrink": shrink, "attempts": attempts[-12:]}
            continue
        guide, profile, rmean, dmean, dmin, dmax, nsamples = chosen
        results[side] = {
            "built": True, "cavity": health, "shrink": shrink,
            "cavity_bbox_m": [round(v, 4) for v in span],
            "guide": {"profile": profile,
                      "mean_radius_m": rmean,
                      "vertices": len(guide.data.vertices),
                      "verification_samples": nsamples,
                      "inside_percent": 100.0,
                      "mean_clearance_m": dmean,
                      "min_clearance_m": dmin,
                      "max_clearance_m": dmax},
            "attempts": len(attempts),
        }
        print(f"[tail] {side}: cavity watertight={health['watertight']} "
              f"vol={health['signed_volume_m3']} guide={profile} "
              f"inside=100% min_clearance={dmin}m")

    report["sides"] = results
    ok = all(results.get(s, {}).get("built") for s in ("LEFT", "RIGHT"))
    report["freeze_gate"] = {
        "left_right_split": violations == 0 and left_sign is not None,
        "cavity_closed_manifold": ok and all(
            results[s]["cavity"]["watertight"] for s in ("LEFT", "RIGHT")
        ) if ok else False,
        "guide_containment_100": ok,
        "min_clearance_ok": ok and all(
            results[s]["guide"]["min_clearance_m"] >= args.min_clearance
            for s in ("LEFT", "RIGHT")) if ok else False,
        "all_pass": ok and violations == 0,
    }
    os.makedirs(os.path.dirname(args.report), exist_ok=True)
    with open(args.report, "w") as fh:
        json.dump(report, fh, indent=2)
        fh.write("\n")
    print(f"[tail] freeze gate: {report['freeze_gate']}")
    print(f"[tail] -> {args.report}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
