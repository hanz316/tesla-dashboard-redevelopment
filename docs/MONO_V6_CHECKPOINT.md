# Mono V6 checkpoint

The `v6_mono` low-cost page now consumes the same `EnvironmentTimeSystem`
palette mapping as Horizon in the host preview. Background and text change
together; the previous dark-on-dark daylight aliasing was a regression, not a
passing baseline. Unavailable telemetry renders as `--`. The capture named
`lost` represents absent telemetry, not a separately verified Commander fault.

The reproducible host evidence is in
`assets/checkpoints/v6_pages/mono_evidence.json`, with normal, door-open, and
Commander-lost captures under `assets/checkpoints/v6_pages/mono/`.

This is a palette checkpoint, not completed Mono integration. Reusing the
production awareness and vehicle renderer still needs implementation. Speed
glyph contrast is measured from rendered pixels at full and half size, and
the evidence generator fails below 4.5:1. The clock is fixed for repeatability.
Device display timing, native font metrics, and
the production Model 3 asset remain `UNKNOWN_UNTIL_DEVICE_TEST`.
