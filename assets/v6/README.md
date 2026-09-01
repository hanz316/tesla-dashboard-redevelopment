# V6 cockpit asset contract

V6 uses pre-rendered assets for visual richness on T113. Runtime code must never flatten an entire concept screen into one background image.

## Residency

Always-resident candidates: shared vehicle base needed by active page, turn-signal/safety overlays, tiny common masks. Full-page assets are lazy-loaded through `AssetManager` and released on page exit.

## Horizon layers

Expected production assets:

- `shared/vehicle/model3_body_rear_2p5d.png`
- `shared/vehicle/model3_glass.png`
- `shared/vehicle/model3_headlights.png`
- `shared/vehicle/model3_brake_lights.png`
- `shared/vehicle/model3_indicator_left.png`
- `shared/vehicle/model3_indicator_right.png`
- `shared/vehicle/model3_door_fl.png`
- `shared/vehicle/model3_door_fr.png`
- `shared/vehicle/model3_door_rl.png`
- `shared/vehicle/model3_door_rr.png`
- `shared/vehicle/model3_frunk.png`
- `shared/vehicle/model3_trunk.png`
- `horizon/environment_graphite.jpg`
- `horizon/road_surface.jpg`
- `horizon/lane_near.png`
- `horizon/lane_far.png`
- `horizon/ap_corridor.png`
- `horizon/blind_zone_left.png`
- `horizon/blind_zone_right.png`
- `horizon/coarse_vehicle_front.png`
- `horizon/coarse_vehicle_left.png`
- `horizon/coarse_vehicle_right.png`

The initial engineering renderer may use fallback primitives when an asset is missing, but production builds must not treat those primitives as final visual assets.

## Truthfulness

Coarse surrounding-car layers represent only coarse presence regions. They must not encode fake distance/heading. Precise positions are enabled only when `SurroundingPositionMode::Precise` is backed by a real source.
