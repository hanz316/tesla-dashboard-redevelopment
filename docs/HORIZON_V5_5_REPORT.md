# Horizon V5.5 — chase camera and one motion vector

The complaint this round answers is not a decoration problem: at 88 km/h the car
still looked parked in a showroom. Wheel blur, wake and road flow existed, but
the whole-screen language of movement did not. V5.5 adds the missing piece and
ties every existing motion effect to it.

## 1. The camera is a camera, not a rotated picture

The Horizon car is a real 3D render behind the frozen orthographic camera, so
the chase view is a camera orbit: `--yaw-deg` moves the camera around the car
and the existing framing solver re-solves the frame afterwards. Nothing about
the vehicle geometry, the camera family or the anchor contract changes.

Measured direction: the negative direction orbits **towards the car's rear**.
The positive direction swings towards the car's side, which is why the sweep is
recorded as `-4/-7/-10/-13/-16` in the render report and as a magnitude in the
runtime.

| yaw | silhouette change vs 0 | body anchor drift | body height before correction | presented height after correction |
|---|---|---|---|---|
| +4° | 0.130 | 0.0 px | ×1.050 | ×1.011 |
| +7° | 0.188 | 0.0 px | ×1.092 | ×1.019 |
| +10° | 0.235 | 0.0 px | ×1.142 | ×1.006 |
| +13° | 0.270 | 0.0 px | ×1.193 | ×0.992 |
| +16° | 0.306 | 0.0 px | ×1.252 | ×0.975 |

Two things follow from that table.

* The framing solver pins the projected **width**, so an orbit foreshortens the
  car and it would grow taller on screen — the scale pumping the review forbids.
  The measured `height_ratio_vs_standstill` per baked angle is applied at
  runtime, which is what the last column shows: the presented car keeps its size
  while its projected shape changes with the view.
* The car's own anchor does not move at any angle (0.0 px). The rendered
  footprint's centre does drift up to 7.5 px at the widest angles, and that is
  the wet-road response changing shape, not the car; it is reported separately
  rather than hidden inside the anchor gate.

## 2. Selected angle

`+4/+7/+10/+13/+16` were rendered for both night and day
(`horizon_v55_chase_yaw_sweep.png`). The automatic rule — the smallest angle
clearing a third of the largest silhouette change with the anchor and the
presented height intact — selects **+7°**. The review also requires 80 km/h to be
clearly rear-three-quarter, and the curve reaches 0.68 of the maximum at 80 km/h;
that needs a maximum of **+10°**, which is the production value
(`CHASE_YAW_MAX_DEG`). Both numbers are in
`assets/checkpoints/horizon_v55/horizon_v55_yaw_selection.json`; the choice is
documented, not silent.

The camera curve is `0/1.8/6.8/10.0°` at `0/30/80/120 km/h`, monotone, with a
maximum step below 0.2°/km/h and exactly zero at a standstill.

## 3. One screen motion vector

`tools/assets/horizon_v5_motion.py` now owns `screen_motion_vector(speed)`:
direction `+y` (the car travels away from the camera, so road-level detail
travels towards the viewer), one intensity, and every dependent magnitude —
camera yaw, road flow, wake trail, reflection stretch, environment parallax.
The layout builder, the bakers and the evidence all read that one function, so
the car, the road, the reflection and the wake cannot point in different
directions.

| speed | yaw | band shift measured / declared | road flow | wheel band Δ | wake Δ | road band Δ |
|---|---|---|---|---|---|---|
| 0 | 0.0° | 0 / 0 px | 0 px | 0 | 0 | 0 |
| 10 | 0.5° | 1 / 0.14 px | 15 px | 19 226 | 1 266 | — |
| 30 | 1.8° | 1 / 1.09 px | 57 px | 33 563 | 6 500 | — |
| 60 | 5.0° | 5 / 3.5 px | 112 px | 46 540 | 11 595 | — |
| 80 | 6.8° | 5 / 5.19 px | 142 px | 49 831 | 12 951 | 73 913 |
| 120 | 10.0° | 5 / 7.0 px | 190 px | 54 163 | 14 791 | 80 739 |

At a standstill every motion-generated effect is exactly zero (measured residual
0 pixels over the whole panel).

## 4. Environment response

The distance layer is the plate and does not move. The near ground is baked as
its own band (`bake_horizon_v55_ground_band.py`, cut at row 173 with a 22-row
feather) and translates along the motion vector, so the far-to-near difference
is a real parallax rather than a whole-screen rotate. It is an image crop of the
plate's own ground: nothing is synthesised, nothing is blurred at runtime.

## 5. Vehicle size: DAY and NIGHT at one contract

The review asked for a larger car in both DAY and NIGHT and for the largest size
that still clears every information zone. The trials are a fixed experiment from
the accepted V5.4 presentation:

| trial | scale | speed zone | energy zone | navigation | trapezoid mask | bottom | DAY/NIGHT body Δ |
|---|---|---|---|---|---|---|---|
| current | 1.09 | 67 px | 511 px | 54.9 px | 669.9 px | 134 px | 0 px |
| +4 % | 1.1336 | 59 px | 503 px | 45.9 px | 661.9 px | 134 px | 0 px |
| +7 % | 1.1663 | 52 px | 496 px | 38.9 px | 654.9 px | 134 px | 0 px |
| **+10 %** | **1.199** | **46 px** | **490 px** | **31.9 px** | **648.9 px** | **134 px** | **0 px** |

**+10 % is selected** (`assets/ui/horizon_v54_presentation.json`): it is the
largest tested scale, every clearance stays positive and DAY and NIGHT present
the identical body box (0 px difference at every trial). The forward-looking
door/frunk/trunk gate is a V2-frozen estimate: those states do not extend the
measured silhouette box (24 103 alpha pixels in base, `door_fl` and `door_rl`
alike), so an open panel is not expected to consume the inbound clearance. The
V5-resolution version of those animations is **NOT_IMPLEMENTED**.

## 6. Awareness under the chase camera

Ten semantic states were rendered at 0 and 80 km/h
(`horizon_v55_awareness_chase.png`). The peripheral field never enters the
information band (0 pixels in every state at both speeds), the two sides remain
exact mirrors (0 channel error), and the camera yaw does not move the UI (0
pixels changed between 0 and 120 km/h).

One real defect was found and fixed: at the +9 % body width the car's near flank
reached x 739 while the secondary silhouette sat at 612, so the ghost overlapped
the car itself by 37 pixels. The ghost now sits at 572/1180 and the measured
overlap is 0 pixels at both speeds.

## 7. Braking

Brake frames at 0/30/80/120 km/h are measured, including how much of the change
lands below the ground contact line (7 426/7 150/7 272/7 271 pixels: the rear
pixels are the lamp and the response is the road plane, with no new wide blob).
Brake-under-chase composition is `horizon_v55_brake_motion.png`.

## 8. Performance inventory (not measured RSS)

| item | decoded RGBA |
|---|---|
| vehicle layers, night standstill (7 layers) | 4 665 752 B |
| one environment plate | 3 686 400 B |
| one ground band | 2 357 760 B |
| awareness assets | 4 722 600 B |
| UI overlays | 8 787 540 B |

Chase yaw is a layered asset dimension: three baked angles per phase are enough
for a continuous curve, and the runtime blends the two that bracket the speed.
No speed × phase × state product is pre-baked. PNG file size is **not** treated
as RAM anywhere in this report. Device performance remains
`UNKNOWN_UNTIL_DEVICE_TEST`.

## 9. Status, honestly

| item | status |
|---|---|
| Chase camera yaw curve, layered assets, anchor contract | **PASS (host, measured)** |
| Screen motion vector coherence | **PASS (host, measured)** |
| Environment parallax band | **PASS (host, measured)** |
| Vehicle scale contract DAY/NIGHT | **PASS (host, measured)** |
| Awareness semantics under chase | **PASS (host, measured)** |
| UI fixed in screen space | **PASS (host, measured)** |
| Chase yaw variants for DAWN and DUSK | **NOT_IMPLEMENTED** (runtime falls back to the accepted presentation for those phases) |
| Awareness fades / conflict attack timing | **TOKENS DECLARED, NOT_IMPLEMENTED** in the host previewer |
| Acceleration / regen environment response | **NOT_IMPLEMENTED** (the propulsion/regen sign convention of `battery_power` is not confirmed) |
| DAY visual quality | **PARTIAL** — unchanged this round, by instruction |
| DI/T113 performance, device visual validation | **UNKNOWN_UNTIL_DEVICE_TEST** |

Green CI is not visual completion, and no device claim is made here.
