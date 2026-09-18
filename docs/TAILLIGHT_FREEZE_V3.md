# Taillight Freeze Gate V3 - result

Report: `assets/checkpoints/taillight_freeze/freeze_gate_v3.json`
Artifacts: `assets/checkpoints/taillight_freeze/` (masks, overlays, 11 state
renders, 5 trunk positions, 600 px and Horizon composites, `presentation_report.json`)

`MODEL_A_PRODUCTION_MASTER` is **LOCKED** with
`taillight_geometry.version = surface-offset-cavity-lightguide-v3`, at
**43 PASS / 0 FAIL / 0 NOT_RUN / 1 N/A_WITH_EVIDENCE / 1 INFORMATIONAL**.

## Stages 15-16: collision

The overlap detector is validated before it is trusted: two unit cubes placed so
that they intersect report **12 pairs**, the same cubes 5 m apart report **0**.
(The first version of this self-test moved a real guide 25 mm and expected a
hit - it reported 0, and that was correct: a lamp interior is a shell, and a
guide can move several centimetres inside it without crossing a surface.)
The detector also silently returned nothing for n-gon trees; it needs triangle
trees, which `mesh_and_tree()` now builds.

| test | result |
|---|---|
| guide vs body | 0 intersecting pairs |
| guide vs trunk-moving geometry | 0 |
| guide vs unrelated lamp | 0 |
| cavity vs housing/reflector | 8 pairs - INFORMATIONAL |

The cavity is a hidden containment volume whose shell is offset inward from the
lens, so it can occupy the housing and reflector region by construction; its
production constraint is screen-space containment, measured in stages 17-20.

## Stages 17-20: protrusion and screen-space

Binary object masks through the **frozen production camera**, AA off, so
"escaped pixel" is an exact statement rather than a visual judgement.

| measurement | value |
|---|---|
| lamp silhouette | 2298 px |
| guide silhouette | 103 px (the guides are sub-pixel thin at production framing) |
| escaped guide pixels | **0** |
| escaped cavity pixels | 2, both at 1 px from the lamp silhouette |
| escaped beyond tolerance | **0** |

The 1 px tolerance is derived, not chosen: the surface-offset cavity keeps the
original lens surface as its outer wall, so its silhouette is the same
silhouette computed from a different mesh and a one-pixel boundary difference is
rasterisation. Escaped pixels *adjacent* to the silhouette are that artefact;
anything farther would be a protrusion.

## Trunk ownership and motion

Ownership is measured, not inferred from names. Absolute distance to the boot
shell cannot decide it (every lamp sits behind bodywork), so each lamp is
assigned to the panel it is measurably closer to:

| lamp | owner | boot median | body median | ratio |
|---|---|---|---|---|
| `rear_lights` (outer) | FIXED_BODY | 58.6 mm | 46.1 mm | 1.27 |
| `rear_lightsl` / `rear_lightsr` (inner) | TRUNK_MOVING | 17.9 mm | 188.5 mm | 0.095 |
| `light_breake` (brake lamp) | FIXED_BODY | 81.3 mm | 89.8 mm | 0.90 → ambiguous |

The brake lamp is genuinely ambiguous by panel distance, so it is resolved by
geometry: it lies inside the outer lamp's volume, so it belongs to that
assembly. This corrected an earlier assumption that the brake lamp moves with
the lid.

Motion at 0 / 25 / 50 / 75 / 100 % of a 55 degree opening about the lid's own
hinge (95th percentile of boot x and z, axis parallel to Y):

| check, every position | result |
|---|---|
| trunk-owned group follows the lid rigidly | max matrix delta 1.8e-07 |
| fixed-body lamps do not move | max matrix delta 0.0 |
| new guide/body collisions in the open state | 0 |

## TaillightLightingSystem

One state-driven system, one assignment point (`taillight_system.apply_state`)
and one set of channel materials: the guide carries a channel material, the lens
carries the same channel's lens material, and a state is nothing but a set of
logical channels (`tools/blender/taillight_states.py`).

```
outer lamp  (rear_lights,  FIXED_BODY)    brake / rear running light
inner lamp  (rear_lightsl/r, TRUNK_MOVING) indicator, per side
brake lamp  (light_breake,  no interior)  brake, by lens emission only
```

Brake and indicator are on **different lamps**, so a brake can never erase an
indicator by priority - `material_key()` raises instead of choosing if a state
ever asks one lamp for two channels, and the regression test asserts no state
does. This mapping is a documented **VISUAL_APPROXIMATION**: MODEL A cannot
prove the OEM optical segmentation, and no OEM-exact claim is made.

Measured response, share of the taillight region that changes visibly versus
OFF (1100x760, frozen camera):

| state | outer lamp | inner left | inner right | brake lamp |
|---|---|---|---|---|
| BRAKE | 96.6 % | 0 % | 0 % | 98.9 % |
| LEFT_INDICATOR | 0 % | 100 % | 0 % | 0 % |
| RIGHT_INDICATOR | 0 % | 0 % | 98.3 % | 0 % |
| HAZARD | 0 % | 100 % | 98.3 % | 0 % |
| BRAKE_LEFT | 96.6 % | 100 % | 0 % | 98.9 % |
| HEADLIGHT (running) | 92.0 %, p95 +0.12 | 0 % | 0 % | 44 % |

HEADLIGHT is a running light, not a brake: p95 +0.12 against BRAKE's +0.36.
BRAKE_HAZARD and the HEADLIGHT+indicator composites are measured in the report.

### OFF

Two independent checks, and the second is one-sided on purpose:

1. **no taillight material emits** - measured max emission strength 0.0;
2. **OFF adds no light anywhere** relative to the same render with the guides
   and lenses hidden - measured max added light **0.0**.

A non-emissive guide seen through the lens is internal structure (a real lamp
shows its light pipe); OFF being *brighter* anywhere would be the glowing guide
or lighting-residue defect. `state_OFF_no_taillight_geometry.png` is the control
render.

## Production scales

Composited with the pipeline's existing rule: the vehicle's own width becomes
600 px, and the Horizon frame places it at its intended size (700x401 at 610,40)
inside the real 1920x480 composition, then crops 1:1.

| verdict | 600 px | Horizon |
|---|---|---|
| BRAKE lights outer + brake lamp | 876 / 223 px changed (silhouettes 662 / 38) | 1132 / 287 px (900 / 52) |
| indicators one-sided | left 164 px in LEFT, 0 in RIGHT | left 205 px in LEFT, 0 in RIGHT |
| HAZARD both sides | 165 / 115 px | 205 / 160 px |
| OFF shows nothing | PASS | PASS |

The criterion at these scales is an absolute count against each lamp's own
projected silhouette: the indicator occupies only a couple of percent of the
whole taillight region, so a region-wide fraction can never be met by a signal
that small, and lowering it would stop measuring anything.

## The inner-lamp coverage question

The accepted geometry leaves 0.800 / 0.810 slab coverage on the inner lamps,
with the gap in the corner section. Production-camera evidence: the missing
section is **not** a visible dark gap - the inner lamp states change 100 % /
98 % of their own pixels at 600 px and Horizon scale, and the lamp reads as a
complete unit in OFF, BRAKE, LEFT, RIGHT and HAZARD. No geometry was added to
chase the missing slabs, and no gate was loosened.

## Version and lock

`taillight_geometry.version = surface-offset-cavity-lightguide-v3`;
`MODEL_A_PRODUCTION_MASTER.status = LOCKED`. The lock is written by
`taillight_freeze.py` only when the assembled table is lockable, and a gate that
was never computed is recorded as NOT_RUN and blocks the lock - an earlier
version of the gate stage locked the master on a table whose stage results were
absent, which is why `gates_never_computed` exists.

## Reproduce

```
blender -b -P tools/blender/build_production_master.py -- \
    --blend assets/source/blender/model_a_production_master.blend \
    --manifest assets/checkpoints/model_a_production_master/MODEL_A_PRODUCTION_MASTER.json
blender -b -P tools/blender/taillight_freeze.py -- \
    --master assets/source/blender/model_a_production_master.blend \
    --stage all --out-dir assets/checkpoints/taillight_freeze \
    --report assets/checkpoints/taillight_freeze/freeze_gate_v3.json
python3 tools/assets/build_taillight_freeze_outputs.py \
    --out-dir assets/checkpoints/taillight_freeze
blender -b -P tools/blender/taillight_freeze.py -- \
    --master assets/source/blender/model_a_production_master.blend \
    --stage gate --out-dir assets/checkpoints/taillight_freeze \
    --report assets/checkpoints/taillight_freeze/freeze_gate_v3.json
```

## One defect fixed on the way

The production master mapped the tail lamp lenses to the **cavity** material
(near-black matte) because the source material classifies as `LENS_CLEAR` while
the assignment code sent non-red rear lenses to the cavity. The lamps therefore
read as dead panels and no light could leave the guide. They now use the red
outer lens material that exists for exactly this surface. This is a material
*mapping* correction - no frozen material definition, camera, HDRI or lighting
parameter changed.
