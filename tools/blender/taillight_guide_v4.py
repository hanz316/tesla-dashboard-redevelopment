#!/usr/bin/env python3
"""Taillight guide v4: medial centreline, per-segment guide, then the gates.

Why this stage exists
---------------------
v3 placed the guide along the midpoint of a ray's near/far wall pair. That
midpoint is *a* point between two walls, not the medial axis of the cavity, and
on a curved lens shell it can sit within microns of a wall while still being
technically inside the volume. v3 also clamped each ring radius by the *centre*
clearance, so shrinking the guide could not fix a centreline that was already
too close to a wall - which is exactly why the reported minimum clearance did
not move across guide scales 1.0 / 0.8 / 0.62 / 0.45.

v3 also treated one side of the car as one continuous lamp. It is not: each
side is three separate shells (outer lamp, inboard lamp, brake light) that
overlap in x but sit at different y. A single continuous guide cannot span the
gap between them, so the pipeline is segmented by source component, which is
the geometry's own definition of an optical segment.

This stage therefore:

* segments per side by source component and solves each segment separately;
* measures the unrefined and the refined centreline through the SAME radius
  solver and the SAME verification, so "the limiting sample is a centreline
  point" is a measurement rather than a hypothesis;
* refines the centreline by bounded, deterministic medial relaxation inside the
  slab plane;
* solves each ring's admissible radius on the actual ring vertices and rejects
  a ring when no admissible radius exists, instead of forcing one;
* gates on coverage and on self-intersection, so a short fragment or a
  collapsed cavity cannot be reported as a production PASS;
* searches cavity offsets from smallest upwards and takes the first that passes.

Usage:
    blender -b --factory-startup -P tools/blender/taillight_guide_v4.py -- \
        --report assets/checkpoints/taillight_final/taillight_candidate_search_v4.json
"""

import argparse
import json
import math
import os
import sys

try:
    import bpy
    from mathutils import Vector
except ImportError:  # pragma: no cover
    sys.exit("Run inside Blender")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import render_vehicle_visual_v2 as vehicle_v2  # noqa: E402
import taillight_finalize as base  # noqa: E402
import taillight_guide_v3 as v3  # noqa: E402
import taillight_medial as medial  # noqa: E402
import taillight_offset as off  # noqa: E402

EPSILON = v3.EPSILON            # 1.5 mm production guide-surface clearance gate
MIN_R = 0.00035                 # thinnest guide the geometry may be asked to use
R_MAX = 0.0030                  # thickest, so a wide cavity cannot balloon it
MIN_USABLE_WALL = 2.0 * MIN_R + 2.0 * EPSILON   # 3.7 mm: ring + gap, both sides
# A slab counts as able to host a guide when a minimum-radius ring fits with
# the production clearance AND a stated margin. Without the margin a slab is
# "usable" only at exactly the gate, so the tube's chords - which always dip a
# little between rings - make it unbuildable, and the coverage gate would then
# be measuring the margin rather than the lamp.
FIT_MARGIN_M = 0.00025
MIN_USABLE_CLEARANCE = MIN_R + EPSILON + FIT_MARGIN_M   # 2.10 mm
COVERAGE_MIN_RATIO = 0.80
COLLAPSE_MIN_WALL_RATIO = 0.90   # median wall must track the offset this closely
# A fold this close to the guide means the wall beside the guide is not a clean
# single surface, so its clearance number cannot be trusted. Folds further away
# - the guaranteed rim overshoot at the shell boundary - are reported as
# evidence at SELFINT_REPORT_RADIUS_M instead of failing the offset, because the
# guide's own clearance gate already covers everything it can touch.
NEAR_GUIDE_SELFINT_RADIUS_M = 0.001
SELFINT_REPORT_RADIUS_M = 0.003
FIT_MAX_ITERATIONS = 12
MAX_RING_GAP_FACTOR = 1.5        # in slab spacings; longer gaps split the guide
MAX_RING_STEP_M = 0.0025         # densify so no chord spans more than this
OFFSET_CANDIDATES_M = [0.002, 0.003, 0.004, 0.005, 0.006, 0.0065, 0.007,
                       0.008, 0.010, 0.012]
RING_SEGMENTS = 12
MIN_COMPONENT_VERTS = 24
PROFILES = ("rounded_rect", "oval", "round")
SCALES = (1.0, 0.8, 0.62, 0.45)
# Left and right pieces of one physical lamp share an offset (see main()).
PAIR_KEYS = {"rear_lights": "outer",
             "rear_lightsl": "quarter",
             "rear_lightsr": "quarter",
             "light_breake": "brake"}


def parse_args():
    argv = sys.argv
    argv = argv[argv.index("--") + 1:]
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", default=vehicle_v2.DEFAULT_INPUT)
    ap.add_argument("--report", required=True)
    ap.add_argument("--debug-dir", default=None,
                    help="directory for per-segment centreline diagnostics")
    ap.add_argument("--offsets", default=",".join(str(o)
                                                  for o in OFFSET_CANDIDATES_M))
    ap.add_argument("--refine", default="on", choices=["on", "off"])
    ap.add_argument("--only", default=None,
                    help="restrict to one segment, e.g. LEFT:light_breake:0")
    ap.add_argument("--full-report", action="store_true",
                    help="keep every offset's full diagnostics (large)")
    return ap.parse_args(argv)


def component_sources(left_sign):
    """One source soup per (side, lamp, connected component)."""
    out = []
    for name in off.LAMPS:
        obj = bpy.data.objects.get(name)
        if obj is None:
            continue
        mw = obj.matrix_world
        for k, (pts, idx) in enumerate(base.components(obj)):
            if len(pts) < MIN_COMPONENT_VERTS:
                continue
            cy = sum(p.y for p in pts) / len(pts)
            side = "LEFT" if cy * left_sign > 0 else "RIGHT"
            local = {old: i for i, old in enumerate(idx)}
            mw3 = mw.to_3x3()
            verts = [mw @ obj.data.vertices[old].co for old in idx]
            normals = [mw3 @ obj.data.vertex_normals[old].vector for old in idx]
            faces = [tuple(local[vi] for vi in poly.vertices)
                     for poly in obj.data.polygons
                     if all(vi in local for vi in poly.vertices)]
            xs = [p.x for p in verts]
            out.append({"side": side, "lamp": name, "component": k,
                        "verts": verts, "normals": normals, "faces": faces,
                        "x_span_m": round(max(xs) - min(xs), 5),
                        "vertices": len(verts), "faces_count": len(faces)})
    return out


def longest_run(indices):
    runs, cur = [], []
    for i in indices:
        if cur and i == cur[-1] + 1:
            cur.append(i)
            continue
        if len(cur) > len(runs):
            runs = cur
        cur = [i]
    if len(cur) > len(runs):
        runs = cur
    return runs


def refine_path(tree, seeds, offset, inside_test, enable):
    """Medial relaxation per slab, with a full before/after record."""
    points, depth, trace = [], [], []
    for s in seeds:
        rec = {"slab_index": s["index"],
               "initial_position": [round(c, 7) for c in s["point"]],
               "initial_clearance_m": round(s["clearance"], 7)}
        if enable:
            r = medial.medial_refine(tree, s["point"], offset, inside_test)
            rec.update({"refined_position": [round(c, 7) for c in r["point"]],
                        "refined_clearance_m": round(r["clearance"], 7),
                        "displacement_m": round(r["displacement"], 7),
                        "iterations": r["iterations"],
                        "accepted_moves": r["accepted_moves"],
                        "termination": r["termination"]})
            points.append(r["point"])
        else:
            rec.update({"refined_position": [round(c, 7) for c in s["point"]],
                        "refined_clearance_m": round(s["clearance"], 7),
                        "displacement_m": 0.0, "iterations": 0,
                        "accepted_moves": 0, "termination": "refinement off"})
            points.append(Vector(s["point"]))
        depth.append(s["width"] * 0.5)
        trace.append(rec)
    return points, depth, trace


def smooth_preserving_clearance(tree, points, inside_test, offset, log,
                                enable=True, passes=6, keep_ratio=0.90):
    """Smooth the path only where smoothing does not cost clearance.

    Priority is clearance > containment > smoothness, but smoothness is not
    cosmetic: a path that kinks turns each ring frame against its neighbour and
    the tube's chords then graze walls that every ring centre clears. So this
    runs several guarded passes - a moved point is kept only when it stays
    inside the cavity and retains keep_ratio of its previous clearance.
    """
    out = list(points)
    if not enable:
        log.append({"passes": 0, "note": "refinement off"})
        return out
    for p_i in range(passes):
        nxt, moves = [], 0
        for i, p in enumerate(out):
            a = out[max(0, i - 1)]
            b = out[i]
            c = out[min(len(out) - 1, i + 1)]
            cand = (a + b * 2.0 + c) / 4.0
            base_c = medial.clearance(tree, p)
            bar = max(MIN_R + EPSILON, keep_ratio * base_c)
            chosen, decision = p, "kept original"
            if inside_test(cand):
                cc = medial.clearance(tree, cand)
                if cc >= bar:
                    chosen, decision = cand, "smoothed"
                else:
                    r = medial.medial_refine(tree, cand, offset, inside_test)
                    if r["clearance"] >= bar:
                        chosen, decision = r["point"], "smoothed then re-relaxed"
            if decision != "kept original":
                moves += 1
            if p_i == 0:
                log.append({"index": i,
                            "base_clearance_m": round(base_c, 7),
                            "smoothed_clearance_m":
                                round(medial.clearance(tree, cand), 7),
                            "decision": decision,
                            "final_clearance_m":
                                round(medial.clearance(tree, chosen), 7)})
            nxt.append(chosen)
        out = nxt
        log.append({"pass": p_i + 1, "moved_points": moves,
                    "points": len(out)})
    return out


def split_runs(points, max_gap_x):
    """Split a centreline where consecutive points are too far apart in x.

    A seed list can skip slabs - either because a slab produced no valid
    interior interval or because the cavity is absent there. Bridging such a
    gap with one ring-to-ring chord produces a straight tube across a curving
    lamp, so a gap wider than a couple of slabs starts a new optical segment.
    Both the coverage metric and the geometry then see the same segmentation.
    """
    runs, cur = [], [0]
    for i in range(1, len(points)):
        if abs(points[i].x - points[i - 1].x) > max_gap_x:
            runs.append(cur)
            cur = []
        cur.append(i)
    runs.append(cur)
    return runs


def densify_path(tree, points, inside_test, offset, max_step_m):
    """Subdivide the path and pull each new point onto the local medial axis.

    A ring pair five millimetres apart spans a chord that cuts across a curving
    lamp, and the tube's chords then graze walls that both ring centres clear.
    Inserting a point on the chord alone would change nothing - the polyline is
    the same. So each inserted point is relaxed toward the local medial axis,
    which makes the path follow the cavity instead of approximating it.
    Insertion is skipped where the chord is already outside the cavity; the
    run splitting handles those gaps.
    """
    out = [points[0]]
    inserted, relaxed = 0, 0
    for i in range(len(points) - 1):
        a, b = points[i], points[i + 1]
        seg = b - a
        if seg.length < 1e-9:
            out.append(b)
            continue
        k = max(1, int(math.ceil(seg.length / max_step_m)))
        for j in range(1, k):
            cand = a + seg * (j / float(k))
            if not inside_test(cand):
                continue
            r = medial.medial_refine(tree, cand, offset, inside_test)
            if r["clearance"] > medial.clearance(tree, cand):
                out.append(r["point"])
                relaxed += 1
            else:
                out.append(cand)
            inserted += 1
        out.append(b)
    return out, {"inserted": inserted, "relaxed": relaxed,
                 "max_step_m": max_step_m, "final_points": len(out)}


def place_guide_run(tree, pts, r0s, profile, scale, inside_test, name,
                    global_indices, cov=None):
    """Fit a guide for every usable stretch of one path run.

    Each ring starts from its own admissible radius (every ring vertex clear).
    That is not sufficient on its own: the straight chord between two rings can
    graze a wall while both rings are clear, and a curved lamp produces exactly
    that. So the built mesh is measured, the limiting sample is attributed, and
    the rings responsible are shrunk; a ring that would have to go below the
    minimum radius is dropped instead, which is how insufficient space rejects
    geometry rather than forcing it.

    Dropping a ring splits the path, and every surviving stretch is built - not
    just the longest one. Keeping only the longest run threw away 42 healthy
    rings (seven slabs of lamp) because one ring in the middle had to go.
    """
    radii, ring_trace = [], []
    bases = medial.ring_bases(pts)
    turns = [math.degrees(bases[k][0].angle(bases[k + 1][0]))
             for k in range(len(bases) - 1)]
    for i, r0 in enumerate(r0s):
        r_cap = min(R_MAX, r0 * scale)
        r, tr = medial.admissible_radius(tree, pts, i, r_cap, profile,
                                         EPSILON, MIN_R, inside_test, bases)
        radii.append(r)
        ring_trace.append({"ring": i, "radius_cap_m": round(r_cap, 7),
                           "admissible_radius_m": None if r is None
                           else round(r, 7), "iterations": tr})
    fit_log = []
    guides, kept_pts_all, kept_runs_all = [], [], []
    for iteration in range(FIT_MAX_ITERATIONS):
        usable = [i for i, r in enumerate(radii) if r is not None]
        stretches = [r for r in _contiguous_runs(usable) if len(r) >= 4]
        if not stretches:
            return None, {"rejected": "fewer than four rings can hold a guide",
                          "usable_rings": len(usable), "longest_run": 0,
                          "path_points": len(pts), "ring_trace": ring_trace,
                          "fit_log": fit_log}
        built, changed, log_row = [], False, {"iteration": iteration,
                                              "stretches": len(stretches)}
        worst_inside, worst_clear = 100.0, None
        for stretch_i, run in enumerate(stretches):
            kept_pts = [pts[i] for i in run]
            kept_r = [radii[i] for i in run]
            kept_global = [global_indices[i] for i in run]
            guide = medial.build_guide(kept_pts, kept_r, profile,
                                       f"{name}_s{stretch_i}")
            records = medial.guide_sample_records(guide, kept_pts,
                                                  RING_SEGMENTS)
            ev = medial.evaluate_samples(tree, records, inside_test)
            ok = (ev["inside_percent"] >= 100.0
                  and ev["min_clearance_m"] > EPSILON)
            worst_inside = min(worst_inside, ev["inside_percent"])
            worst_clear = ev["min_clearance_m"] if worst_clear is None else \
                min(worst_clear, ev["min_clearance_m"])
            if ok:
                built.append((guide, kept_pts, kept_r, run, kept_global, ev))
                continue
            bpy.data.objects.remove(guide, do_unlink=True)
            lim = ev["limiting_sample"]
            local = lim["ring"] if lim else 0
            if lim is None:
                targets = list(run)
            elif lim["kind"] == "GUIDE_LENGTH_SAMPLE":
                targets = [run[local], run[min(local + 1, len(run) - 1)]]
            elif lim["kind"] in ("GUIDE_RING_VERTEX",
                                 "GUIDE_RING_EDGE_MIDPOINT"):
                targets = [run[local]]
            else:  # CENTERLINE: the path is too close, shrinking cannot help
                targets = [run[local]]
            for t in targets:
                if radii[t] is None:
                    continue
                shrunk = radii[t] * 0.7
                radii[t] = None if shrunk < MIN_R else shrunk
                changed = True
        log_row.update({"stretches_built": len(built),
                        "stretch_count": len(stretches),
                        "worst_inside_percent": round(worst_inside, 4),
                        "worst_min_clearance_m": None if worst_clear is None
                        else round(worst_clear, 7),
                        "accepted": len(built) == len(stretches)})
        fit_log.append(log_row)
        if len(built) == len(stretches):
            radii_all, evs, kept_global_all = [], [], []
            for guide, kept_pts, kept_r, run, kept_global, ev in built:
                guides.append(guide)
                kept_pts_all.extend(kept_pts)
                kept_runs_all.append(run)
                radii_all.extend(kept_r)
                evs.append(ev)
                kept_global_all.extend(kept_global)
            result = {"rings_built": len(radii_all),
                      "path_points": len(pts),
                      "rings_rejected": len(radii) - len(usable),
                      "stretches_built": len(built),
                      "vertices": sum(len(g.data.vertices) for g, *_ in built),
                      "mean_radius_m": round(sum(radii_all) / len(radii_all), 7),
                      "min_radius_m": round(min(radii_all), 7),
                      "max_radius_m": round(max(radii_all), 7),
                      "x_span_m": round(max(p.x for p in kept_pts_all)
                                        - min(p.x for p in kept_pts_all), 7),
                      "kept_slab_indices": kept_global_all,
                      "max_ring_basis_turn_deg": round(max(turns), 3)
                      if turns else 0.0,
                      "containment": {
                          "samples": sum(e["samples"] for e in evs),
                          "inside_percent": round(worst_inside, 4),
                          "min_clearance_m": round(worst_clear, 7),
                          "limiting_sample": min(
                              (e for e in evs if e["limiting_sample"]),
                              key=lambda e: e["min_clearance_m"]
                          )["limiting_sample"] if evs else None},
                      "pass": True, "ring_trace": ring_trace,
                      "fit_log": fit_log}
            return ((guides, kept_pts_all, kept_runs_all, result), result)
        for guide, *_ in built:
            bpy.data.objects.remove(guide, do_unlink=True)
        if not changed:
            break
    return None, {"rejected": "no radius set satisfies the clearance gate",
                  "path_points": len(pts), "ring_trace": ring_trace,
                  "fit_log": fit_log}


def _contiguous_runs(indices):
    """All contiguous runs in a list of indices, not only the longest."""
    runs, cur = [], []
    for i in indices:
        if cur and i == cur[-1] + 1:
            cur.append(i)
            continue
        if cur:
            runs.append(cur)
        cur = [i]
    if cur:
        runs.append(cur)
    return runs


def place_guide(tree, points, r0_list, profile, scale, inside_test, name,
                usable_slabs, slab_spacing, seed_x, cov=None):
    """One guide per contiguous run; a segment passes only if all runs pass."""
    max_gap_x = MAX_RING_GAP_FACTOR * slab_spacing
    runs = split_runs(points, max_gap_x)
    results, guides, kept_pts_all, kept_runs = [], [], [], []
    for ri, run in enumerate(runs):
        if len(run) < 4:
            results.append({"run": ri, "path_indices": run,
                            "path_points": len(run),
                            "rejected": "fewer than four centreline points "
                                        "in this run"})
            continue
        pts = [points[i] for i in run]
        r0s = [r0_list[i] for i in run]
        # Path points can outnumber seeds once the path is densified, so the
        # slab each ring belongs to is resolved by nearest seed x rather than
        # by index.
        gidx = [min(range(len(seed_x)),
                    key=lambda s: abs(seed_x[s] - p.x)) for p in pts]
        built, res = place_guide_run(tree, pts, r0s, profile, scale,
                                     inside_test, f"{name}_run{ri}", gidx, cov)
        res["run"] = ri
        res["path_indices"] = run
        if built is not None:
            run_guides, kept_pts, kept_runs_local, _ = built
            res["kept_local_indices"] = [
                i for stretch in kept_runs_local for i in stretch]
            guides.extend(run_guides)
            kept_pts_all.extend(kept_pts)
            kept_runs.append(kept_runs_local)
        results.append(res)

    retained_x = sorted(p.x for p in kept_pts_all)
    coverage = medial.slab_coverage(retained_x, usable_slabs, slab_spacing,
                                    COVERAGE_MIN_RATIO)
    coverage["segment_x_span_m"] = round(
        slab_spacing * (len(usable_slabs) or 1), 7)
    coverage["runs"] = len(runs)
    built = [r for r in results if "containment" in r]
    unbuildable = [r for r in results if "containment" not in r]
    # A run that cannot host a guide is an exclusion with a measured reason,
    # not a segment failure: its slabs are still in the coverage denominator,
    # so losing real lamp length to it shows up as a coverage failure. The
    # segment fails when a run that WAS built fails containment or clearance,
    # or when coverage is short.
    all_pass = (coverage["pass"] and built
                and all(r.get("pass") for r in built))
    out = {"profile": profile, "scale": scale, "runs": results,
           "run_count": len(runs), "runs_built": len(built),
           "runs_unbuildable": len(unbuildable),
           "unbuildable_reasons": [
               {"run": r["run"], "path_points": r.get("path_points"),
                "reason": r.get("rejected"),
                "usable_rings": r.get("usable_rings"),
                "clearest_ring_radius_m": r.get("min_radius_m")}
               for r in unbuildable],
           "coverage": coverage, "pass": bool(all_pass)}
    if all_pass:
        return (guides, kept_pts_all, kept_runs, out), out
    for g in guides:
        bpy.data.objects.remove(g, do_unlink=True)
    return None, out


def evaluate_offset(sign, copy, thickness, refine, inside_factory,
                    source_verts, source_normals, label=""):
    """Cavity -> centreline -> guide for one segment at one offset."""
    mesh = off.solidify(copy, thickness, sign["flip_needed"])
    health = off.health(mesh)
    row = {"thickness_m": thickness, "cavity": health}
    if not (health["watertight"] and health["outward"]
            and health["signed_volume_m3"] > 0):
        row["rejected"] = "cavity is not a valid closed manifold"
        return None, row
    cov = bpy.data.objects.new(
        f"Cavity_{label}_{thickness * 1000.0:.1f}mm" if label
        else f"Cavity_{thickness}", mesh)
    bpy.context.scene.collection.objects.link(cov)
    tree = base.bvh_of(cov)
    inside_test = inside_factory(tree)
    row["self_intersection"] = medial.self_intersections(cov)
    row["true_wall"] = v3.true_wall_thickness(cov)
    wall_median = (row["true_wall"] or {}).get("median_m") or 0.0
    row["wall_to_offset_ratio"] = round(wall_median / thickness, 4) \
        if thickness else 0.0
    if row["wall_to_offset_ratio"] < COLLAPSE_MIN_WALL_RATIO:
        row["rejected"] = ("inward offset collapsed: median wall %.2f mm is "
                           "far below the %.0f mm offset"
                           % (wall_median * 1000.0, thickness * 1000.0))
        return cov, row
    x = [p.x for p in (cov.matrix_world @ v.co for v in cov.data.vertices)]
    span = max(x) - min(x)

    seeds, qa, slabs = medial.slab_seeds(
        tree, cov, thickness, inside_test,
        source={"verts": source_verts, "normals": source_normals})
    row["centreline_qa"] = qa
    if not seeds:
        row["rejected"] = "no slab produced a parity-confirmed interior interval"
        return cov, row
    points, depth, trace = refine_path(tree, seeds, thickness, inside_test,
                                       refine)
    smooth_log = []
    points = smooth_preserving_clearance(tree, points, inside_test, thickness,
                                         smooth_log, enable=refine)
    densify_log = {}
    if refine:
        points, densify_log = densify_path(tree, points, inside_test,
                                           thickness, MAX_RING_STEP_M)
        points = smooth_preserving_clearance(tree, points, inside_test,
                                             thickness, smooth_log,
                                             enable=True, passes=1)
    point_clearance = [medial.clearance(tree, p) for p in points]
    row["centreline_clearance"] = medial.clearance_stats(point_clearance)
    row["centreline_refinement"] = {
        "before": medial.clearance_stats([s["clearance"] for s in seeds]),
        "after": medial.clearance_stats(point_clearance),
        "trace": trace, "smoothing": smooth_log, "densify": densify_log}
    usable_x, usable_span = medial.usable_spans(slabs, MIN_USABLE_CLEARANCE)
    row["usable_slabs"] = len(usable_x)
    row["usable_x_span_m"] = round(usable_span, 7)
    row["slabs"] = slabs
    if usable_span <= 0.0:
        row["rejected"] = ("no slab has a thick enough interior interval for a "
                           "guide ring plus clearance")
        return cov, row

    # Radius prior from each point's own measured clearance: for a mid-wall
    # point that is half the local thickness, which is exactly the quantity the
    # ring must fit into.
    # No floor here: a floor on the radius is how the old code forced geometry
    # into space that could not hold it. admissible_radius rejects instead.
    r0_list = [min(R_MAX, 0.40 * c) for c in point_clearance]
    slab_spacing = span / (medial.SLAB_COUNT - 1.0) if span > 0 else 0.0
    seed_x = [s["slab_x"] for s in seeds]
    attempts, picked = [], None
    for profile in PROFILES:
        for scale in SCALES:
            built, res = place_guide(tree, points, r0_list, profile, scale,
                                     inside_test,
                                     f"TailGuide_{label}_"
                                     f"{thickness * 1000.0:.1f}mm_"
                                     f"{profile}_{scale}",
                                     usable_x, slab_spacing, seed_x, cov)
            if built is not None:
                guides, kept_points, kept_runs, res = built
                attempts.append(res)
                picked = (guides, kept_points, kept_runs, res)
                break
            else:
                attempts.append(res)
        if picked:
            break
    row["attempts"] = attempts
    if picked:
        row["selected"] = True
        row["guide"] = picked[3]
        guide_points = picked[1]
        si = medial.self_intersections(cov, guide_points,
                                       NEAR_GUIDE_SELFINT_RADIUS_M)
        row["self_intersection_near_guide"] = si
        row["self_intersection_near_guide_evidence"] = \
            medial.self_intersections(cov, guide_points,
                                      SELFINT_REPORT_RADIUS_M)
        if si["near_guide_pairs"]:
            for g in picked[0]:
                bpy.data.objects.remove(g, do_unlink=True)
            row["selected"] = False
            row["rejected"] = ("cavity self-intersects within %.1f mm of the "
                               "guide: %d face pairs"
                               % (NEAR_GUIDE_SELFINT_RADIUS_M * 1000.0,
                                  si["near_guide_pairs"]))
            del row["guide"]
    else:
        best = None
        for a in attempts:
            summary = summarize_attempt(a)
            if summary["worst_containment_percent"] is None:
                continue
            key = (summary["worst_containment_percent"],
                   summary["coverage"]["coverage_ratio_of_usable"],
                   summary["worst_min_clearance_m"])
            if best is None or key > best[0]:
                best = (key, summary)
        if best is not None:
            row["best_failed_attempt"] = best[1]
    return cov, row


def summarize_attempt(attempt):
    """Flatten one segment-level attempt into the numbers a gate cares about."""
    runs = attempt.get("runs", [])
    containment = [r["containment"]["inside_percent"] for r in runs
                   if "containment" in r]
    clearance = [r["containment"]["min_clearance_m"] for r in runs
                 if "containment" in r]
    return {"profile": attempt.get("profile"), "scale": attempt.get("scale"),
            "coverage": attempt.get("coverage"),
            "run_count": attempt.get("run_count"),
            "runs_built": len(containment),
            "worst_containment_percent": min(containment) if containment
            else None,
            "worst_min_clearance_m": min(clearance) if clearance else None,
            "rejected_runs": [{"run": r.get("run"),
                               "rejected": r.get("rejected"),
                               "usable_rings": r.get("usable_rings"),
                               "path_points": r.get("path_points")}
                              for r in runs if "containment" not in r]}


def evaluate_segment(comp, offsets, refine, debug_dir, only):
    label = f"{comp['side']}:{comp['lamp']}:{comp['component']}"
    if only and label != only:
        return None
    entry = {"side": comp["side"], "lamp": comp["lamp"],
             "component": comp["component"], "label": label,
             "source_vertices": comp["vertices"],
             "source_faces": comp["faces_count"],
             "x_span_m": comp["x_span_m"], "offsets": []}
    copy, cleanup = off.cleaned_copy(f"CavitySrc_{label}", comp["verts"],
                                     [tuple(f) for f in comp["faces"]])
    consistency, flipped = off.normals_consistent(copy.data)
    sign = off.inward_sign(copy, 1.0, comp["side"])
    entry["cleanup"] = cleanup
    entry["normal_consistency"] = consistency
    entry["flipped_faces"] = flipped
    entry["inward"] = sign

    def inside_factory(tree):
        return lambda p: base.inside_volume(tree, p)

    selected = None
    for th in offsets:
        cov, row = evaluate_offset(sign, copy, th, refine, inside_factory,
                                   comp["verts"], comp["normals"], label)
        entry["offsets"].append(row)
        if debug_dir and cov is not None and "slabs" in row:
            os.makedirs(debug_dir, exist_ok=True)
            path = os.path.join(
                debug_dir,
                f"centerline_debug_{label.replace(':', '_')}_"
                f"{int(th * 1000)}mm.json".lower())
            with open(path, "w") as fh:
                json.dump({"side": comp["side"], "segment": label,
                           "offset_m": th, "slabs": row["slabs"],
                           "centreline_refinement":
                               row["centreline_refinement"],
                           "attempts": row.get("attempts"),
                           "rejected": row.get("rejected")}, fh, indent=2)
                fh.write("\n")
        # Keep going after a pass: the other side of the same lamp may need a
        # different offset, and both sides are required to end up on one
        # common offset so the pair stays symmetric.
        if row.get("selected") and selected is None:
            selected = row
        if cov is not None:
            if not row.get("selected"):
                bpy.data.objects.remove(cov, do_unlink=True)
    if selected:
        apply_row(entry, selected)
    else:
        entry["selected_thickness_m"] = None
        # A segment that cannot host a guide at any offset is excluded by
        # geometry, and the exclusion has to carry its own measurement.
        spans = [row.get("usable_x_span_m") or 0.0
                 for row in entry["offsets"]]
        walls = [row["true_wall"]["median_m"] for row in entry["offsets"]
                 if row.get("true_wall")]
        entry["excluded_by_geometry"] = bool(walls) and not any(spans)
        entry["evidence"] = {
            "max_usable_x_span_m": round(max(spans) if spans else 0.0, 7),
            "median_wall_by_offset_m": walls,
            "usable_slabs_by_offset": [row.get("usable_slabs")
                                       for row in entry["offsets"]],
        }
    entry["passed"] = selected is not None
    if selected:
        entry["summary"] = summarize_attempt(selected["guide"])
    return entry


def apply_row(entry, row):
    """Adopt one offset's result as the segment's selected result."""
    entry["selected_thickness_m"] = row["thickness_m"]
    for key in ("cavity", "self_intersection", "true_wall", "guide",
                "centreline_clearance", "centreline_refinement",
                "centreline_qa", "usable_slabs", "usable_x_span_m",
                "self_intersection_near_guide",
                "self_intersection_near_guide_evidence"):
        if key in row:
            entry[key] = row[key]
    entry["passed"] = True
    entry["summary"] = summarize_attempt(row["guide"])


def row_at(entry, target):
    for row in entry["offsets"]:
        if abs(row["thickness_m"] - target) < 1e-9 and row.get("selected"):
            return row
    return None


def pair_offsets(segments):
    """Both sides of one physical lamp must end up on one cavity offset.

    The left and right lamps are mirror images, so a different offset per side
    would give the two lamps a different wall separation and read as an
    asymmetry on the car. Where both sides pass at a common offset, the larger
    of the two selections is adopted for both.
    """
    pairs = {}
    for s in segments:
        pairs.setdefault(PAIR_KEYS.get(s["lamp"], s["lamp"]), []).append(s)
    for key, group in pairs.items():
        if len(group) != 2 or not all(s["passed"] for s in group):
            continue
        offsets_sel = [s["selected_thickness_m"] for s in group]
        if offsets_sel[0] == offsets_sel[1]:
            for s in group:
                s["pair_offset_m"] = offsets_sel[0]
            continue
        target = max(offsets_sel)
        rows = [(s, row_at(s, target)) for s in group]
        if all(r is not None for _s, r in rows):
            for s, r in rows:
                apply_row(s, r)
                s["pair_offset_m"] = target
                s["pair_offset_note"] = (
                    "raised to the common pair offset %d mm so both sides of "
                    "the %s lamp match" % (target * 1000.0, key))
        else:
            for s in group:
                s["pair_offset_m"] = None
                s["pair_offset_note"] = (
                    "no common offset passes on both sides; per-side offsets "
                    "kept (%s) and the asymmetry is recorded"
                    % ", ".join("%d mm" % (o * 1000.0) for o in offsets_sel))
    return segments


def discard_unselected(entry):
    """Keep only the winning offset's cavity and the winning attempt's guides.

    Every offset is evaluated so the pair rule can see all of them, which
    leaves several cavities and many candidate guides in the scene. The
    production master must contain exactly one cavity and one guide set per
    optical segment, so the losers are removed here.
    """
    label = entry["label"]
    keep_mm = entry.get("selected_thickness_m")
    guide = entry.get("guide") or {}
    keep_tag = None
    if (keep_mm is not None and guide.get("profile")
            and guide.get("scale") is not None):
        keep_tag = (f"_{keep_mm * 1000.0:.1f}mm_"
                    f"{guide['profile']}_{guide['scale']}")
    removed = []
    for obj in list(bpy.data.objects):
        name = obj.name
        if name.startswith(f"CavitySrc_{label}"):
            removed.append(name)
            bpy.data.objects.remove(obj, do_unlink=True)
            continue
        if name.startswith(f"Cavity_{label}_"):
            suffix = name[len(f"Cavity_{label}_"):].replace(".001", "")
            if keep_mm is None or suffix != f"{keep_mm * 1000.0:.1f}mm":
                removed.append(name)
                bpy.data.objects.remove(obj, do_unlink=True)
            continue
        if name.startswith(f"TailGuide_{label}_"):
            if keep_tag is None or keep_tag not in name:
                removed.append(name)
                bpy.data.objects.remove(obj, do_unlink=True)
    return removed


def slim_slab(slab):
    """The per-slab evidence that matters, without the raw hit lists."""
    keep = ("index", "slab_x", "band_vertices", "selected_strategy",
            "selected_width", "selected_midpoint", "selected_midpoint_clearance",
            "best_midpoint_clearance_m", "potential_thickness_m",
            "usable_for_guide", "cavity_normal", "rejected")
    return {k: slab[k] for k in keep if k in slab}


def slim_attempt(attempt):
    """Drop the per-ring iteration traces; keep the outcome and the radii."""
    out = {k: v for k, v in attempt.items() if k != "runs"}
    out["runs"] = []
    for run in attempt.get("runs", []):
        r = {k: v for k, v in run.items() if k != "ring_trace"}
        r["ring_radii_m"] = [t.get("admissible_radius_m")
                             for t in run.get("ring_trace", [])]
        r["ring_caps_m"] = [t.get("radius_cap_m")
                            for t in run.get("ring_trace", [])]
        out["runs"].append(r)
    return out


def prune_report(report):
    """Keep full diagnostics for the selected offsets, summaries elsewhere."""
    for entry in report["segments"]:
        keep_full = entry.get("selected_thickness_m")
        for row in entry["offsets"]:
            chosen = (keep_full is not None
                      and abs(row["thickness_m"] - keep_full) < 1e-9)
            if not chosen:
                if "guide" in row:
                    row["guide_summary"] = summarize_attempt(row["guide"])
                    del row["guide"]
                if "best_failed_attempt" in row:
                    row["best_failed_attempt"] = {
                        k: v for k, v in row["best_failed_attempt"].items()
                        if k in ("profile", "scale", "coverage", "run_count",
                                 "runs_built", "worst_containment_percent",
                                 "worst_min_clearance_m",
                                 "rejected_runs")}
                for key in ("slabs", "attempts", "centreline_refinement",
                            "centreline_clearance", "centreline_qa"):
                    row.pop(key, None)
                continue
            if "slabs" in row:
                row["slabs"] = [slim_slab(s) for s in row["slabs"]]
            # The chosen attempt is already stored as row["guide"]; the other
            # attempts are summarised by profile and scale only.
            if "attempts" in row:
                row["attempts"] = [
                    {"profile": a.get("profile"), "scale": a.get("scale"),
                     "pass": a.get("pass"),
                     "coverage": (a.get("coverage") or {}).get(
                         "coverage_ratio_of_usable"),
                     "runs_built": a.get("runs_built"),
                     "runs_unbuildable": a.get("runs_unbuildable")}
                    for a in row["attempts"]]
            if "guide" in row:
                row["guide"] = slim_attempt(row["guide"])
            ref = row.get("centreline_refinement")
            if ref and "trace" in ref:
                ref["trace"] = [
                    {k: t.get(k) for k in ("slab_index", "initial_clearance_m",
                                           "refined_clearance_m",
                                           "displacement_m", "accepted_moves",
                                           "termination")}
                    for t in ref["trace"]]
            if ref and "smoothing" in ref:
                ref["smoothing"] = [s for s in ref["smoothing"]
                                    if isinstance(s, dict) and "pass" in s]
    return report


def main():
    args = parse_args()
    offsets = sorted(float(x) for x in args.offsets.split(","))
    _meshes, size = vehicle_v2.import_and_normalise(args.input, "+Y")
    left_sign, _ = base.resolve_left_sign()
    report = {
        "stage": "taillight_guide_v4",
        "method": "surface-offset cavity + medial centreline + per-ring "
                  "admissible radius, solved per source lamp component",
        "vehicle_size_m": size,
        "epsilon_m": EPSILON,
        "min_guide_radius_m": MIN_R,
        "max_guide_radius_m": R_MAX,
        "min_usable_wall_m": MIN_USABLE_WALL,
        "coverage_min_ratio_of_usable": COVERAGE_MIN_RATIO,
        "coverage_definition":
            "retained guide x-span / x-span of the slabs in the same source "
            "component whose thickest parity-confirmed interior interval can "
            "hold a minimum-radius ring plus epsilon on both sides",
        "offset_candidates_m": offsets,
        "refinement_enabled": args.refine == "on",
        "segments": [],
    }
    comps = component_sources(left_sign)
    report["segment_count"] = len(comps)
    for comp in comps:
        entry = evaluate_segment(comp, offsets, args.refine == "on",
                                 args.debug_dir, args.only)
        if entry is None:
            continue
        report["segments"].append(entry)
        guide = entry.get("guide") or {}
        summary = summarize_attempt(guide) if guide else {}
        print(f"[v4] {entry['label']}: passed={entry['passed']} "
              f"offset={entry.get('selected_thickness_m')} "
              f"runs={summary.get('runs_built')}/{summary.get('run_count')} "
              f"containment={summary.get('worst_containment_percent')} "
              f"clearance={summary.get('worst_min_clearance_m')} "
              f"coverage={(summary.get('coverage') or {}).get('coverage_ratio_of_usable')}")

    segs = report["segments"]

    # The left and right lamps are mirror images of one another, so they must
    # end up on the same cavity offset: a different offset per side would give
    # the two lamps different wall separation and read as an asymmetry on the
    # car. Where both sides pass at a common offset, the larger of the two
    # selections is adopted for both.
    pair_offsets(segs)
    passed = [s for s in segs if s["passed"]]
    report["freeze_gate_v3"] = {
        "every_segment_has_a_guide_or_measured_exclusion": all(
            s["passed"] or s.get("excluded_by_geometry") for s in segs),
        "guide_containment_100": all(
            s["summary"]["worst_containment_percent"] == 100.0
            for s in passed),
        "guide_clearance_over_epsilon": all(
            (s["summary"]["worst_min_clearance_m"] or 0.0) > EPSILON
            for s in passed),
        "coverage_pass": all(
            (s["summary"]["coverage"] or {}).get("pass") for s in passed),
        "segments_passed": sum(1 for s in segs if s["passed"]),
        "segments_excluded_by_geometry": sum(
            1 for s in segs if s.get("excluded_by_geometry")),
        "segments_total": len(segs),
    }
    os.makedirs(os.path.dirname(args.report), exist_ok=True)
    if not args.full_report:
        report = prune_report(report)
    with open(args.report, "w") as fh:
        json.dump(report, fh, indent=2)
        fh.write("\n")
    print(f"[v4] gate: {report['freeze_gate_v3']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
