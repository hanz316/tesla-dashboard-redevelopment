# Build V6-H1 — Horizon hardware handoff

Branch: `feature/v6-cockpit`

## Build ID

`V6-H1`

## Changes

- V6 core framework is now part of `dashboard_core`: signal validity/staleness, shared VehicleVisualModel, MotionEngine OFF/LOW/FULL, WarningManager, AssetManager, source arbitration, page/safety framework, TripComputer, PerformanceTimer, ReplayAdapter and V6 product state contracts.
- Horizon is implemented as backend-neutral layered `RenderFrameV6` commands: environment, road, lanes, AP corridor, blind zones, coarse surrounding slots, shared vehicle layers, primary data, context rail, turn/safety overlay and critical warnings.
- `IRenderBackendV6` isolates product rendering from EasyUI/FTU. No UI layer reads UART/BLE/PhoneBridge.
- V6 asset catalog defines production paths and decoded-memory estimates. Actual production image binaries are not yet committed.
- Original MCU gear parser corrected to real-car-confirmed nibble `0=P`, `4=D`. Unconfirmed R/N codes remain Unknown rather than guessed.
- Original MCU SOC byte is retained but marked `Estimated`; production Horizon/Safety does not treat this known-untrusted value as actual SOC. Commander `actual_soc` will override when available.
- Replay uses the same OriginalMcuAdapter/parser path and supports 0.5x/1x/2x, pause, seek and restart.
- Commander interfaces are read-only placeholders; no protocol reverse engineering or vehicle-control write surface is included.

## Expected behavior

- Real speed, confirmed P/D, range and confirmed door FL continue to come from `/dev/ttyS5` through OriginalMcuAdapter.
- Stale driving data invalidates rather than freezing an old value.
- If only the known-untrusted MCU SOC is present, normal V6 UI treats SOC as unavailable rather than showing a false 97% as trusted battery state.
- Horizon never converts coarse surrounding presence into fake exact coordinates.
- Critical vehicle-data loss interrupts ordinary page/motion presentation.
- Missing V6 visual assets are a render-backend/asset condition; they must not be replaced with fabricated telemetry.

## How to test

1. Checkout exact handoff commit on `feature/v6-cockpit`.
2. Host:
   - `cmake -S . -B build -DBUILD_HOST_TOOLS=ON -DBUILD_FLYTHINGS_DEVICE=OFF`
   - `cmake --build build -j`
   - `ctest --test-dir build --output-on-failure`
3. T113 cross compile with existing `cmake/t113-musl-toolchain.cmake` / established SDK environment.
4. Confirm the additional `dashboard_core` sources compile for 32-bit musl hard-float and `libzkgui.so` links without new undefined symbols.
5. Deploy only via the existing `/tmp` temporary path. Do not write boot/uboot/res/MCU/Flash.
6. Confirm vehicle UART remains `/dev/ttyS5`, 38400, read-only; check process FDs/symbols for no vehicle write path.
7. Verify real-car state responsiveness:
   - Park -> Drive must become `P -> D` from nibble `0 -> 4`.
   - Driver door open/close must follow bit0.
   - speed and range must update without visual/state lag.
   - MCU SOC should remain diagnostic/untrusted unless a trusted `actual_soc` source exists.
8. Inspect available EasyUI 2.2 SDK/FTU authoring path and implement one `IRenderBackendV6` adapter rather than duplicating Horizon state/layout logic. The repo currently contains the validated compiled `main.ftu` release artifact but not an editable V6 FTU source layout.
9. For the first real Horizon render, map asset IDs from `v6_asset_catalog.cpp` to temporary `/tmp` image assets and capture framebuffer output.
10. Measure stable 30 FPS target, frame time, CPU, RSS and decoded asset memory for Motion OFF/LOW/FULL.

## Signals required

Minimum first pass:
- speed
- gear

Recommended:
- range
- doors/frunk/trunk
- turn indicators/lights if real mapping is available
- AP/blind/coarse surrounding only when current parser/source publishes valid data

Optional enhanced data must remain absent rather than simulated in production.

## Known limitations

- Production V6 PNG/JPG art assets are still missing. The code has the correct layer IDs, lifecycle and memory contract, not final binary art.
- Editable V6 `main.ftu` source is not present in the repository. Do not overwrite the hardware-validated release artifact. Codex should establish the supported EasyUI 2.2 runtime/FTU binding mechanism and implement the backend against confirmed APIs.
- Only P and D are currently real-car confirmed gear values. R/N are intentionally Unknown until validated.
- Navigation, Media/Lyrics and Commander contracts exist, but live integrations are not required for this Horizon hardware pass.
- Exact surrounding-vehicle positions are not available and must not be inferred.

## Performance risk

- Core logic risk: low; host CI builds with warnings enabled and tests core state transitions.
- Render risk: medium until EasyUI backend and real image decoding are measured.
- RAM risk: medium/high if a backend eagerly decodes every catalog asset. It must lazy-load only shared + current page + safety resources and report resident estimates.
- Motion risk: bounded by OFF/LOW/FULL tiers; benchmark at 30 FPS, not desktop 60 FPS.
