# T113 device validation - 2026-09-18

First hardware session against the real cluster, while the car was being
driven. Everything below is measured on the device; the raw captures live in
the gitignored `captures/` directory and are listed with each result.

## Connection and device

| item | value |
|---|---|
| link | ADB over Wi-Fi, `10.144.92.196:5555` |
| device | `Zkswe_T113_SPINOR`, FlyThings **V2.1** |
| panel scanout | **480x1920**, single layer, **60.2 Hz**, backlight 255 |
| framebuffer | `/dev/fb0` = 480x3840 (two pages, 32bpp), logical 1920x480, **rotate 270** |
| memory | MemTotal 249,964 kB; MemFree 154,964 kB; MemAvailable 180,816 kB |
| Wi-Fi throughput | ~0.1 MB/s pulling 7 MB (69 s) - plan deploy times accordingly |

## Live vehicle data - decoded, not inferred

The stock UI was stopped (`setprop ctl.stop zkswe`) so that /dev/ttyS5 was
unclaimed; nothing competed with a running dashboard for the stream.

`captures/uart-live-20260918.bin` - 22,378 bytes in 60 s = **373 B/s**
(about 9 % of 38400 8N1, consistent with ~40 short frames/s):

* **2,637 frames, 0 checksum errors** - the frame format and checksum rule in
  `docs/protocol-table.md` are confirmed against a real car.
* `0x04` speed: **min 23, max 62, 40 distinct values in 60 s** - live and
  tracking the drive. Units read as km/h.
* `0x04` range: 84-85 km.
* `0x04` SOC: **stuck at 97 % for the whole capture** while range said 84 km -
  the documented known-bad SOC, confirmed on live data.
* `0x12` tire pressures: 2.825 / 2.85 / 2.925 / 2.75 bar, stable
  (wheel order still NEEDS REAL CAR TEST).
* `0x01` doors/frunk/trunk bits: 0 (all closed) - consistent with driving.
* `0x07` temperature primary 21-22 C; secondary -23..68 C, so the LIKELY
  mapping for the secondary is **not credible** and should not be shown.

**Discrepancy found:** `0x01` gear nibble was **3** for the whole capture while
the car was being driven in Drive, where the protocol table records
`0 = P, 4 = D`. That field's mapping is wrong or incomplete and needs a
controlled Park/Drive shift to re-measure. Until then it must not drive gear
display.

## Our own build on the device

`build-t113/libzkgui.so` (67,744 B, ELF 32-bit ARM EABI5) deployed to
`/tmp/tesla-dashboard-mvp/lib/` with `deploy/temporary-adb/EasyUI.cfg` in
`/tmp`, then `setprop ctl.restart zkswe`:

* the app runs and loads **our** library (verified in `/proc/<pid>/maps`);
* it holds `/dev/ttyS5` with flags **`lr-x`** - read-only, exactly as the
  safety rule requires;
* **RSS 3,696 kB, 9 threads**, VSIZE 27.9 MB;
* **CPU ~4.4 % of one core** (utime+stime delta over 35 s); the stock UI
  measured ~19 % / 7,960 kB on the same device for comparison;
* its own `/tmp/uart_record` channel produced `captures/uart-ourown-20260918.bin`
  (11,186 bytes / 30 s) which decodes to **1,302 frames, 0 rejections**
  (speed 117, range 80, tires unchanged) - our read path works end to end;
* the framebuffer shows our dark UI: `captures/device-ours-20260918.png`
  (11,259 distinct colours) against `captures/device-stock-20260918.png`,
  mean pixel difference 228.

**Defect found while running:** our app logs missing resources in the stock
`/res` tree - `back_gears_remind.png`, `forward_gears_remind.png`,
`right_speed_max.png` - so those HUD elements render as gaps. Either the
assets must ship with the app or the UI needs a fallback.

## Toolchain reality

`toolchains/toolchain-sunxi-musl/toolchain/bin/arm-openwrt-linux-muslgnueabi-g++`
is a **Linux x86-64** binary and cannot execute on macOS - which is why
`scripts/build_t113.sh` runs inside Docker. Docker/podman/colima are not
installed on this Mac, so the library deployed in this session is the existing
prebuilt ARM build. Rebuilding current sources on this machine needs Docker (or
colima) first; no amount of local cmake/firmware work substitutes for it.

## Device state and how to revert

The add-on cluster is currently running **our** library from /tmp. To go back to
the stock UI:

```bash
adb -s 10.144.92.196:5555 shell 'rm -f /tmp/EasyUI.cfg; setprop ctl.restart zkswe'
```

Nothing outside `/tmp` was written: no `/res`, no MTD/flash, no firmware, and
no vehicle or MCU command was ever sent (the project's read-only rule).

## Still open on hardware

## Controlled-action captures (partial, then stopped by the owner)

A short controlled-action session was run: gear P / R / N / D, then a door
block. The owner then asked to stop re-deriving protocol fields that the stock
cluster already reads correctly, so the campaign was stopped and the stock UI
restored. What the captures still prove, at no further cost:

**Gear is NOT in `0x01`, and `0x02` is only a partial candidate.**

| gear | `0x02` payload (dominant values) | byte 3 | byte 4 |
|---|---|---|---|
| P | `0000000500` / `000000f9ff` | 05 / f9 | 00 / ff |
| N | `0000000200` / `0000000400` | 02 / 04 | 00 |
| D | `0000000900` / `0000000a00` | 09 / 0a | 00 |
| R (while shifting) | `000000ffff` / `000000faff` | ff / fa | **ff** |
| R (parked #1, 409 frames, 0 checksum errors) | `000000e7ff` only | **e7** | **ff** |
| R (parked #2, 410 frames, 0 checksum errors) | `000000edff` (32) + `000000ecff` (1) | **ed / ec** | **ff** |

Findings, stated at the confidence the evidence supports:

* **byte 4 = `0xff` appeared in every R observation** - four separate captures,
  the car shifting and then parked twice, roughly a thousand frames - while P,
  N and D were `0x00` in every capture. That is the one feature that repeats.
* **byte 3 is not a clean gear enum**: in R it moved `ff -> fa -> fe -> f9`
  while shifting and then read `e7` and `ed`/`ec` when parked. P/N/D each
  showed two adjacent values too (`05`/`f9`, `02`/`04`, `09`/`0a`). Read as a
  little-endian pair, R's byte3/byte4 are negative (-1 to -25) while P/N/D sit
  near zero, which looks like a signed actuator or selector quantity rather
  than a gear code.
* **a caveat that cannot be resolved from the UART alone**: selecting R also
  turns on the reverse lamps, so byte 4 may be reporting "reverse state" (lamp
  or camera) rather than the gear selection. Nothing in these captures
  separates those two.
* so the `0x02` mapping stays **LIKELY and INCOMPLETE**. It is not used for
  production gear, and gear remains UNKNOWN in the runtime.

**Correction to an earlier statement in this document:** "across those same four
states `0x01` did not change a single bit" was wrong. All four shifting windows
happened to capture the same `0x01` payload (`810000003c3c001064`), but the
parked-in-R capture shows a completely different one
(`010300001c3d001020`). `0x01` therefore *does* change with vehicle state; its
field layout is simply not decoded, and it must not be read as a gear. The
`docs/protocol-table.md` entry is updated to say that rather than to claim the
command is gear-free.

The door block did not stay controlled - the captures show `0x02` byte 3 moving
between gear values instead of door bits - so no door/frunk/trunk bit is
claimed from this session.

* `ZKImageAnim` capability probe (variable frame size, arbitrary x/y, delta
  sequence, fixed-tight) - needs our current sources on the device, i.e. a
  Docker build.
* Device frame rate of our renderer and its decode timing - needs
  instrumentation inside the app rather than inference from CPU share.
* The `0x01` gear mapping and the wheel order for `0x12`.
* Battery/charging fields and the `0x0D` 20 Hz one-byte stream, still
  unexplained.
