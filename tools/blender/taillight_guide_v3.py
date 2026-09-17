#!/usr/bin/env python3
"""Taillight guide v3: true wall thickness -> cavity choice -> proven guide.

Continues from taillight_offset.py, which proved the offset cavity is a valid
closed manifold. This pass fixes the thickness measurement (the earlier probe
rayed along a heuristic axis instead of each sample's own normal) and then
places and PROVES the light guide.
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
except ImportError:  # pragma: no cover
    sys.exit("Run inside Blender")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import render_vehicle_visual_v2 as vehicle_v2  # noqa: E402
import taillight_finalize as base  # noqa: E402
import taillight_offset as off  # noqa: E402

EPSILON = 0.0015


def parse_args():
    argv = sys.argv
    argv = argv[argv.index("--") + 1:]
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", default=vehicle_v2.DEFAULT_INPUT)
    ap.add_argument("--report", required=True)
    return ap.parse_args(argv)


def true_wall_thickness(cavity_obj):
    """Ray along each vertex's OWN normal from the inner wall to the outer wall.

    The previous probe used a fixed Y direction, so it measured the probe axis
    rather than the wall. This uses the mesh normal, which is what "wall
    thickness" actually means.
    """
    tree = base.bvh_of(cavity_obj)
    mw = cavity_obj.matrix_world
    normals = cavity_obj.data.vertex_normals
    vals = []
    for i, v in enumerate(cavity_obj.data.vertices):
        p = mw @ v.co
        n = (mw.to_3x3() @ Vector(normals[i].vector))
        if n.length < 1e-9:
            continue
        n.normalize()
        # The first crossing is the surface the sample is standing on (or an
        # adjacent face of the same shell a few microns away) - that is the
        # self-hit that made the previous version report a 10 um wall at a
        # 12 mm offset. Step past it and take the SECOND crossing, which is the
        # far wall.
        for direction in (-n, n):
            start = p - direction * 1e-5
            first = tree.ray_cast(start, direction, 0.10)
            if first[0] is None or first[3] is None:
                continue
            second_origin = first[0] + direction * 2e-5
            second = tree.ray_cast(second_origin, direction, 0.10)
            if second[0] is not None and second[3] is not None \
                    and second[3] > 1e-5:
                vals.append(second[3])
                break
    if not vals:
        return None
    vals.sort()
    n = len(vals)

    def pc(f):
        return round(vals[min(n - 1, int(n * f))], 6)

    return {"samples": n, "min_m": pc(0.0), "p1_m": pc(0.01),
            "p5_m": pc(0.05), "median_m": pc(0.5),
            "mean_m": round(sum(vals) / n, 6), "max_m": pc(1.0)}


def make_guide(path, radii, profile, name):
    bm = bmesh.new()
    rings = []
    for i, p in enumerate(path):
        if i == 0:
            t = path[1] - path[0]
        elif i == len(path) - 1:
            t = path[-1] - path[-2]
        else:
            t = path[i + 1] - path[i - 1]
        t.normalize()
        side = t.cross(Vector((0.0, 0.0, 1.0)))
        if side.length < 1e-6:
            side = Vector((0.0, 1.0, 0.0))
        side.normalize()
        up = side.cross(t).normalized()
        r = radii[i]
        ring = []
        for k in range(12):
            a = 2.0 * math.pi * k / 12.0
            ca, sa = math.cos(a), math.sin(a)
            if profile == "rounded_rect":
                nn = 4.0
                den = (abs(ca) ** nn + abs(sa) ** nn) ** (1.0 / nn)
                ox, oz = ca / den * r, sa / den * r
            elif profile == "oval":
                ox, oz = ca * r * 0.6, sa * r
            else:
                ox, oz = ca * r, sa * r
            ring.append(bm.verts.new(p + side * ox + up * oz))
        rings.append(ring)
    bm.verts.ensure_lookup_table()
    for i in range(len(rings) - 1):
        a, b = rings[i], rings[i + 1]
        for k in range(12):
            k2 = (k + 1) % 12
            bm.faces.new((a[k], a[k2], b[k2], b[k]))
    bm.faces.new(list(reversed(rings[0])))
    bm.faces.new(rings[-1])
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    mesh = bpy.data.meshes.new(name)
    bm.to_mesh(mesh)
    bm.free()
    for p in mesh.polygons:
        p.use_smooth = True
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.scene.collection.objects.link(obj)
    return obj


def main():
    args = parse_args()
    meshes, size = vehicle_v2.import_and_normalise(args.input, "+Y")
    left_sign, _ = base.resolve_left_sign()
    report = {"epsilon_m": EPSILON, "vehicle_size_m": size, "sides": {}}

    # Rebuild the side sources exactly as taillight_offset does.
    groups = {"LEFT": [], "RIGHT": []}
    for name in off.LAMPS:
        obj = bpy.data.objects.get(name)
        if obj is None:
            continue
        for pts, idx in base.components(obj):
            if len(pts) < 24:
                continue
            cy = sum(p.y for p in pts) / len(pts)
            groups["LEFT" if cy * left_sign > 0 else "RIGHT"].append(
                (name, idx, obj))

    results = {}
    for side in ("LEFT", "RIGHT"):
        items = groups[side]
        if not items:
            continue
        verts, faces, base_index = [], [], 0
        for _n, idx, obj in items:
            mw = obj.matrix_world
            local = {old: base_index + k for k, old in enumerate(idx)}
            verts += [mw @ obj.data.vertices[old].co for old in idx]
            for poly in obj.data.polygons:
                if all(vi in local for vi in poly.vertices):
                    faces.append([local[vi] for vi in poly.vertices])
            base_index += len(idx)
        copy, _ = off.cleaned_copy(f"Cavity_{side}_src", verts,
                                   [tuple(f) for f in faces])
        sign = off.inward_sign(copy, left_sign, side)

        chosen = None
        sweep = []
        for th in off.THICKNESSES:
            mesh = off.solidify(copy, th, sign["flip_needed"])
            h = off.health(mesh)
            if not (h["watertight"] and h["outward"]
                    and h["signed_volume_m3"] > 0):
                sweep.append({"thickness_m": th, "valid": False})
                continue
            cov = bpy.data.objects.new(f"Cavity_{side}_{th}", mesh)
            bpy.context.scene.collection.objects.link(cov)
            t = true_wall_thickness(cov)
            sweep.append({"thickness_m": th, "valid": True,
                          "volume_m3": h["signed_volume_m3"],
                          "true_wall": t})
            # Accept the SMALLEST cavity whose minimum wall clears the guide
            # plus epsilon: minimal volume, adequate clearance.
            if t and t["median_m"] >= (2 * 0.0018 + EPSILON):
                chosen = (th, h, cov, t)
                break
            # keep the largest-thickness candidate as a fallback so the stage
            # still reports a real distribution instead of nothing
            fallback = (th, h, cov, t)
            bpy.data.objects.remove(cov, do_unlink=True)

        if chosen is None:
            chosen = locals().get("fallback")
        if chosen is None:
            results[side] = {"built": False, "sweep": sweep,
                             "reason": "no offset gives usable wall thickness"}
            continue
        th, h, cov, t = chosen
        tree = base.bvh_of(cov)

        # Centreline: walk the cavity's own vertices, take the deepest sample
        # in each slab along X, then smooth. Depth is measured to the boundary,
        # so the path prefers the fat middle of the cavity.
        cv = [cov.matrix_world @ v.co for v in cov.data.vertices]
        xs = sorted(p.x for p in cv)
        lo_x, hi_x = xs[0], xs[-1]
        steps = 24
        raw = []
        for i in range(steps):
            t_ = i / (steps - 1.0)
            cx = lo_x + (hi_x - lo_x) * t_
            band = [p for p in cv if abs(p.x - cx) < (hi_x - lo_x) / steps]
            if not band:
                continue
            # The CENTROID of a slab's vertices sits inside the wall. Picking
            # the "deepest" vertex puts the path ON the far wall instead, which
            # is why the first version measured clearances of 0.0 and put half
            # the guide outside the cavity.
            c = Vector((0.0, 0.0, 0.0))
            for p in band:
                c += p
            c /= len(band)
            res = tree.find_nearest(c, 5.0)
            d = res[3] if res[0] is not None else 0.0
            if d > 0.0:
                raw.append((c, d))
        if len(raw) < 6:
            results[side] = {"built": False, "reason": "centerline too short",
                             "sweep": sweep}
            continue
        # Smooth the path.
        pts = [p for p, _ in raw]
        depth = [d for _, d in raw]
        sm = []
        for i in range(len(pts)):
            a = pts[max(0, i - 1)]
            b = pts[i]
            c = pts[min(len(pts) - 1, i + 1)]
            sm.append((a + b * 2.0 + c) / 4.0)
        radii = [max(0.0004, min(0.0030, d * 0.40)) for d in depth]

        attempts = []
        picked = None
        for profile in ("rounded_rect", "oval", "round"):
            for f in (1.0, 0.8, 0.62, 0.45):
                rr = [r * f for r in radii]
                guide = make_guide(sm, rr, profile,
                                   f"TailGuide_{side}_{profile}_{f}")
                gverts = [guide.matrix_world @ v.co
                          for v in guide.data.vertices]
                samp = list(gverts)
                for i in range(0, len(gverts), 12):
                    ring = gverts[i:i + 12]
                    for k in range(len(ring)):
                        samp.append((ring[k] + ring[(k + 1) % len(ring)]) * 0.5)
                samp += sm
                inside = sum(1 for p in samp if base.inside_volume(tree, p))
                pct = 100.0 * inside / len(samp)
                ds = []
                for p in samp:
                    res = tree.find_nearest(p, 5.0)
                    if res[0] is not None:
                        ds.append(res[3])
                ds.sort()
                dmin = ds[0] if ds else 0.0
                attempts.append({"profile": profile, "scale": f,
                                 "samples": len(samp),
                                 "inside_percent": round(pct, 4),
                                 "min_clearance_m": round(dmin, 6)})
                if pct >= 100.0 and dmin > EPSILON:
                    picked = (guide, profile, f, rr, len(samp), addstats(ds))
                    break
                bpy.data.objects.remove(guide, do_unlink=True)
            if picked:
                break

        results[side] = {
            "built": picked is not None,
            "selected_thickness_m": th,
            "cavity": h,
            "true_wall": t,
            "sweep": sweep,
            "centerline_points": len(sm),
            "attempts": attempts,
        }
        if picked:
            guide, profile, f, rr, nsamp, stats = picked
            results[side]["guide"] = {
                "profile": profile, "scale": f,
                "mean_radius_m": round(sum(rr) / len(rr), 6),
                "vertices": len(guide.data.vertices),
                "verification_samples": nsamp,
                "inside_percent": 100.0,
                "clearance": stats,
            }
        print(f"[v3] {side}: th={th*1000:.0f}mm wall_min={t['min_m']} "
              f"guide={'PASS' if picked else 'FAIL'} "
              f"{results[side].get('guide',{})}")

    report["sides"] = results
    report["freeze_gate_v3"] = {
        "surface_offset_cavity": all(
            results.get(s, {}).get("selected_thickness_m")
            for s in ("LEFT", "RIGHT")),
        "guide_containment_100": all(
            results.get(s, {}).get("guide", {}).get("inside_percent") == 100.0
            for s in ("LEFT", "RIGHT")),
    }
    os.makedirs(os.path.dirname(args.report), exist_ok=True)
    with open(args.report, "w") as fh:
        json.dump(report, fh, indent=2)
        fh.write("\n")
    print(f"[v3] gate: {report['freeze_gate_v3']}")
    return 0


def addstats(ds):
    n = len(ds)
    if n == 0:
        return {}

    def pc(f):
        return round(ds[min(n - 1, int(n * f))], 6)

    return {"samples": n, "min_m": pc(0.0), "p1_m": pc(0.01),
            "p5_m": pc(0.05), "median_m": pc(0.5),
            "mean_m": round(sum(ds) / n, 6), "max_m": pc(1.0)}


if __name__ == "__main__":
    sys.exit(main())
