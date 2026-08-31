# Seven-page dashboard product status

The seven dashboard pages now have real render implementations in the standalone
`dashboard_product_simulator`. They are not seven skins: each page has its own
information architecture while sharing `VehicleState`, `ProductState`,
`ThemeManager`, `PageManager`, `MotionEngine`, `ContextRouter`, `WarningManager`
and the common Safety Layer.

## Implemented pages

1. **HORIZON** — default flagship driving page. Vehicle silhouette, speed, gear,
   SOC/range, status strip and context card.
2. **MONO** — minimal driving page. Speed/gear/SOC/range with conditional closure
   messaging and large negative space.
3. **PULSE** — performance page. Front/rear motor, pack power, power/regen strip,
   accelerator, brake temperatures and performance-timer surface.
4. **ROUTE** — navigation page. Lightweight route strip, next maneuver, road,
   remaining time/distance, ETA, arrival SOC and traffic delay.
5. **STUDIO** — media/lyrics page. Album-art slot, title/artist, three-line lyrics,
   progress, transport surface and lyric offset indicator.
6. **ENERGY** — battery/BMS page. Pack voltage/current/power, actual SOC,
   remaining energy, power-flow diagram, cell summary and cell-deviation preview.
7. **NOCTURNE** — dedicated night layout with near-black background, reduced light
   area, speed/gear/SOC/range and minimal navigation context.

## Shared Safety Layer

The Safety Layer is rendered after the selected page so non-driving pages cannot
hide core driving information. It supports:

- speed
- gear
- SOC (Commander `actual_soc` first, MCU fallback marked unverified)
- left/right turn signal reserved signals
- critical/warning overlay
- moving door/frunk/trunk warnings
- vehicle-data-loss warning

Turn-signal fields are reserved in `VehicleState`; no MCU/Commander decoder was
added and the fields remain unavailable on real data until a source supplies
them.

## Standalone simulator

Target: `dashboard_product_simulator`

It is independent of UART recordings, FlyThings, device backups and stock UI
assets. It uses SDL2 + SDL2_ttf and runs at 1920x480 with the calibrated
trapezoid mask (top cut 116 px, bottom cut 51 px).

Interactive controls:

- `Left/Right`, `1..7`: page navigation
- `T`: Dark / Graphite / Light theme cycle
- `M`: motion A/B enable/disable
- `C`: enable/disable **simulator-only** Commander telemetry
- `L/R`: simulated turn indicators
- `O`: simulated driver door open
- `Up/Down`: simulated speed

The simulator-only Commander mode exists solely to exercise PULSE and ENERGY
layouts. It writes signals with `SignalSource::Simulation`; it is not a
Commander decoder and must never be treated as live vehicle data.

## Screenshot validation

Run:

```bash
bash scripts/render_product_pages.sh /tmp/tesla-dashboard-pages
```

Expected outputs:

```text
/tmp/tesla-dashboard-pages/dashboard-page-1.bmp  # Horizon
/tmp/tesla-dashboard-pages/dashboard-page-2.bmp  # Mono
/tmp/tesla-dashboard-pages/dashboard-page-3.bmp  # Pulse
/tmp/tesla-dashboard-pages/dashboard-page-4.bmp  # Route
/tmp/tesla-dashboard-pages/dashboard-page-5.bmp  # Studio
/tmp/tesla-dashboard-pages/dashboard-page-6.bmp  # Energy
/tmp/tesla-dashboard-pages/dashboard-page-7.bmp  # Nocturne
```

## Truthfulness / unavailable data

Real product UI must render unavailable signals as `--`. The standalone
simulator may optionally inject clearly marked `SignalSource::Simulation`
fixtures to visually validate Commander-dependent layouts. No runtime UI reads
UART/BLE/PhoneBridge packets directly.

## Remaining validation before device claim

The product implementation is complete enough for host rendering, but it is not
claimed T113-validated until Codex performs:

1. host build + `ctest`
2. seven screenshot generation
3. visual inspection for safe-area clipping
4. FlyThings port of the accepted layouts
5. `/tmp` device deployment only
6. framebuffer screenshots page-by-page
7. FPS / CPU / RAM measurements
8. long-run stability check

No vehicle control, raw CAN TX, MCU write, Flash write or Commander protocol
implementation is part of this work.
