# Vehicle state assets -> Horizon

Built from the LOCKED `MODEL_A_PRODUCTION_MASTER`
(`taillight_geometry.version = surface-offset-cavity-lightguide-v3`), following
the contract that already existed (`assets/manifest.json` v6-vehicle v2, canvas
356x236, one camera, one anchor).

Reports:
`assets/checkpoints/vehicle_state_assets/vehicle_state_assets.json`,
`.../vehicle_state_budget.json`, `.../vehicle_state_manifest_check.json`,
`.../horizon_state_report.json`, `.../horizon_state_sheet.png` (contact sheet).

## Static state assets

| asset | source | frames |
|---|---|---|
| `vehicle.base` | frozen master, all panels closed, lights off | 1 |
| `vehicle.brake` | frozen TaillightLightingSystem, `BRAKE` | 1 |
| `vehicle.headlight` | front lamp lens emission (same channel mechanism) | 1 |
| `vehicle.running` | frozen system, rear running light | 1 |
| `vehicle.indicator.left` / `.right` | frozen system, per side | 12-frame loop @12 fps |
| `vehicle.hazard` | frozen system, both sides | 12-frame loop @12 fps |

The indicator loops are a two-state pattern (lit for half the cycle, dark for
the other half), so they are two renders plus ten copies written as a real
12-frame sequence - not twelve renders. `vehicle.headlight` is the FRONT lamp;
the rear running light is recorded separately as `vehicle.running`, which is
also why the manifest needed that entry added (the C++ controller can emit it
and the cross-check test caught the gap).

## Moving body layers

Every pivot is measured on Model A, including the swing sign:

| panel | object | hinge | hinge on edge | sign | far-edge travel | frames |
|---|---|---|---|---|---|---|
| door_fl | `door_lf` | (1.0406, 0.8982, 0.6151) | yes | **-1** | 1.095 m | 16 |
| door_fr | `door_rf` | (1.0406, -0.8976, 0.6151) | yes | **+1** | 1.095 m | 16 |
| door_rl | `door_lr` | (-0.1251, 0.9226, 0.6150) | yes | **-1** | 0.983 m | 16 |
| door_rr | `door_rr` | (-0.1251, -0.9220, 0.6150) | yes | **+1** | 0.983 m | 16 |
| frunk | `bonnet_ok` | (1.1755, 0.0002, 0.8828) | yes | **-1** | 0.855 m | 14 |
| trunk | `boot` | (-1.5192, 0.0002, 1.2041) | yes | **+1** | 0.904 m | 14 |

The left and right doors of the same axle open with opposite signs, which is
exactly what copying Door_FL's constant would have broken. The far-edge travel
is what the sign was chosen to maximise (outward |y| for doors, upward z for
hood and lid), so the choice is a measurement, not a convention.

**Timing**: 16 frames at 24 fps is 0.625 s open, matching the Door_FL baseline
of 0.62 s; the close animation plays the same frames backwards at 0.54 s. Frunk
and trunk are 14 frames (0.542 s) with their own recorded timings. Open is
cubic ease-in-out; no spring, no bounce, no overshoot.

## Animation asset strategy

Per `docs/ANIMATION_STATE_STRATEGY.md`: doors/hood/lid are class A
(pre-rendered `to_state` sequences), brake/headlight/running are class B
(single-frame overlays), indicators are class C (12-frame loop at 12 fps).

Metadata is generated so the same animation can be represented either way:

* variable delta: per-frame dirty pixel counts and the dirty bbox (measured);
* fixed-tight fallback: the union dirty bbox, which is what the mandatory
  fixed-canvas representation needs when `ZKImageAnim` variable-frame support
  is unknown on the device.

Alignment is measured, not assumed: for every frame, every pixel outside the
changed region must match the base within the delta threshold. The measured
noise floor outside those regions is 3-4 levels, which is why the repository's
delta threshold of 4 is the right one rather than an arbitrary number.

## Budget (measured on Mac; decode times estimated for T113)

At the 600 px presentation width (the numbers for 400 and 800 are in the
report), decoded RGBA is 955 KB per frame; the base PNG is 62 KB and moving
frames are 66-70 KB.

Dirty region at 600 px, measured: doors 32-48 K px mean (64-96 K union), frunk
52 K mean, trunk 26 K mean, lighting overlays 32 K. The trunk and the lights are
the cheap layers; the doors are the expensive ones because a door reveals the
interior across a large area.

Composed Horizon path, stated in the two ways that matter separately:

* **resident** -- base + one moving layer + up to three overlays = 5 assets =
  **1.60 MB peak decoded RGBA**, against 3.52 MB for one full 1920x480 frame;
* **per frame** -- one sequence frame is decoded while a panel is moving and
  nothing once it has stopped (the base and the overlays stay resident):
  **20.7 % of the 30 fps budget**, 41.4 % of a 60 fps budget, using the
  repository's 6.9 ms per 356x236 PNG decode.

The pathological alternative -- re-decoding every layer every frame -- would be
103 % of the 30 fps budget. It is recorded only so it cannot be mistaken for
the design.

Scale sensitivity at 600 px: 955 KB decoded per frame, one decode of 19.6 ms.
At 800 px the same decode is 34.8 ms (25 % of a 30 fps budget, 50 % of 60 fps),
which is why 800 px and 60 fps are evaluation data rather than the target.
Actual device fps, real simultaneous decode cost and variable-frame support
remain **UNKNOWN UNTIL DEVICE TEST**.

## VehicleVisualController

`include/dashboard/vehicle_visual_controller.h` +
`src/core/vehicle_visual_controller.cpp`. Consumes canonical `VehicleState`
only: the UI never reads UART, BLE, Commander or PhoneBridge.

* **UNKNOWN != OFF**: a lamp with no signal, an invalid signal or a signal
  older than the policy window is reported `known == Unknown`, never as a
  confirmed off. A door with no fresh signal *holds its position* - it must not
  snap shut, which would draw a physically open door as closed.
* Hazard drives both indicators and never erases one that is already on.
* Panel animation advances by elapsed time toward the signal's target, at the
  panel's own durations, and stops at a terminal state.
* **Production refuses mock**: `applyMockState` returns false unless developer
  mode was explicitly enabled, independent of the asset-source guard
  (`production_allows_placeholder = false`) and of the provider's
  `--require-model3`.
* Layer output is explicit: base first (replacement), then at most one moving
  layer per panel (replacement), then the lighting overlays (never
  replacements).

## Horizon integration

The Horizon scene's `vehicle_visual` node already carried the box, anchor and z
order; what it did not carry was the wiring for the declared layers. The node
now also references `vehicle.frunk`, `vehicle.trunk`, the
`vehicle.brake`/`vehicle.headlight` overlays and the two indicator loops, in all
three redesign candidates. No layout, box, anchor or z value changed, and
Horizon itself was not redesigned.

18 states composited at 1920x480 through the production vehicle assets
(`--require-model3`, source reported as `RENDERED_MODEL3`) and measured against
the neutral frame:

| state | changed pixels | state | changed pixels |
|---|---|---|---|
| normal_drive | 0 (baseline) | vehicle_frunk | 26 533 |
| vehicle_brake | 11 725 | vehicle_trunk_brake | 14 512 |
| vehicle_left | 11 708 | vehicle_fl_rr_brake | 19 156 |
| vehicle_right | 11 729 | all_open | 51 859 |
| vehicle_hazard | 12 446 | uart_lost | 20 887 |
| vehicle_headlight | 12 070 | vehicle_stale_doors | 8 936 |

Every lighting channel, every moving panel and the composites reach the screen;
a state that silently produced an identical image would show up here as zero.

## Tests

* `tests/vehicle_visual_controller_tests.cpp` - UNKNOWN != OFF, stale, invalid,
  indicator/brake/hazard composition, door terminal state, hold-on-missing,
  production mock refusal, layer order and replacement flags.
* `tests/vehicle_asset_manifest_tests.py` - every asset id the C++ controller can
  emit exists in the manifest, every manifest entry resolves to a real file with
  the declared canvas, every Horizon scene reference resolves, production mode
  refuses placeholder art, peak decoded RGBA stays under two full frames.

`ctest --test-dir build` -> **10/10**.

## Open items (device, not host)

* `ZKImageAnim` support for variable-size frames, arbitrary x/y and delta
  sequences - UNKNOWN UNTIL DEVICE TEST; the fixed-tight canvas metadata is
  generated for exactly this reason.
* Actual decode time, achieved fps and peak RSS on the T113 - UNKNOWN.
* The trunk carries the inner lamps, so a lighting overlay composited onto a
  trunk-open frame has to follow the panel. Per-frame screen-space affines are
  recorded in the asset report for that; the trunk+brake composite is verified,
  the trunk+indicator composite is not yet visually compared against a
  ground-truth render.
