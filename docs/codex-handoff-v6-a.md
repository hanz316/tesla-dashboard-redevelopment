# Build V6-A — Codex hardware handoff

Branch: `feature/v6-cockpit`

## Changes

- Signal now distinguishes valid / stale / unavailable while preserving stale source, quality and sample timestamp.
- VehicleState expanded for V6 cockpit and future Commander telemetry; unavailable fields remain invalid.
- Added V6 cockpit core: MotionEngine OFF/LOW/FULL, safety-priority interrupt semantics, AssetManager residency accounting, WarningManager, shared VehicleVisualModel, coarse/precise surrounding-position capability, HorizonScene state builder, basic source arbitration helper.
- SimulationAdapter expanded for lighting, turn/hazard, AP/blind-zone/coarse surrounding state and enhanced power simulation.
- Added V6 asset contract under `assets/v6/`.
- Added Horizon engineering preview renderer with 1920x480 trapezoid mask. The fallback vehicle primitive is development-only until layered vehicle PNG assets are supplied.
- Added V6 unit tests and CMake target.

## Expected behavior

- Existing Original MCU parser path remains read-only and unchanged.
- Existing real vehicle fields continue to populate VehicleState.
- Stale samples become `valid=false, stale=true` and retain original source/timestamp for diagnostics.
- Horizon scene never invents precise surrounding vehicle positions when only coarse presence is available.
- Critical vehicle-data-loss and driving-priority values bypass normal motion smoothing.
- AssetManager refuses loads beyond configured budget and releases non-shared page assets at zero references.

## How to test

1. Host build/tests:
   `cmake -S . -B build -DBUILD_HOST_TOOLS=ON -DBUILD_FLYTHINGS_DEVICE=OFF`
   `cmake --build build -j`
   `ctest --test-dir build --output-on-failure`
2. T113 cross compile using existing toolchain and current safe process.
3. Deploy only to `/tmp` using the established temporary path.
4. Verify UART remains `/dev/ttyS5` at 38400 and no write path is introduced.
5. Confirm speed/gear/doors still respond with real vehicle data.
6. Measure baseline RSS and CPU before any large V6 assets are added.

## Signals required for first Horizon hardware pass

Required: speed, gear. Recommended: SOC, range, doors/frunk/trunk, turn indicators/lights when mapped, AP/blind-zone/coarse surrounding state when available.

## Known limitations

- Production Model 3 layered visual assets are not yet present; current host renderer has a development-only fallback vehicle.
- NavigationState/MediaState/Commander decoding are intentionally not integrated in this build.
- Exact surrounding-vehicle coordinates are not used.
- Full EasyUI V6 page wiring is the next implementation step after core build compatibility is confirmed.

## Performance risk

Low in the new core logic. Asset memory is the main future risk; production images must be lazy-loaded and measured on T113. Motion is time-based and supports OFF/LOW/FULL.
