#!/usr/bin/env python3
"""Regression tests for the taillight guide geometry rules.

These run without Blender: the geometry module is imported against a minimal
mathutils stand-in, and the cavity is replaced by a fake BVH whose distance
function is known analytically. What is protected here is the set of rules that
were expensive to learn:

* space that cannot hold a ring must REJECT the ring, never force a minimum
  radius into it - the bug that made containment look fixed while the guide ran
  along a wall, and that made the failure count identical at every guide scale;
* a ring may only be placed where every one of its vertices clears the wall by
  the production epsilon;
* coverage must be counted in slabs, so a guide that jumps over the middle of a
  lamp cannot report the span it jumps over as coverage;
* the limiting sample must be attributable to the centreline, a ring vertex or a
  ring edge - which is what showed the old failure was not a radius problem.
"""

import math
import os
import re
import sys
import types

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class Vector:
    """Minimal stand-in for mathutils.Vector (3D only)."""

    __slots__ = ("x", "y", "z")

    def __init__(self, x=0.0, y=0.0, z=0.0):
        if isinstance(x, (tuple, list)):
            x, y, z = x[0], x[1], x[2]
        self.x, self.y, self.z = float(x), float(y), float(z)

    def __add__(self, o):
        return Vector(self.x + o.x, self.y + o.y, self.z + o.z)

    def __sub__(self, o):
        return Vector(self.x - o.x, self.y - o.y, self.z - o.z)

    def __mul__(self, s):
        return Vector(self.x * s, self.y * s, self.z * s)

    __rmul__ = __mul__

    def __truediv__(self, s):
        return Vector(self.x / s, self.y / s, self.z / s)

    def __neg__(self):
        return Vector(-self.x, -self.y, -self.z)

    def __iter__(self):
        return iter((self.x, self.y, self.z))

    def __getitem__(self, i):
        return (self.x, self.y, self.z)[i]

    @property
    def length(self):
        return (self.x ** 2 + self.y ** 2 + self.z ** 2) ** 0.5

    def dot(self, o):
        return self.x * o.x + self.y * o.y + self.z * o.z

    def cross(self, o):
        return Vector(self.y * o.z - self.z * o.y,
                      self.z * o.x - self.x * o.z,
                      self.x * o.y - self.y * o.x)

    def normalized(self):
        n = self.length
        return Vector(self.x / n, self.y / n, self.z / n) if n else Vector()

    def normalize(self):
        n = self.length
        if n:
            self.x, self.y, self.z = self.x / n, self.y / n, self.z / n

    def lerp(self, o, t):
        return Vector(self.x + (o.x - self.x) * t,
                      self.y + (o.y - self.y) * t,
                      self.z + (o.z - self.z) * t)

    def angle(self, o):
        c = self.dot(o) / (self.length * o.length)
        return math.acos(max(-1.0, min(1.0, c)))

    def copy(self):
        return Vector(self.x, self.y, self.z)


def load_medial():
    stub = types.ModuleType("mathutils")
    stub.Vector = Vector
    sys.modules["mathutils"] = stub
    sys.path.insert(0, os.path.join(REPO, "tools", "blender"))
    import taillight_medial as medial
    return medial


class SlabTree:
    """A fake cavity: an infinite slab of half-thickness hy in y, hz in z.

    Distance to the boundary is analytic, so every expectation below is a
    closed-form number rather than another approximation.
    """

    def __init__(self, hy, hz):
        self.hy, self.hz = hy, hz

    def find_nearest(self, p, max_dist=5.0):
        d = min(self.hy - abs(p.y), self.hz - abs(p.z))
        return (Vector(p.x, p.y, p.z), Vector(0.0, 1.0, 0.0), 0, d)

    def ray_cast(self, origin, direction, distance=0.5):
        return (None, None, None, None)

    def overlap(self, other):
        return []


FAILURES = []


def check(condition, label):
    if condition:
        print("  ok   %s" % label)
    else:
        print("  FAIL %s" % label)
        FAILURES.append(label)


def main():
    medial = load_medial()
    eps = 0.0015
    min_r = 0.00035

    def inside(point):
        return True

    print("admissible radius")
    # A 6 mm slab: a ring of radius r at the centre clears each wall by 3 - r.
    tree = SlabTree(hy=0.003, hz=0.05)
    path = [Vector(0.0, 0.0, 0.0), Vector(0.01, 0.0, 0.0),
            Vector(0.02, 0.0, 0.0)]
    r, _trace = medial.admissible_radius(tree, path, 0, 0.0030, "round",
                                         eps, min_r, inside)
    check(r is not None and r >= min_r,
          "roomy slab yields a radius (%.5f m)" % (r if r else -1.0))
    pts = medial.ring_points(path, 0, r, "round")
    check(min(medial.clearance(tree, q) for q in pts) > eps,
          "every vertex of the accepted ring clears epsilon")

    # The regression: 1.8 mm of clearance cannot hold a 0.35 mm ring with a
    # 1.5 mm gap. The old code forced max(0.0002, ...) and placed it anyway.
    tight = SlabTree(hy=0.0018, hz=0.05)
    r_tight, trace_tight = medial.admissible_radius(
        tight, path, 0, 0.0030, "round", eps, min_r, inside)
    check(r_tight is None,
          "a slab that cannot hold a ring REJECTS it instead of forcing one")
    check(all(t.get("radius_m", 1.0) >= min_r for t in trace_tight),
          "the rejection never tries a radius below the minimum")

    edge = SlabTree(hy=0.00185, hz=0.05)
    r_edge, _ = medial.admissible_radius(edge, path, 0, 0.0030, "round",
                                         eps, min_r, inside)
    check(r_edge is None, "clearance exactly at the gate is not accepted")

    print("ring frame continuity")
    bent = [Vector(0.0, 0.0, 0.0), Vector(0.01, 0.0, 0.0),
            Vector(0.02, 0.0, 0.0), Vector(0.03, 0.0, 0.02),
            Vector(0.04, 0.0, 0.04)]
    bases = medial.ring_bases(bent)
    dots = [bases[i][0].dot(bases[i + 1][0]) for i in range(len(bases) - 1)]
    check(all(d > 0.0 for d in dots),
          "no ring frame flips against its neighbour along the path")

    print("coverage is counted in slabs")
    slabs = [{"index": i, "slab_x": i * 0.005} for i in range(20)]
    full = medial.slab_coverage([s["slab_x"] for s in slabs], slabs, 0.005)
    check(full["coverage_ratio_of_usable"] == 1.0 and full["pass"],
          "rings on every slab cover every slab")
    gapped = medial.slab_coverage(
        [s["slab_x"] for s in slabs if s["index"] not in (8, 9, 10, 11)],
        slabs, 0.005)
    check(gapped["coverage_ratio_of_usable"] < 0.85,
          "a hole in the middle is not hidden by a wide x span (%.4f)"
          % gapped["coverage_ratio_of_usable"])
    check(gapped["uncovered_slab_indices"] == [8, 9, 10, 11],
          "the uncovered slabs are named")
    short = medial.slab_coverage([s["slab_x"] for s in slabs[:5]], slabs,
                                 0.005)
    check(not short["pass"],
          "keeping a fifth of the lamp is a coverage failure, not a PASS")

    print("clearance attribution")
    records = [{"kind": "GUIDE_RING_VERTEX", "ring": 0, "vertex": 0,
                "position": Vector(0.0, 0.0029, 0.0)},
               {"kind": "CENTERLINE", "ring": 0, "vertex": None,
                "position": Vector(0.0, 0.0, 0.0)},
               {"kind": "GUIDE_LENGTH_SAMPLE", "ring": 1, "vertex": 3,
                "position": Vector(0.01, 0.001, 0.0)}]
    ev = medial.evaluate_samples(tree, records, inside)
    check(ev["limiting_sample"]["kind"] == "GUIDE_RING_VERTEX",
          "the minimum is attributed to the sample that caused it")
    check(ev["inside_percent"] == 100.0, "containment is reported separately")

    print("forced minimum radius cannot come back")
    src_dir = os.path.join(REPO, "tools", "blender")
    # The active pipeline only. taillight_guide_v3.py is the superseded stage
    # that contained the original max(0.0002, ...) floor; it is kept for
    # history and is no longer imported for placement (v4 imports only its
    # EPSILON constant and its thickness probe), so the rule guarded here is
    # the one that governs placement today.
    active = ("taillight_medial.py", "taillight_guide_v4.py",
              "taillight_offset.py", "taillight_finalize.py")
    offenders = []
    for name in active:
        with open(os.path.join(src_dir, name)) as fh:
            text = fh.read()
        for m in re.finditer(r"max\(\s*0\.000\d", text):
            offenders.append("%s:%d" % (name,
                                        text.count("\n", 0, m.start()) + 1))
    check(not offenders,
          "no forced positive minimum radius in the active pipeline (%s)"
          % (", ".join(offenders) if offenders else "clean"))

    print("")
    if FAILURES:
        print("%d FAILED: %s" % (len(FAILURES), "; ".join(FAILURES)))
        return 1
    print("all taillight guide regression checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
