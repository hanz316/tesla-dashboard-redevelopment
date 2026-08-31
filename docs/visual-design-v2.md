# Visual Design V2 — Premium Production Cockpit

Status: implementation target for the seven-page product simulator and later T113 renderer.

## Global visual language

V2 is not a recolor of V1. The visual hierarchy is explicitly layered:

1. Background environment
2. Vehicle / route / power stage
3. Primary driving data
4. Context
5. Safety overlay

Rules:
- Remove at least 60% of persistent rounded cards. Cards are reserved for transient context or safety overlays.
- Default background is graphite/off-black, not pure black. No realtime Gaussian blur, WebGL, particle systems, or frame-by-frame PNG animation.
- Blue is a semantic accent, not a default decoration. Route and energy may use their own restrained semantic accents.
- Debug/source/confidence/unverified labels are Developer Mode only.
- Typography targets: speed 120–180 px, hero 48–72 px, primary 32–44 px, secondary 22–28 px, ordinary text >=16 px where practical.
- Safety Layer always wins z-order over media/navigation/BMS.
- 1920x480 native composition with calibrated trapezoid safe area.
- Stable 30 FPS is the first performance target.

## 01 HORIZON

Spatial daily-driving cockpit. The vehicle sits inside a lightweight perspective road/lane environment instead of inside a vehicle card. Speed is centered over the road space. Nearby vehicles and future AP state belong to the same environment layer. SOC/range and maneuver context float without large card backgrounds.

## 02 MONO

Typography-first. Speed is the dominant object. Gear, SOC, range, time and temperature are the only persistent secondary information. No decorative vehicle, telemetry panels, or filler UI.

## 03 PULSE

Power Stage architecture. A single central REGEN <-> POWER axis is the visual backbone. Pack power is the hero value; front/rear motor output, accelerator and performance timing are satellites around that axis. It must not read as a telemetry table.

## 04 ROUTE

The route polyline is the page. Position, destination, next maneuver and ETA are composed around one continuous route graphic. No map card + ETA card split. Route rendering remains intentionally lightweight and does not require a map engine.

## 05 STUDIO

Cinematic music cockpit. Album art supplies a precomputed dominant-color environment. Current lyric is the hero element; previous and next lyrics are subordinate. Album art, title/artist and progress are integrated into one composition. Runtime blur is forbidden; dominant-color/low-resolution background assets should be prepared before rendering.

## 06 ENERGY

Energy topology, not gauges. Battery is the central energy node and front/rear motors are connected with lightweight segmented flow. Cell visualization is a deviation grid around pack average, not an EQ-style bar graph. BMS detail remains secondary to the energy flow.

## 07 NOCTURNE

Purpose-built low-luminance cockpit. It retains a very dark road/AP spatial environment rather than becoming an empty black screen. Lanes, ego vehicle and nearby vehicles use extremely low luminance; speed remains the brightest object. Navigation context remains visible with minimal emitting area.

## Motion budget

- Number micro-transition: 80–120 ms
- State/toggle: 150–220 ms
- Context/safety card: 180–260 ms (critical warnings are immediate)
- Page transition: 280–380 ms
- Day/night transition: 400–650 ms

Use state-driven interpolation only. Motion must be globally disableable for A/B performance testing.

## Developer Mode

The normal driving UI must not show source names, confidence, protocol labels, `UNVERIFIED`, UART counters, or diagnostic ages. Developer Mode may expose these in a dedicated diagnostic overlay/page without changing normal product hierarchy.

## Acceptance criteria

A V2 page is not accepted merely because it renders on the host. It must pass: host screenshot review at 1920x480, no safe-area clipping, no overlap with Safety Layer, unavailable-data `--` behavior, motion-off A/B, and later real T113 framebuffer/FPS/CPU/RAM validation.