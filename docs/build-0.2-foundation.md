# Build 0.2 foundation

This change starts the productization work on top of the hardware-validated Build 0.1 baseline.

## Included

- Per-domain stale timeouts for `VehicleState`.
- Stale signals become invalid for consumers while preserving the last timestamp/source/quality/unit for diagnostics.
- Runtime UART health now distinguishes open/waiting/healthy/stale/lost states.
- Runtime snapshots expose last RX timestamp, RX age, byte count, read error count and number of signals expired in that snapshot.
- The driving UI no longer renders unavailable Speed/SOC/Range/Tire values as fake zeroes.
- Gear background is cleared when gear data is unavailable.
- Door text is reduced to closure state plus a compact UART health label; packet/CRC/unknown-command counters are removed from the driving surface.
- Dedicated host tests cover stale expiration, diagnostic provenance preservation and monotonic-clock regression handling.

## Safety

The vehicle UART remains `/dev/ttyS5` opened with `O_RDONLY`. No transmit API, `write`, raw CAN TX, MCU firmware write or persistent flash modification is added.

## Host verification performed by ChatGPT

- Core stale tests: pass with C++14, `-Wall -Wextra -Wpedantic`.
- Existing parser/adapter core tests reconstructed from the Build 0.1 source: pass.
- `device_runtime.cpp`: C++14 syntax/compile check passes on host.
- `main_activity.cpp`: C++14 syntax check passes against minimal EasyUI-compatible stubs.

## Codex T113 validation checklist

1. Pull the Build 0.2 commit.
2. Run the normal host CMake build and `ctest --output-on-failure`.
3. Run `bash scripts/build_t113.sh`.
4. Confirm the target ELF is still 32-bit ARM EABI5 and links no `write` symbol for vehicle UART output.
5. Package and deploy only through the existing `/tmp` ADB path.
6. Restart the app and verify PID/maps point at the temporary `libzkgui.so`.
7. Confirm `/dev/ttyS5` is still opened read-only.
8. Capture a 1920x480 framebuffer screenshot at rest.
9. Verify Speed, Gear, SOC, Range, Doors and Tire Pressure against the real vehicle.
10. Temporarily interrupt UART reception without writing to the vehicle and verify values age out to unavailable instead of freezing indefinitely.
11. Capture log, CPU, RAM and frame timing.
12. Report any EasyUI API/runtime incompatibility and the screenshot back to ChatGPT for the next UI pass.

## Not yet claimed complete

- Physical door and tire ordering still requires controlled real-car confirmation.
- This commit improves the existing stock-FTU presentation but does not yet replace `main.ftu` with the final premium 1920x480 layout.
- UART Recorder/Replay/Developer Mode remain Build 0.3 work.
