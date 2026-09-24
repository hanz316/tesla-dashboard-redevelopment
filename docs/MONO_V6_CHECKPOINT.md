# Mono V6 checkpoint

The `v6_mono` low-cost page now consumes the same `EnvironmentTimeSystem`
palette mapping as Horizon. Its dark canvas remains stable while shared text
and rail literals follow the selected day/night palette. The page still reads
only `VehicleState` bindings; unavailable Commander values render as `--`.

The reproducible host evidence is in
`assets/checkpoints/v6_pages/mono_evidence.json`, with normal, door-open, and
Commander-lost captures under `assets/checkpoints/v6_pages/mono/`.

This is host-render evidence. Device display timing, native font metrics, and
the production Model 3 asset remain `UNKNOWN_UNTIL_DEVICE_TEST`.
