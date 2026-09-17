# Taillight guide v4 - medial centreline, per-segment guide, honest gates

Stage report for `tools/blender/taillight_guide_v4.py` (+ `tools/blender/taillight_medial.py`).
Supersedes the v3 stage (`tools/blender/taillight_guide_v3.py`), which is kept for history.

Report: `assets/checkpoints/taillight_final/taillight_candidate_search_v4.json`

## 1. What v3 actually reported

v3 was read as "containment 100% on both sides, clearance does not pass". Re-running it
reproduces its published numbers exactly, and its own gate block says
`guide_containment_100: false` - **no guide was ever selected**. The "100%" came from the
best failed attempt, and the two numbers that mattered were:

| | LEFT | RIGHT |
|---|---|---|
| centreline points that survived v3's filters | **5** | 18 |
| verification samples (`25 x rings`) | 125 | 450 |
| reported minimum clearance | 1.166 mm | 0.061 mm |

## 2. Root causes, each measured

1. **The limiting sample was a centreline point, not a ring vertex.**
   v3's verification set included the path points themselves (`samp += sm`), and its ring
   radius was capped by the *centre* clearance (`min(r0 * f, clr * 0.5)`). Measured: the
   reported minimum was invariant at 5.4e-05 m across guide scales 1.0 / 0.8 / 0.62 /
   0.45, which is only possible if shrinking the ring cannot change the number.
2. **One side of the car is not one lamp.** Each side is three separate shells:
   `rear_lights` (x span 0.188 m), `rear_lightsl`/`sr` (0.114 m) and `light_breake`
   (0.059 m), overlapping in x at different y. A single continuous guide cannot span the
   gaps between them.
3. **A slab's mean vertex is not on the geometry.** 24 slabs of 24 measured: where the
   lamp wraps around the corner the band centroid sat 9.5-35 mm from the nearest cavity
   surface (z span 147 mm vs 24 mm elsewhere), and every ray fired from that empty point
   hit nothing. This is the whole of v3's "6 of 24 slabs have no valid pair".
4. **The cavity's own normals cancel.** A solidified shell has an outer and an inner
   surface whose normals oppose, so the mean normal of a band is a small residual vector
   whose direction is unstable. Rays are now fired from actual shell vertices along each
   vertex's own normal.
5. **Selecting an interval per ray is not enough.** Using only each ray's
   thickness-prior winner discarded the interval that was actually mid-wall: on one slab
   the prior's pick sat 0.5 mm from a wall while another interval in the same slab sat
   2.8 mm from it.
6. **Measuring one ring shape and building another.** The radii were validated with
   `medial.ring_points()` (a +/-2-neighbour tangent) while `make_guide()` built the mesh
   with a single-neighbour tangent. The tube's chords grazed walls that every ring
   cleared.
7. **Ring frames flipped and the path kinked.** `side = tangent x Z` flips sign when the
   tangent swings past Z, rotating one ring 180 degrees against its neighbour; and a seed
   allowed to jump sideways makes the frames turn 76-81 degrees between adjacent rings.
8. **Dropping one ring discarded a whole stretch.** The fit loop kept only the longest
   contiguous run, so one impossible ring in the middle threw away 42 healthy rings -
   seven slabs of lamp.

## 3. The gates, as they are now defined

* **Containment**: every sample (ring vertices, ring edge midpoints, length samples
  between rings, and the path points) inside the closed cavity, measured against the
  cavity BVH. Length samples exist because a straight chord between two clear rings can
  still leave the cavity.
* **Guide-surface clearance**: the *actual* minimum distance from any sample to the
  cavity surface must exceed `epsilon = 1.5 mm` (unchanged). Every report states which
  sample produced the minimum: `CENTERLINE`, `GUIDE_RING_VERTEX`,
  `GUIDE_RING_EDGE_MIDPOINT` or `GUIDE_LENGTH_SAMPLE`.
* **Coverage**: `covered usable slabs / usable slabs`, counted in slabs, never in min/max
  x. A ring counts only for the slab it is actually in (0.6 slab spacing), because a
  wider window let a four-slab hole report 90% coverage. Required ratio: **0.80**.
  A slab is `usable` when some interior point of it clears `MIN_R + epsilon + 0.25 mm`
  (2.10 mm), i.e. a minimum-radius ring fits with the production gate and a stated
  margin.
* **Cavity validity**: closed manifold, positive volume, outward; plus two rules learned
  here - the median wall must track the offset (`wall/offset >= 0.90`, else the inward
  offset collapsed) and no self-intersecting face pair may lie within 1 mm of the guide.
  Self-intersection is triangulated before the overlap test and calibrated against known
  cases (flat and gently curved shells report 0; a gently curved shell driven past its
  curvature radius reports non-zero).
* **Rejection, never force**: a ring that cannot hold `MIN_R = 0.35 mm` is dropped, not
  shrunk below it; a stretch that cannot hold four rings is an exclusion with a reason.
  Regression test: `tests/taillight_guide_tests.py`.
* **L/R symmetry**: both sides of one physical lamp must end up on one common offset.

## 4. Result

Offset candidates 2 / 3 / 4 / 5 / 6 / 6.5 / 7 / 8 / 10 / 12 mm, smallest passing wins,
then the pair rule.

| segment | offset | guide runs | containment | min clearance | coverage |
|---|---|---|---|---|---|
| LEFT `rear_lights` | 5 mm | 2 | 100% | 1.503 mm | 0.941 |
| RIGHT `rear_lights` | 5 mm | 2 | 100% | 1.502 mm | 0.941 |
| LEFT `rear_lightsl` | 6 mm | 1 | 100% | 1.501 mm | 0.800 |
| RIGHT `rear_lightsr` | 6 mm | 1 | 100% | 2.198 mm | 0.810 |
| LEFT `light_breake` | - | - | excluded by geometry | | |
| RIGHT `light_breake` | - | - | excluded by geometry | | |

The quarter lamp pair passes at 5 mm on the left and 6 mm on the right; the pair rule
raises both to 6 mm, the larger of the two.

**Brake lamp exclusion evidence** (both sides, every offset measured): the inward offset
collapses at 2-5 mm (median wall 0.80-0.92 mm against a 2-5 mm offset, 35-175
self-intersecting face pairs) and is no longer a valid closed manifold at 6-12 mm; the
usable x span is 0.0 m at every offset. The brake lamp has no interior that can host a
guide, so it is lit by material/emission on the lens. No guide geometry is generated for
it - consistent with "no geometry beats protruding geometry" and with the
`VISUAL_APPROXIMATION` label in the handoff.

## 5. Not done - the master is NOT re-locked

`taillight_geometry.version` is **not** upgraded and `MODEL_A_PRODUCTION_MASTER` is
**not** re-locked. Freeze Gate V3 items 15-26 are still NOT RUN: guide/body and
guide/trunk collision, visible protrusion, screen-space escape QA from the production
camera, trunk ownership `FIXED_BODY`/`TRUNK_MOVING` at 0/25/50/75/100%, and the OFF /
BRAKE / LEFT / RIGHT / HAZARD / HEADLIGHT close-up, 600px and Horizon passes. The
geometry stage is complete against its own gates; the lighting system, trunk motion and
screen-space QA that the freeze gate also requires are separate work.

Regenerate everything with:

```
blender -b --factory-startup -P tools/blender/taillight_guide_v4.py -- \
    --report assets/checkpoints/taillight_final/taillight_candidate_search_v4.json
```

Add `--debug-dir <dir>` for the full per-slab dumps (raw hits, clustered crossings,
candidate intervals, parity votes per ray, refinement traces) - roughly 8 MB for all
offsets, which is why they are not committed. The committed report keeps the per-slab
evidence and the full radial trace for the selected offsets only.
