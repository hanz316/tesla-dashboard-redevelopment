#!/usr/bin/env python3
"""Medial centreline construction and diagnostics for the taillight cavity.

Stage 3a of the taillight work. taillight_guide_v3.py places the light guide
along a centreline derived from ray/surface intersection midpoints. That seed
is only *a* pair of walls along one ray, not necessarily the medial axis of the
cavity, and on a curved lens shell it can sit within microns of a wall while
still being technically inside the volume. That is the failure this module
exists to remove.

Three responsibilities, in this order:

1. INSTRUMENT - every slab keeps a full record of its raw hits, clustered
   unique crossings, candidate consecutive intervals, the parity verdict for
   each interval midpoint, and the finally selected pair. Diagnostics are
   written from that record, so any conclusion can be traced back to the
   numbers that produced it.
2. REFINE - the seed midpoint is relaxed to a local maximum of the distance to
   the cavity boundary. The move is constrained to the slab plane, so the path
   keeps its ordering in x and cannot jump to unrelated geometry.
3. MEASURE - coverage and clearance are reported as separate quantities, and
   every clearance number can be attributed to the sample that produced it.

A point that is inside the volume but grazing a wall reads as "containment
100%" while being unusable as a guide path. Containment and clearance are not
the same gate and this module never reports one as the other.
"""

import math

from mathutils import Vector

RAY_STEP_M = 1e-5
CLUSTER_EPS_M = 2e-4
RAY_LIMIT_M = 0.5
ORIGIN_BACKOFF_M = 0.3
SLAB_COUNT = 24

# Deterministic secondary rays for the independent parity verdict. They are
# deliberately non-axis-aligned so that a face nearly tangent to one of them
# cannot flip the verdict on its own.
SECOND_RAYS = [Vector((1.0, 0.37, 0.71)).normalized(),
               Vector((-0.53, 1.0, 0.29)).normalized(),
               Vector((0.41, -0.62, 1.0)).normalized()]
PARALLEL_LIMIT = 0.95
SOURCE_RAYS_PER_SLAB = 8


def _representatives(count, k):
    """Up to k deterministic, evenly spaced indices out of `count`."""
    if count <= 0:
        return []
    if count <= k:
        return list(range(count))
    return sorted({int(round(i * (count - 1) / (k - 1))) for i in range(k)})


def _compact(entry):
    """An attempt that found nothing, without its (large) raw hit list."""
    return {k: v for k, v in entry.items() if k != "raw_hits"} | {
        "raw_hit_count": len(entry.get("raw_hits", [])),
        "candidate_intervals": [
            {"verdict": iv.get("verdict"), "width": iv.get("width"),
             "inside": iv.get("inside")}
            for iv in entry.get("candidate_intervals", [])]}


def raw_hits(tree, origin, direction, limit=RAY_LIMIT_M):
    """Every surface hit along a ray, in travel order.

    Positions and polygon indices are kept so a suspect crossing can be
    identified instead of inferred.
    """
    hits = []
    o = Vector(origin)
    travelled = 0.0
    for _ in range(128):
        loc, nrm, idx, dist = tree.ray_cast(o, direction, limit - travelled)
        if loc is None:
            break
        travelled += (loc - o).length
        if travelled >= limit:
            break
        hits.append({"t": travelled,
                     "position": [round(c, 7) for c in loc],
                     "normal": [round(c, 6) for c in nrm] if nrm else None,
                     "polygon": idx})
        o = loc + direction * RAY_STEP_M
    return hits


def cluster_crossings(hits, eps=CLUSTER_EPS_M):
    """Raw hits -> unique surface crossings.

    A shared edge or shared vertex registers two triangle hits for one physical
    crossing, which silently corrupts parity. Clustering by distance is what
    makes the parity meaningful.
    """
    ts = sorted(h["t"] for h in hits)
    clusters = []
    for t in ts:
        if clusters and abs(t - clusters[-1]["t"]) < eps:
            clusters[-1]["members"].append(t)
            continue
        clusters.append({"t": t, "members": [t]})
    return clusters


def inside_by(tree, point, direction, limit=RAY_LIMIT_M):
    """Odd crossing count along one ray."""
    return len(cluster_crossings(raw_hits(tree, point, direction, limit))) % 2 == 1


def classify(tree, point, primary, rays=None):
    """Independent, non-collinear parity verdict with its per-ray evidence."""
    rays = SECOND_RAYS if rays is None else rays
    votes = []
    for d in rays:
        if abs(d.dot(primary)) > PARALLEL_LIMIT:
            votes.append({"direction": [round(c, 6) for c in d],
                          "skipped": "too parallel to the primary ray"})
            continue
        v = inside_by(tree, point, d)
        votes.append({"direction": [round(c, 6) for c in d], "inside": v})
        if len([x for x in votes if "inside" in x]) >= 2:
            break
    decided = [x for x in votes if "inside" in x]
    if not decided:
        return None, votes
    return sum(1 for v in decided if v["inside"]) * 2 >= len(decided), votes


def clearance(tree, point, max_search=5.0):
    """Euclidean distance from a point to the nearest cavity surface."""
    res = tree.find_nearest(point, max_search)
    if res[0] is None:
        return 0.0
    return res[3]


def segments_for_verts(verts, steps):
    """The fixed slab grid: `steps` bands of equal width across the x extent."""
    xs = sorted(p.x for p in verts)
    lo_x, hi_x = xs[0], xs[-1]
    width = (hi_x - lo_x) / steps
    out = []
    for i in range(steps):
        t = i / (steps - 1.0)
        cx = lo_x + (hi_x - lo_x) * t
        band = [j for j, p in enumerate(verts) if abs(p.x - cx) < width]
        out.append({"index": i, "cx": cx, "band": band, "half_width": width})
    return out


def attempt_ray(tree, origin, direction, limit, expected_wall, inside_test):
    """Cast one ray and score every parity-confirmed interior interval."""
    hits = raw_hits(tree, origin, direction, limit)
    clusters = cluster_crossings(hits)
    ts = [cl["t"] for cl in clusters]
    entry = {"origin": [round(v, 7) for v in origin],
             "direction": [round(v, 7) for v in direction],
             "limit_m": limit,
             "raw_hits": hits,
             "unique_crossings": [round(t, 7) for t in ts],
             "clusters": [{"t": round(cl["t"], 7),
                           "members": len(cl["members"])} for cl in clusters],
             "candidate_intervals": []}
    best = None
    for k in range(len(ts) - 1):
        t0, t1 = ts[k], ts[k + 1]
        iv = {"pair": [k, k + 1], "t0": round(t0, 7), "t1": round(t1, 7),
              "width": round(t1 - t0, 7)}
        if (t1 - t0) < 1e-4:
            iv["verdict"] = "degenerate width"
            entry["candidate_intervals"].append(iv)
            continue
        mid = Vector(origin) + Vector(direction) * ((t0 + t1) * 0.5)
        verdict, votes = classify(tree, mid, Vector(direction))
        iv["midpoint"] = [round(v, 7) for v in mid]
        iv["midpoint_clearance_m"] = round(clearance(tree, mid), 7)
        iv["parity_votes"] = votes
        iv["inside"] = verdict
        if verdict is not True:
            iv["verdict"] = "midpoint not confirmed inside"
            entry["candidate_intervals"].append(iv)
            continue
        if not inside_test(mid):
            iv["verdict"] = "midpoint parity disagrees with the volume test"
            entry["candidate_intervals"].append(iv)
            continue
        iv["verdict"] = "valid interior interval"
        score = -abs((t1 - t0) - expected_wall)
        iv["thickness_prior_score"] = round(score, 7)
        if best is None or score > best[0]:
            best = (score, mid, t1 - t0, iv)
        entry["candidate_intervals"].append(iv)
    entry["best_interval"] = None if best is None else {
        "width_m": round(best[2], 7),
        "midpoint": [round(v, 7) for v in best[1]]}
    return entry, best


def slab_seeds(tree, cavity, expected_wall, inside_test, source=None,
               steps=SLAB_COUNT, segments=None):
    """Slab-by-slab centreline seeds with a complete diagnostic record.

    Two independent seeding strategies are recorded for every slab:

    * CAVITY_NORMAL - the v3 behaviour: ray from the mean of the cavity's own
      band vertices along the mean of the cavity's own band normals. This is
      fragile: the solidified cavity has an outer and an inner shell whose
      normals point in opposite directions, so their mean is a small residual
      vector whose direction is unstable and often nearly tangent to the wall.
    * SOURCE_NORMAL - ray along the mean normal of the ORIGINAL lens shell in
      the same band, cast from just outside the shell in both directions. The
      source shell has consistent normals, so this direction is meaningful.

    A seed is only accepted as a valid interior interval when its midpoint is
    confirmed inside by an independent, non-collinear ray and by the volume
    test. "Widest gap wins" is never used as proof.
    """
    mw = cavity.matrix_world
    mw3 = mw.to_3x3()
    verts = [mw @ v.co for v in cavity.data.vertices]
    normals = cavity.data.vertex_normals
    if segments is None:
        segments = segments_for_verts(verts, steps)

    qa = {"samples": 0, "valid_pairs": 0, "invalid_pairs": 0,
          "midpoints_inside": 0, "midpoints_outside": 0, "no_band": 0,
          "no_cavity_normal_interval": 0,
          "no_source_vertex_normal_interval": 0,
          "selected_from_source_vertex_normal": 0,
          "selected_from_cavity_normal": 0,
          "selection_widened_for_continuity": 0}
    seeds, debug = [], []
    source_limit = max(0.02, 4.0 * expected_wall)
    xs = [p.x for p in verts]
    slab_spacing = (max(xs) - min(xs)) / (steps - 1.0)
    # Kept tight on purpose: a seed allowed to land several slabs sideways
    # makes the path kink, and a kinked path turns each ring frame against its
    # neighbour (measured: 76-81 degrees) so the tube's chords graze a wall.
    max_jump = 0.9 * slab_spacing
    prev_point = None

    for record in segments:
        i = record["index"]
        cx = record["cx"]
        band = record["band"]
        if not band:
            qa["no_band"] += 1
            continue
        c = Vector((0.0, 0.0, 0.0))
        n = Vector((0.0, 0.0, 0.0))
        for j in band:
            c += verts[j]
            n += mw3 @ Vector(normals[j].vector)
        c /= len(band)
        slab = {"index": i, "slab_x": round(cx, 7), "band_vertices": len(band),
                "cavity_centroid": [round(v, 7) for v in c],
                "cavity_normal": None, "attempts": []}
        candidates = []
        if n.length >= 1e-9:
            qa["samples"] += 1
            n.normalize()
            slab["cavity_normal"] = [round(v, 6) for v in n]
            entry, _best = attempt_ray(tree, c + n * ORIGIN_BACKOFF_M, -n,
                                       RAY_LIMIT_M, expected_wall, inside_test)
            entry["strategy"] = "CAVITY_NORMAL"
            slab["attempts"].append(entry)
            if _best is None:
                qa["no_cavity_normal_interval"] += 1
        if source is not None:
            sverts, snormals = source["verts"], source["normals"]
            sband = [j for j in range(len(sverts))
                     if abs(sverts[j].x - cx) < record["half_width"]]
            if sband:
                # Rays start ON the shell, along each vertex's own normal. A
                # band centroid is not on the geometry: where the lamp wraps
                # around the corner, the measured distance from the band
                # centroid to the nearest cavity surface reached 35 mm, and
                # every ray fired from that empty point hit nothing.
                reps = _representatives(len(sband), SOURCE_RAYS_PER_SLAB)
                got = False
                for r in reps:
                    j = sband[r]
                    sv, sn = sverts[j], snormals[j]
                    if sn.length < 1e-9:
                        continue
                    sn = sn.normalized()
                    for sign in (1.0, -1.0):
                        entry, best = attempt_ray(
                            tree, sv + sn * (sign * 0.001), -sn * sign,
                            source_limit, expected_wall, inside_test)
                        entry["strategy"] = "SOURCE_VERTEX_NORMAL"
                        entry["source_vertex"] = j
                        entry["side_sign"] = sign
                        entry["vertex_normal"] = [round(v, 6) for v in sn]
                        slab["attempts"].append(
                            entry if best is not None else _compact(entry))
                        if best is not None:
                            got = True
                            break
                    if got:
                        break
                if not got:
                    qa["no_source_vertex_normal_interval"] += 1
        # Every parity-confirmed interior interval from every attempt is a
        # candidate. Using only each attempt's thickness-prior winner discards
        # the interval that is actually mid-wall: on one slab the prior's pick
        # sat 0.5 mm from a wall while another interval in the same slab sat
        # 2.8 mm from it.
        for entry in slab["attempts"]:
            for iv in entry.get("candidate_intervals", []):
                if iv.get("verdict") != "valid interior interval":
                    continue
                candidates.append((entry["strategy"], iv))
        if not candidates:
            qa["invalid_pairs"] += 1
            slab["rejected"] = ("no attempt produced a parity-confirmed "
                                "interior interval")
            debug.append(slab)
            continue
        # Choose by measured clearance at the interval midpoint, not by which
        # strategy produced it. A mid-wall midpoint is roughly half the local
        # thickness from a wall, so clearance IS the empirical quality signal;
        # the thickness prior only breaks ties. An earlier version preferred
        # SOURCE_NORMAL unconditionally and selected 0.06 mm-clearance seeds in
        # slabs where the cavity-normal ray had already found a 2 mm one.
        scored = []
        for strategy, iv in candidates:
            mid = Vector(iv["midpoint"])
            scored.append((iv.get("midpoint_clearance_m") or 0.0,
                           iv.get("thickness_prior_score") or 0.0,
                           strategy, mid, iv["width"], iv))
        scored.sort(key=lambda s: (-s[0], -s[1], s[2]))
        # Keep the path coherent: in a slab that wraps around the lamp corner
        # the best-clearance interval can sit on the other side of the shell,
        # so candidates farther than a few slabs from the running path are
        # rejected - unless nothing else is available.
        if prev_point is not None:
            near = [s for s in scored
                    if (s[3] - prev_point).length <= max_jump]
            if near:
                scored = near
            else:
                qa["selection_widened_for_continuity"] += 1
        _, score, strategy, mid, width, iv = scored[0]
        iv["selected"] = True
        qa["valid_pairs"] += 1
        qa["selected_from_source_vertex_normal"
            if strategy == "SOURCE_VERTEX_NORMAL"
            else "selected_from_cavity_normal"] += 1
        if inside_test(mid):
            qa["midpoints_inside"] += 1
        else:
            qa["midpoints_outside"] += 1
        slab["selected_strategy"] = strategy
        slab["selected_width"] = round(width, 7)
        slab["selected_midpoint"] = [round(v, 7) for v in mid]
        slab["selected_midpoint_clearance"] = round(clearance(tree, mid), 7)
        debug.append(slab)
        prev_point = mid
        seeds.append({"index": i, "slab_x": cx, "centroid": c, "normal": n,
                      "width": width, "point": mid, "strategy": strategy,
                      "clearance": clearance(tree, mid)})

    return seeds, qa, debug


def medial_refine(tree, seed, expected_wall, inside_test,
                  plane_axes=((0.0, 1.0, 0.0), (0.0, 0.0, 1.0)),
                  step0=None, tol=1e-6, max_iters=256, max_disp=None,
                  improvement=1e-6):
    """Relax a seed to a local maximum of the distance to the boundary.

    Deterministic: a fixed set of in-plane directions, a geometrically
    decreasing step, an explicit iteration bound and an explicit displacement
    bound. A move is accepted only when the candidate is confirmed inside the
    closed cavity and strictly increases the minimum boundary distance, so the
    path can never leave the volume, cannot jump to a disconnected region and
    cannot reverse.

    The slab plane constraint is what keeps the path ordered: x is fixed, so
    slab i stays between slab i-1 and slab i+1 by construction.
    """
    step_start = expected_wall * 0.25 if step0 is None else step0
    disp_cap = expected_wall * 2.0 if max_disp is None else max_disp
    ax, ay = Vector(plane_axes[0]), Vector(plane_axes[1])
    dirs = []
    for k in range(8):
        a = 2.0 * math.pi * k / 8.0
        dirs.append((ax * math.cos(a) + ay * math.sin(a)).normalized())

    best = Vector(seed)
    best_c = clearance(tree, best)
    start = best.copy()
    start_c = best_c
    step = step_start
    iters = 0
    accepted = 0
    termination = "step below tolerance"
    while step > tol:
        if iters >= max_iters:
            termination = "iteration bound reached"
            break
        improved = False
        for d in dirs:
            cand = best + d * step
            if (cand - start).length > disp_cap:
                continue
            if not inside_test(cand):
                continue
            c = clearance(tree, cand)
            if c > best_c + improvement:
                best, best_c = cand, c
                accepted += 1
                improved = True
                break
        iters += 1
        if not improved:
            step *= 0.5
    return {"point": best, "clearance": best_c,
            "start_clearance": start_c,
            "displacement": (best - start).length,
            "iterations": iters, "accepted_moves": accepted,
            "termination": termination}


def coverage(seeds, retained_indices, usable_span_m, cavity_span_m,
             min_ratio=0.80):
    """Coverage gate derived from geometry, not from a visual guess.

    `usable_span_m` is the x-extent of the slabs where the cavity is actually
    thick enough to hold a guide of the minimum admissible radius. Retaining a
    short fragment of the lamp and reporting 100% containment is exactly the
    loophole this measures: a guide that covers a fifth of the usable span is
    not a production light guide, however well contained it is.
    """
    x = [s["slab_x"] for s in seeds if s["index"] in retained_indices]
    retained_span = (max(x) - min(x)) if len(x) >= 2 else 0.0
    ratio = (retained_span / usable_span_m) if usable_span_m > 0 else 0.0
    return {
        "retained_points": len(x),
        "retained_x_span_m": round(retained_span, 7),
        "usable_x_span_m": round(usable_span_m, 7),
        "cavity_x_span_m": round(cavity_span_m, 7),
        "coverage_ratio_of_usable": round(ratio, 4),
        "coverage_ratio_of_cavity": round(
            retained_span / cavity_span_m if cavity_span_m > 0 else 0.0, 4),
        "min_ratio_required": min_ratio,
        "pass": ratio >= min_ratio,
    }


def usable_spans(slabs, min_usable_clearance_m):
    """Which slabs have room for a guide, judged by geometry alone.

    A ring of radius R fits with epsilon to spare exactly when some interior
    point of the slab sits at least R + epsilon from the boundary, so the test
    is run on the best measured midpoint clearance in the slab - not on whether
    the placement algorithm succeeded there, and not as a min/max x span.
    """
    usable = []
    for s in slabs:
        best = max([iv.get("midpoint_clearance_m") or 0.0
                    for attempt in s.get("attempts", [])
                    for iv in attempt.get("candidate_intervals", [])
                    if iv.get("inside") is True] or [0.0])
        s["best_midpoint_clearance_m"] = round(best, 7)
        s["potential_thickness_m"] = round(2.0 * best, 7)
        s["usable_for_guide"] = best >= min_usable_clearance_m
        if s["usable_for_guide"]:
            usable.append(s)
    xs = [s["slab_x"] for s in usable]
    span = (max(xs) - min(xs)) if len(xs) >= 2 else 0.0
    return usable, span


def self_intersections(obj, guide_points=None, near_radius_m=None):
    """Faces that intersect without sharing a vertex.

    The mesh is triangulated first so that the polygon indices returned by the
    overlap test map one-to-one onto the primitives in the tree. Testing the
    untriangulated mesh reports adjacency as intersection and turns a healthy
    cavity into hundreds of phantom hits.

    Calibrated against known cases: a flat shell and a gently curved shell
    report 0 pairs at every offset that does not collapse, and a gently curved
    shell at an offset past its curvature radius reports a non-zero count. A
    non-zero global count on a real lamp is therefore local collapse - typically
    even-offset overshoot at the shell rim, away from the guide.

    When guide_points are supplied, the pairs within near_radius_m of the guide
    are counted separately. That is the subset that can invalidate the
    containment proof for THIS guide; the rest is reported as evidence.
    """
    import bpy
    import bmesh
    from mathutils.bvhtree import BVHTree

    bm = bmesh.new()
    bm.from_mesh(obj.data)
    bmesh.ops.triangulate(bm, faces=bm.faces)
    bm.verts.ensure_lookup_table()
    verts = [tuple(obj.matrix_world @ v.co) for v in bm.verts]
    tris = [tuple(v.index for v in f.verts) for f in bm.faces]
    bm.free()
    if not tris:
        return {"intersecting_face_pairs": 0, "triangles": 0, "examples": []}
    tree = BVHTree.FromPolygons(verts, tris, all_triangles=True)
    centroids = [tuple(sum(verts[i][k] for i in tri) / 3.0 for k in range(3))
                 for tri in tris]
    bad, seen = [], set()
    near = 0
    for a, b in tree.overlap(tree):
        if a == b:
            continue
        if set(tris[a]) & set(tris[b]):
            continue
        key = (a, b) if a < b else (b, a)
        if key in seen:
            continue
        seen.add(key)
        bad.append(key)
        if guide_points and near_radius_m:
            mid = tuple((centroids[a][k] + centroids[b][k]) * 0.5
                        for k in range(3))
            for p in guide_points:
                dx = mid[0] - p.x
                dy = mid[1] - p.y
                dz = mid[2] - p.z
                if dx * dx + dy * dy + dz * dz <= near_radius_m ** 2:
                    near += 1
                    break
    return {"intersecting_face_pairs": len(bad),
            "near_guide_pairs": near if guide_points else None,
            "near_radius_m": near_radius_m if guide_points else None,
            "triangles": len(tris),
            "examples": [{"faces": list(p),
                          "midpoint": [round(c, 5) for c in
                                       [(centroids[p[0]][k]
                                         + centroids[p[1]][k]) * 0.5
                                        for k in range(3)]]}
                         for p in sorted(bad)[:8]]}


# ---------------------------------------------------------------------------
# Ring geometry. These helpers are the single definition of a ring's shape, so
# that measuring a candidate ring and building the guide mesh can never
# disagree about where the ring's vertices are.

def ring_basis(path, i):
    # A wider tangent window keeps the ring plane from being thrown around by
    # one noisy neighbour: the tube's surface chords are what graze a wall when
    # adjacent ring planes disagree, even though every ring centre is mid-wall.
    n = len(path)
    lo = max(0, i - 2)
    hi = min(n - 1, i + 2)
    t = path[hi] - path[lo]
    if t.length < 1e-9:
        t = path[min(i + 1, n - 1)] - path[max(i - 1, 0)]
    t.normalize()
    side = t.cross(Vector((0.0, 0.0, 1.0)))
    if side.length < 1e-6:
        side = Vector((0.0, 1.0, 0.0))
    side.normalize()
    up = side.cross(t).normalized()
    return side, up


def ring_bases(path):
    """Ring frames along the whole path, with the sign kept continuous.

    side = tangent x Z flips direction when the tangent swings past Z, and a
    single flip rotates one ring by 180 degrees against its neighbour: every
    longitudinal edge then crosses the tube and grazes a wall, however well
    each ring was sized on its own. Carrying the sign forward removes that
    without changing any ring that was already consistent.
    """
    bases = []
    prev_side = None
    for i in range(len(path)):
        side, up = ring_basis(path, i)
        if prev_side is not None and side.dot(prev_side) < 0.0:
            side, up = -side, -up
        bases.append((side, up))
        prev_side = side
    return bases


def ring_points_with(bases, path, i, r, profile, segments=12):
    side, up = bases[i]
    p = path[i]
    out = []
    for k in range(segments):
        ox, oz = profile_offset(profile, 2.0 * math.pi * k / segments, r)
        out.append(p + side * ox + up * oz)
    return out


def profile_offset(profile, angle, r):
    ca, sa = math.cos(angle), math.sin(angle)
    if profile == "rounded_rect":
        nn = 4.0
        den = (abs(ca) ** nn + abs(sa) ** nn) ** (1.0 / nn)
        return ca / den * r, sa / den * r
    if profile == "oval":
        return ca * r * 0.6, sa * r
    return ca * r, sa * r


def ring_points(path, i, r, profile, segments=12):
    side, up = ring_basis(path, i)
    p = path[i]
    out = []
    for k in range(segments):
        ox, oz = profile_offset(profile, 2.0 * math.pi * k / segments, r)
        out.append(p + side * ox + up * oz)
    return out


def build_guide(path, radii, profile, name, segments=12):
    """The guide mesh, built from the same ring definition that was measured.

    v3's make_guide derived its own ring planes from a single-neighbour
    tangent, while the radii were decided from a differently oriented ring.
    Measuring one shape and building another is how every ring passes its own
    check while the chords between rings still graze a wall, so this builds
    from ring_points() directly.
    """
    import bpy
    import bmesh

    bm = bmesh.new()
    rings = []
    bases = ring_bases(path)
    for i, p in enumerate(path):
        ring = [bm.verts.new(q) for q in
                ring_points_with(bases, path, i, radii[i], profile, segments)]
        rings.append(ring)
    bm.verts.ensure_lookup_table()
    for i in range(len(rings) - 1):
        a, b = rings[i], rings[i + 1]
        for k in range(segments):
            k2 = (k + 1) % segments
            bm.faces.new((a[k], a[k2], b[k2], b[k]))
    bm.faces.new(list(reversed(rings[0])))
    bm.faces.new(rings[-1])
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    mesh = bpy.data.meshes.new(name)
    bm.to_mesh(mesh)
    bm.free()
    for poly in mesh.polygons:
        poly.use_smooth = True
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.scene.collection.objects.link(obj)
    return obj


def admissible_radius(tree, path, i, r_cap, profile, epsilon, min_r,
                      inside_test, bases=None, shrink=0.85, iterations=14):
    """Largest ring radius that keeps every ring vertex genuinely clear.

    The measurement is on the actual ring vertices in the actual ring plane,
    not on an analytic approximation from the centre clearance. Insufficient
    local space returns None - the ring is rejected, never forced to a minimum
    radius. That rule is the regression this function exists to guarantee.
    """
    r = r_cap
    trace = []
    bases = ring_bases(path) if bases is None else bases
    for _ in range(iterations):
        if r < min_r:
            trace.append({"radius_m": round(r, 7),
                          "rejected": "below minimum admissible radius"})
            return None, trace
        pts = ring_points_with(bases, path, i, r, profile)
        ds = [clearance(tree, q) for q in pts]
        outside = sum(1 for q in pts if not inside_test(q))
        dmin = min(ds)
        trace.append({"radius_m": round(r, 7),
                      "min_clearance_m": round(dmin, 7),
                      "vertices_outside": outside})
        if outside == 0 and dmin > epsilon:
            return r, trace
        r *= shrink
    return None, trace


def guide_sample_records(guide_obj, path, ring_segments=12):
    """Every verification sample with its identity.

    Attribution matters: a reported minimum clearance that cannot say whether
    it came from the centreline or from a ring is not actionable.
    """
    mw = guide_obj.matrix_world
    verts = [mw @ v.co for v in guide_obj.data.vertices]
    records = []
    n_rings = len(path)
    for i in range(n_rings):
        ring = verts[i * ring_segments:(i + 1) * ring_segments]
        for k in range(ring_segments):
            records.append({"kind": "GUIDE_RING_VERTEX", "ring": i,
                            "vertex": k, "position": ring[k]})
        for k in range(ring_segments):
            mid = (ring[k] + ring[(k + 1) % ring_segments]) * 0.5
            records.append({"kind": "GUIDE_RING_EDGE_MIDPOINT", "ring": i,
                            "vertex": k, "position": mid})
    # Along the length, not only at the rings: when two consecutive rings are
    # far apart (a slab with no seed between them) the tube between them is a
    # straight chord, and a chord across a curving lamp can leave the cavity
    # without any ring vertex moving. Sampling only the rings would miss it.
    for i in range(n_rings - 1):
        a = verts[i * ring_segments:(i + 1) * ring_segments]
        b = verts[(i + 1) * ring_segments:(i + 2) * ring_segments]
        for k in range(ring_segments):
            for t in (0.25, 0.5, 0.75):
                records.append({"kind": "GUIDE_LENGTH_SAMPLE", "ring": i,
                                "vertex": k, "t": t,
                                "position": a[k].lerp(b[k], t)})
    for i, p in enumerate(path):
        records.append({"kind": "CENTERLINE", "ring": i, "vertex": None,
                        "position": p})
    return records


def evaluate_samples(tree, records, inside_test):
    """Containment and clearance with the limiting sample identified."""
    inside = 0
    worst = None
    for rec in records:
        p = rec["position"]
        if inside_test(p):
            inside += 1
        d = clearance(tree, p)
        rec["clearance_m"] = round(d, 7)
        if worst is None or d < worst[0]:
            worst = (d, rec)
    total = len(records)
    limiting = None
    if worst is not None:
        limiting = {"kind": worst[1]["kind"], "ring": worst[1]["ring"],
                    "vertex": worst[1]["vertex"],
                    "position": [round(c, 7) for c in worst[1]["position"]],
                    "clearance_m": round(worst[0], 7)}
    return {"samples": total,
            "inside": inside,
            "inside_percent": round(100.0 * inside / total, 4) if total else 0.0,
            "min_clearance_m": round(worst[0], 7) if worst else 0.0,
            "limiting_sample": limiting}


def percentile(values, f):
    if not values:
        return None
    s = sorted(values)
    return s[min(len(s) - 1, int(len(s) * f))]


def slab_coverage(retained_x, usable_slabs, slab_spacing, min_ratio=0.80):
    """Coverage of the usable slabs, counted in slabs rather than in min/max x.

    A guide that jumps over the middle of a lamp still has a wide x span, so a
    span-based ratio reports coverage that is not there. Counting the slabs
    that actually have a ring near them cannot be fooled that way, and it is
    what stops "18 usable samples -> keep 5 -> PASS" from being reported as a
    production result.
    """
    # A ring counts for the slab it is actually in, not for its neighbours:
    # with a one-and-a-half-slab window a four-slab hole was still reported as
    # 90% covered, because the rings on either side both claimed the gap.
    covered = set()
    for slab in usable_slabs:
        for x in retained_x:
            if abs(x - slab["slab_x"]) <= 0.6 * slab_spacing:
                covered.add(slab["index"])
                break
    ratio = (len(covered) / float(len(usable_slabs))) if usable_slabs else 0.0
    retained = sorted(retained_x)
    return {
        "usable_slabs": len(usable_slabs),
        "covered_usable_slabs": len(covered),
        "covered_slab_indices": sorted(covered),
        "uncovered_slab_indices": sorted(s["index"] for s in usable_slabs
                                         if s["index"] not in covered),
        "coverage_ratio_of_usable": round(ratio, 4),
        "min_ratio_required": min_ratio,
        "retained_x_span_m": round(max(retained) - min(retained), 7)
        if len(retained) >= 2 else 0.0,
        "slab_spacing_m": round(slab_spacing, 7),
        "pass": ratio >= min_ratio,
    }


def clearance_stats(values):
    values = sorted(v for v in values if v is not None)
    if not values:
        return {}
    n = len(values)
    return {"samples": n,
            "min_m": round(values[0], 7),
            "p5_m": round(values[min(n - 1, int(n * 0.05))], 7),
            "median_m": round(values[min(n - 1, int(n * 0.5))], 7),
            "max_m": round(values[-1], 7)}
