# Horizon V5.4 checkpoint

This checkpoint starts from `5fe31e9` and keeps Model A geometry, the frozen
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
- Frozen-camera body box for both phases: `[758, 128, 1150, 345]`.
- Scale trials: +6% = 416 px body width, +9% = 427 px, +12% = 439 px.
  All retain at least 61 px clearance from the vehicle safe-zone limits; the
  selected presentation scale remains 1.00 until a larger production review.
- The selected soft scrim is a single horizontal field, max alpha 36, with a
  two-level-per-pixel boundary and no central vehicle bubble.
- Blind-zone evidence covers none/left/right/both and same-side indicator
  combinations. Left and right overlays are symmetric within 100 pixels and
  have zero measured overlap with the information safe zones.

The blind-zone renderer consumes semantic `VehicleState` values only. The raw
`0x38` rear-left/rear-right candidates remain diagnostic fields and are not
published as confirmed signals; live validation is still pending.

The host suite is green: `ctest --test-dir build` passes 29/29. This includes
phase crop/alpha regression checks, blind-zone evidence checks, and the
existing V5.2 depth/material/motion gates. Mac measurements are not T113
measurements; device performance and visual validation remain
`UNKNOWN_UNTIL_DEVICE_TEST`.

Evidence is in `assets/checkpoints/horizon_v54/metrics.json`, with full-size
and half-size before/after frames, material crops, scale trials, and blind-zone
state frames alongside it.
