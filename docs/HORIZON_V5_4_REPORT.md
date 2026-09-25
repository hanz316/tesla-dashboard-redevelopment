# Horizon V5.4 checkpoint

The takeover started at `ceea1fb`, a descendant of `5fe31e9`, and keeps Model A geometry, the frozen
camera contract, the VehicleState signal contract, and the receive-only UART
principle.

The daylight problem came from a night-derived material rig, a low-frequency
road with no metre-scale variation, and a phase compositor that treated a
different crop margin as a different vehicle scale. V5.4 adds a cool overcast
world gradient, multi-depth terrain with aerial haze, roughness/albedo road
variation, and actual shader controls for paint, glass, tyre, and rim. Phase
vehicle layers are now blended in premultiplied space inside their measured
canvas coordinates.

Measured on the Mac host:

- Day environment: sky 181.4, near ground 111.2, ground/sky ratio 0.61;
  strongest terrain edge 66.0 levels.
- Day material mask: paint mean 143.3, glass 70.5, tyre 19.0, rim 54.0.
- Independently measured body alpha boxes: DAY `[757,127,1152,346]`, NIGHT
  `[757,127,1151,346]`. Exact equality is false; the difference is one raster
  pixel. The previous shared camera-report measurement was not independent.
- Selected common scale: 1.09, anchor `[954,345]`. Presented boxes are DAY
  `[739,107,1170,346]`, NIGHT `[739,107,1168,346]`; minimum body-zone clearance
  is 67 px. +6% was less prominent, while +12% consumed more headroom.
- Raw alpha pixels: DAY 57,590, NIGHT 57,540. Combined shadow/reflection boxes
  before presentation are DAY `[677,127,1185,453]`, NIGHT `[757,127,1151,480]`.
  Those combined footprints still differ and need further motion work.
- The selected soft scrim is a single horizontal field, max alpha 36, with a
  two-level-per-pixel boundary and no central vehicle bubble.
- The peripheral Side Awareness Zone replaced the rejected car-shaped outline.
  Each side is one semantic field whose colour is selected by state: green
  TURN ONLY, amber BLIND PRESENCE ONLY, red SIDE CONFLICT, plus a soft
  secondary silhouette. All three colours share one alpha field exactly and
  the two sides mirror with zero channel error, so the colour carries the
  meaning and the geometry does not.
- Awareness evidence covers none, either side, both sides, turn only, conflict
  and hazards, measured on the layer alone. Information-band overlap is zero
  in every state, and turn intent with no presence reading paints nothing.

The awareness layer consumes semantic `VehicleState` values only. The raw
`0x38` rear-left/rear-right candidates remain diagnostic fields and are not
published as confirmed signals; live validation is still pending. TURN ONLY is
claimed only for a side the state has explicitly measured as clear, so the
layer stays dark where presence is unknown rather than inventing a clear road.

The host suite is green: `ctest --test-dir build` passes 29/29. This includes
phase crop/alpha regression checks, awareness-zone evidence checks, and the
existing V5.2 depth/material/motion gates. Mac measurements are not T113
measurements; device performance and visual validation remain
`UNKNOWN_UNTIL_DEVICE_TEST`.

Evidence is in `assets/checkpoints/horizon_v54/metrics.json`, with full-size
and half-size before/after frames, material crops, scale trials, and
awareness-zone state frames alongside it.

## Continuation audit — 2026-09-25

This is a verified checkpoint, **not completed Horizon acceptance**.
The continuation began at `0900df2`; implementation ends at `e7c7d17`.
The final documentation commit, remote hash and working-tree status are
reported in the delivery message. Earlier local workflow-edit commits were
replaced before successful push; no force push was used.

| Commit | Responsibility |
|---|---|
| `468e3c1` | Build-local Pillow/NumPy dependencies; no silent pixel-test skip |
| `4322325` | Frozen V2 fixtures; retain C++ assertions in Release |
| `8bd5169` | Independently render validated left/right awareness, including both |
| `e7c7d17` | Palette synchronization, +9% presentation, rendered awareness QA |

Changed areas: CMake/host dependency setup; `horizon_v6.h/.cpp`; Horizon/Mono
builders and scenes; shared preview rendering; environment palette source;
blind baker; evidence tools; pixel/C++ regressions. Generated checkpoint images
and frozen 356×236 V2 panel fixtures are committed. V5 working renders remain
local regenerable assets. The current diff is available with
`git diff --stat 0900df2..HEAD`.

### Typography, scrim and visual quality

Primary ink is medium-weight cool graphite `#23323D`, with light road labels
at 20 px and reduced tracking. Heavy text shadows are disabled. The scrim
uses phase multipliers DAY 1.0, DAWN/DUSK 0.25, NIGHT 0.03, fading toward the
vehicle rather than forming circular cards.

At half size, median DAY contrast is speed 3.56, range 2.75 and
RANGE/SOC/POWER labels 2.42–2.59. NIGHT label medians are 6.22–6.83.
DAY readability and terrain/material polish remain **PARTIAL**; these figures
do not establish production readability or photographic-quality acceptance.
See `after_day.png`, `after_night.png`, their `_half` versions and the
`before_after_*` views under `assets/checkpoints/horizon_v54/`.

### Motion, awareness and protocol

Existing wheel blur, road-flow, wake and reflection assets remain. All declared
motion curves now evaluate to zero at standstill, including the formerly
nonzero light-persistence crop. This is a curve-level regression, not a new
complete perceptual motion benchmark. Coordinated continuous rear/chase yaw
and directional environment variants are **NOT_IMPLEMENTED**.

Awareness flows through `VehicleState` → `projectVehicleAwareness` →
`VehicleVisualController`/`HorizonRendererV6`. Production rejects stale,
future-dated, inferred and synthetic presence; replay/simulation require
developer mode. C++ rendering now treats sides independently, so BOTH works.
`HorizonRenderInput.now_ms` must use the same monotonic clock as signal stamps;
production call-site integration remains pending.

The peripheral zone is a state selection, not a tint: presence alone is amber,
same-side turn intent over presence is red, turn intent over a confirmed clear
side is green, and hazards alone are green on both sides. Fresh pixel tests
verify the selection in the awareness layer itself, not merely the extra
turn-lamp pixels: presence and conflict share 97.6 % of their support while
their own pixels differ by up to 69 levels, an opposite-side indicator repaints
the opposite side only (0 pixels on the present side), and UNKNOWN, stale,
synthetic or unmeasured presence paints nothing at all. No collision
probability is inferred. Raw `0x38` candidates remain diagnostic and
**not live validated**. C++ semantic command output is tested, but its older
artwork and the V5 Python artwork have not yet been unified.

### Environment, state matrix and moving assets

The EnvironmentTimeSystem remains the single time source. Fixed-phase JSON
now exactly matches its source palettes, enforced by regression. Existing
solar estimation, Ontario monthly fallback and fixed fallback remain.
Current monthly sunrise/sunset fallback hours: January 7.75/16.83,
April 6.70/19.90, July 5.82/20.77, October 7.90/18.68. The requested full
32-sample seasonal visual matrix has not been regenerated for V5.4.

| Area | Evidence | Status |
|---|---|---|
| DAY/NIGHT neutral and scale trials | Fresh full/half-size images | CHECKPOINT PASS |
| Blind none/left/right/both + same-side indicator | Fresh pixels and C++ tests | HOST SEMANTICS PASS |
| Blind UNKNOWN/STALE | Fresh pixel and C++ tests | PASS |
| Brake/headlight/hazard combinations | Existing tests; incomplete new matrix | PARTIAL |
| Navigation hidden | Zero-pixel V2 regression | PASS FOR V2 ONLY |
| Low SOC/navigation/regen/power draw | Existing bindings | V5.4 MATRIX PARTIAL |
| DAWN/DUSK expanded light/blind matrix | Not regenerated | NOT_RUN |
| V2 doors/frunk/trunk and combinations | Frozen 356×236 assets, composition/ownership tests | PASS FOR V2 ONLY |
| V5-resolution doors/frunk/trunk and combinations | Matching animations absent | NOT_IMPLEMENTED |
| Complete V5 state matrix | Missing coverage above | PARTIAL |

The STALE preview fixture now explicitly marks values stale; a dictionary
containing `value: false` no longer counts as an open panel.

### Performance, testing and continuation

Decoded RGBA inventory: DAY base 831,776 bytes, NIGHT base 666,536 bytes,
two environment plates 7,372,800 bytes. Their subtotal is 8,871,112 bytes.
This **is not measured resident or peak memory**: it excludes other overlays,
scrim, framebuffers, intermediates and caches. Updated 400/600/800 at 30/60 fps
benchmarks, production dirty-region counts and decode costs remain pending.
Stable T113 30 fps is **UNKNOWN_UNTIL_DEVICE_TEST**.

Host suite: 29 CTest entries, now with C++ assertions active in Release.
Missing pixel dependencies install in a build-local venv and fail loudly if
unavailable. An empty Python environment was tested. Frozen V2 fixtures allow
Linux CI to execute previously skipped composition checks. Deterministic
render tests now fix the clock to avoid failures across minute boundaries.

CI at `4322325` passed all 29 checks. The delivery message records the final
exact-commit CI result, rather than substituting that earlier success.
Added checks cover crop placement, premultiplied alpha, visibility, both
awareness sides, stale/synthetic suppression, semantic colors, source/JSON
palette agreement, Mono full/half-size contrast and standstill motion curves.

### Awareness zone continuation — 2026-09-25

The rejected outline was replaced by the peripheral Side Awareness Zone and
the work was finished off against its own gates:

- `bake_horizon_v54_awareness.py` bakes one alpha field per side in three
  semantic colours plus a soft silhouette. The right side is the exact mirror
  of the left; recomputing it from `width - cut` was one pixel off.
- `apply_safe_area` now draws the left panel corner and mirrors it. Filling
  both slanted corners with the polygon rasteriser made them differ by a pixel,
  so every left/right symmetry measurement inherited a 13-level error.
- The preview fixtures now carry `hazards`, which is part of the
  `VehicleState` contract and which the zone reads; without it every hazard
  condition was permanently unknown.
- The evidence is measured on the awareness layer alone and reports the
  information-band overlap, own-side and opposite-side pixels, suppression,
  per-side mirror error and the shared-field overlap ratio.

The layer still needs a live presence source: `0x38` is diagnostic only, and
an unmeasured side deliberately shows nothing. Device validation remains
`UNKNOWN_UNTIL_DEVICE_TEST`.

Horizon overall remains **PARTIAL**. Mono has a corrected host palette
checkpoint: background and text now change together and speed glyphs pass
the 4.5:1 script gate. Full Mono awareness/vehicle integration remains partial.
Other V6 pages retain the existing generated baseline; no new completion
claim is made. Production integration is **NOT_RUN** and device validation
is **UNKNOWN_UNTIL_DEVICE_TEST**.
