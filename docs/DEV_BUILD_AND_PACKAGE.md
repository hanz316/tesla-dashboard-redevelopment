# Building for the T113 from this Mac, and the DEV package

## Why a container is required (and nothing else works)

Measured on this machine:

| fact | consequence |
|---|---|
| host is **arm64** macOS 26.6.2 | cross tools must either be arm64-native or run under emulation |
| `scripts/build_t113.sh` uses Docker + `docker/t113-build.Dockerfile` (Debian, multi-arch) | the sanctioned path is a **linux/amd64** container |
| `toolchains/toolchain-sunxi-musl/.../bin/arm-openwrt-linux-muslgnueabi-g++` is a **Linux x86-64** ELF | it cannot execute on macOS at all |
| `toolchains/toolchain-t113.zip` contains **`.exe`** binaries (`arm-unknown-linux-musleabihf`) | that is the Windows toolchain, not usable here |
| `toolchains/flythings-ide-20260403.zip` contains **no darwin toolchain** (0 matches) | the IDE does not ship a Mac cross-compiler |
| no `lld`, no cross toolchain installed on the host | clang alone cannot link an ARM Linux shared object |

So the simplest reliable solution is the existing containerised path, unchanged:
**Colima + Docker CLI** running the repository's own Dockerfile. Colima is the
lightweight option on macOS (no Docker Desktop licence, no GUI); it is not a
redesign of the build system, just a container runtime for the same script.

### The one action this run could not take

Installing software on the user's machine is the point where this run stops:

```bash
brew install colima docker
colima start --arch x86_64 --cpu 4 --memory 6
scripts/build_t113.sh          # unchanged, linux/amd64, existing Dockerfile
scripts/package_dev_bundle.sh  # writes dist/dev-bundle + BUILD_INFO.json
```

Everything after that is prepared and tested (see below).

## What the build must produce

`build-t113/libzkgui.so` must be **ELF 32-bit, ARM, EABI5, hard-float, musl**,
matching the instrument. Verify with:

```bash
file build-t113/libzkgui.so
shasum -a 256 build-t113/libzkgui.so
```

`scripts/package_dev_bundle.sh` records the source commit, the artifact hash,
the build mode and the target in `dist/dev-bundle/BUILD_INFO.json`. That file is
what makes the old prebuilt library impossible to confuse with a current build:
the deploy script refuses unless local HEAD == recorded commit and the artifact
hash matches.

## The DEV package

```
dist/dev-bundle/
  EasyUI.cfg                       # startupLibPath -> /tmp/tesla-dashboard-mvp/lib
  BUILD_INFO.json                  # commit, hash, mode, target
  tesla-dashboard-mvp/lib/libzkgui.so
```

Nothing else is packaged: the activity reuses the stock `main.ftu` page and
copies no stock artwork. Only `/tmp` is ever written on the device.

## Deploy and rollback

```bash
# deploy (refuses a non-T113, refuses a mismatched HEAD or hash)
scripts/deploy_dev_bundle.sh --serial <host:port>          # or ADB_SERIAL=...
scripts/deploy_dev_bundle.sh --serial <host:port> --dry-run # prints and stops

# rollback - nothing outside /tmp is touched
scripts/rollback_dev_bundle.sh --serial <host:port>
```

Both scripts take the target explicitly or discover a **unique** connected
device; neither contains a literal IP address, and a test enforces that. The
deploy script prints SOURCE COMMIT, TARGET, ARTIFACT HASH, BUILD MODE and the
rollback command before it pushes anything.

## The /res missing-image question, answered

The deployed MVP logged three missing stock images:
`back_gears_remind.png`, `forward_gears_remind.png`, `right_speed_max.png`.

Root cause: **those strings are not in our source or in our binary.** They are
in the *stock* library (`artifacts/firmware/*/lib/libzkgui.so`) and in the stock
`main.ftu` page that our activity reuses. Our activity only sets the gear
picture (`/home/white_gears_{p,r,n,d}.png`) and text on controls it binds.

Classification: **A - obsolete stock UI dependency**, and not ours to satisfy.
Writing them into `/res` or copying stock artwork into the repository is
explicitly forbidden, and the warnings are non-critical.

What we *did* fix is the rule behind the question: our own display layer now
renders **UNKNOWN as "--"**, never as `0`, and never as a stale number. See
`device/flythings/display_format.{h,cpp}` and its host test.

## The next parked-device session, in order

Everything here is prepared; none of it touches the vehicle during this run.

1. `brew install colima docker && colima start --arch x86_64 && scripts/build_t113.sh`
2. `scripts/package_dev_bundle.sh`
3. `scripts/deploy_dev_bundle.sh --serial <device> --dry-run` (prints the guard)
4. `scripts/deploy_dev_bundle.sh --serial <device>`
5. **ZKImageAnim capability probe** (specified, small and deterministic): the
   bundle carries four tiny PNG pairs; the probe resolves
   `createDecoder/readFrame/updateFrame/drawAnim` from the device's
   `libeasyui.so` at runtime (they are not in the shipped headers) and answers
   four questions with SUPPORTED / PARTIALLY_SUPPORTED / UNSUPPORTED:
   variable frame size, arbitrary per-frame x/y, variable-delta sequence,
   fixed-tight canvas. `device/bench/bench_plan.{h,cpp}` already encodes the
   decision rule: VARIABLE_DELTA only when the device proves it, otherwise the
   mandatory FIXED_TIGHT fallback.
6. **Performance runs** with the same harness: BASE, BASE+brake, indicator,
   one door, trunk, trunk+indicator, one multi-layer Horizon state; record
   achieved fps, p95 frame time, dropped frames, decode time, RSS, CPU, and
   repeat each animation long enough to see whether RSS grows.
7. `scripts/rollback_dev_bundle.sh --serial <device>`

## Live protocol status carried into this work

`docs/protocol-table.md` now records the only live-validated correction from the
2026-09-18 session: the `0x01` gear nibble is **REJECTED_MAPPING**, and the gear
correlates with `0x02` byte 3 (P=0x05, N=0x02, D=0x09, R=0xff) at **LIKELY**
confidence - one observation per gear. `OriginalMcuAdapter` no longer produces a
gear from `0x01` at all, so production gear stays **UNKNOWN** rather than being
filled in with Park.
